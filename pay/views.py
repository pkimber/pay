# -*- encoding: utf-8 -*-
import logging
import stripe

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseRedirect
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from braces.views import (
    LoginRequiredMixin,
    StaffuserRequiredMixin,
)

from base.view_utils import BaseMixin
from mail.models import Notify
from mail.service import (
    queue_mail_message,
    queue_mail_template,
)
from mail.tasks import process_mail

from .forms import StripeForm
from .models import (
    Payment,
    StripeCustomer,
)
from .service import (
    PAYMENT_LATER,
    PAYMENT_THANKYOU,
)


CURRENCY = 'GBP'
PAYMENT_PK = 'payment_pk'

logger = logging.getLogger(__name__)

#class PayPalFormView(LoginRequiredMixin, BaseMixin, FormView):
#
#    form_class = PayPalPaymentsForm
#    template_name = 'pay/paypal.html'
#
#    def get_initial(self):
#        return dict(
#            business=settings.PAYPAL_RECEIVER_EMAIL,
#            amount='10.01',
#            currency_code='GBP',
#            item_name='Cycle Routes around Hatherleigh',
#            invoice='0001',
#            notify_url="https://www.example.com" + reverse('paypal-ipn'),
#            return_url="https://www.example.com/your-return-location/",
#            cancel_return="https://www.example.com/your-cancel-location/",
#        )


def _check_perm(request, payment):
    """Check the session variable to make sure it was set."""
    payment_pk = request.session.get(PAYMENT_PK, None)
    if payment_pk:
        if not payment_pk == payment.pk:
            logger.critical(
                'payment check: invalid {} != {}'.format(
                    payment_pk, payment.pk,
            ))
            raise PermissionDenied('Valid payment check fail.')
    else:
        logger.critical('payment check: invalid')
        raise PermissionDenied('Valid payment check failed.')


def _send_notification_email(payment, request):
    email_addresses = [n.email for n in Notify.objects.all()]
    if email_addresses:
        subject, message = payment.mail_subject_and_message(request)
        queue_mail_message(
            payment,
            email_addresses,
            subject,
            message,
        )
    else:
        logging.error(
            "Cannot send email notification of payment.  "
            "No email addresses set-up in 'enquiry.models.Notify'"
        )


@require_POST
def pay_later_view(request, pk):
    payment = Payment.objects.get(pk=pk)
    _check_perm(request, payment)
    payment.check_can_pay
    payment.set_pay_later()
    queue_mail_template(
        payment,
        payment.mail_template_name,
        payment.mail_template_context(),
    )
    _send_notification_email(payment, request)
    process_mail.delay()
    return HttpResponseRedirect(payment.url)


class PaymentAuditListView(
        LoginRequiredMixin, StaffuserRequiredMixin,
        BaseMixin, ListView):

    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(dict(audit=True))
        return context

    def get_queryset(self):
        return Payment.objects.payments_audit()


class PaymentListView(
        LoginRequiredMixin, StaffuserRequiredMixin,
        BaseMixin, ListView):

    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(dict(audit=False))
        return context

    def get_queryset(self):
        return Payment.objects.payments()


class StripeFormViewMixin(object):

    form_class = StripeForm
    model = Payment

    def _init_stripe_customer(self, name, email, token):
        """Make sure a stripe customer is created and update card (token)."""
        result = None
        try:
            c = StripeCustomer.objects.get(email=email)
            self._stripe_customer_update(c.customer_id, name, token)
            result = c.customer_id
        except StripeCustomer.DoesNotExist:
            customer = self._stripe_customer_create(name, email, token)
            c = StripeCustomer(**dict(
                customer_id=customer.id,
                email=email,
            ))
            c.save()
            result = c.customer_id
        return result

    def _log_card_error(self, e, payment_pk):
        logger.error(
            'CardError\n'
            'payment: {}\n'
            'param: {}\n'
            'code: {}\n'
            'http body: {}\n'
            'http status: {}'.format(
                payment_pk,
                e.param,
                e.code,
                e.http_body,
                e.http_status,
            )
        )

    def _log_stripe_error(self, e, message):
        logger.error(
            'StripeError\n'
            '{}\n'
            'http body: {}\n'
            'http status: {}'.format(
                message,
                e.http_body,
                e.http_status,
            )
        )

    def _stripe_customer_create(self, name, email, token):
        """Use the Stripe API to create/update a customer."""
        try:
            return stripe.Customer.create(
                card=token,
                description=name,
                email=email,
            )
        except stripe.StripeError as e:
            self._log_stripe_error(e, 'create - email: {}'.format(email))

    def _stripe_customer_update(self, customer_id, name, token):
        """Use the Stripe API to create/update a customer."""
        try:
            customer = stripe.Customer.retrieve(customer_id)
            customer.card = token
            customer.description = name
            customer.save()
        except stripe.StripeError as e:
            self._log_stripe_error(e, 'update - id: {}'.format(customer_id))

    def get_context_data(self, **kwargs):
        context = super(StripeFormViewMixin, self).get_context_data(**kwargs)
        _check_perm(self.request, self.object)
        self.object.check_can_pay
        context.update(dict(
            currency=CURRENCY,
            description=self.object.description,
            email=self.object.email,
            key=settings.STRIPE_PUBLISH_KEY,
            name=settings.STRIPE_CAPTION,
            total=self.object.total_as_pennies(),
        ))
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        # Create the charge on Stripe's servers - this will charge the user's card
        token = form.cleaned_data['stripeToken']
        self.object.save_token(token)
        # Set your secret key: remember to change this to your live secret key
        # in production.  See your keys here https://manage.stripe.com/account
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            customer_id = self._init_stripe_customer(
                self.object.name, self.object.email, token
            )
            stripe.Charge.create(
                amount=self.object.total_as_pennies(), # amount in pennies, again
                currency=CURRENCY,
                customer=customer_id,
                description=', '.join(self.object.description),
            )
            with transaction.atomic():
                self.object.set_paid()
            queue_mail_template(
                self.object,
                self.object.mail_template_name,
                self.object.mail_template_context(),
            )
            _send_notification_email(self.object, self.request)
            process_mail.delay()
            result = super(StripeFormViewMixin, self).form_valid(form)
        except stripe.CardError as e:
            self.object.set_payment_failed()
            self._log_card_error(e, self.object.pk)
            result = HttpResponseRedirect(self.object.url_failure)
        except stripe.StripeError as e:
            self.object.set_payment_failed()
            self._log_stripe_error(e, 'payment: {}'.format(self.object.pk))
            result = HttpResponseRedirect(self.object.url_failure)
        return result

    def get_success_url(self):
        return self.object.url
