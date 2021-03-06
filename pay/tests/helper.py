# -*- encoding: utf-8 -*-
from django.core.urlresolvers import reverse

from base.tests.model_maker import clean_and_save

from pay.models import PaymentState


def check_payment(model_instance):
    """The 'Payment' model links to generic content."""
    # can we create a payment instance (need to set url before save).
    payment = model_instance.create_payment()
    assert payment.paymentline_set.count() > 0, "no payment lines"
    payment.url = reverse('project.home')
    payment.url_failure = reverse('project.home')
    clean_and_save(payment)
    # can the generic content be paid?
    paid = PaymentState.objects.get(slug=PaymentState.PAID)
    model_instance.payment_state
    model_instance.set_payment_state(paid)
    # do we have mail templates for paid and pay later?
    assert model_instance.mail_template_name
    # the generic content must implement 'get_absolute_url'
    model_instance.get_absolute_url()
    # the generic content must implement 'allow_pay_later'
    model_instance.allow_pay_later()
    clean_and_save(model_instance)
