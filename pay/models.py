# -*- encoding: utf-8 -*-
from __future__ import unicode_literals

from decimal import Decimal

from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

import reversion

from base.model_utils import TimeStampedModel


def default_payment_state():
    return PaymentState.objects.get(slug=PaymentState.DUE)


class PayError(Exception):

    def __init__(self, value):
        Exception.__init__(self)
        self.value = value

    def __str__(self):
        return repr('%s, %s' % (self.__class__.__name__, self.value))


class PaymentState(TimeStampedModel):

    DUE = 'due'
    FAIL = 'fail'
    LATER ='later'
    PAID = 'paid'

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ('name',)
        verbose_name = 'Payment state'
        verbose_name_plural = 'Payment state'

    def __str__(self):
        return '{}'.format(self.name)

reversion.register(PaymentState)


class Payment(TimeStampedModel):
    """List of payments."""

    name = models.TextField()
    email = models.EmailField()
    title = models.CharField(max_length=100)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    state = models.ForeignKey(
        PaymentState,
        default=default_payment_state,
    )
    url = models.CharField(
        max_length=100,
        help_text='redirect to this location after payment.'
    )
    url_failure = models.CharField(
        max_length=100,
        help_text='redirect to this location if the payment fails.'
    )
    # link to the object in the system which requested the payment
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey()

    class Meta:
        ordering = ('pk',)
        # payment should only link to one other object.
        unique_together = ('object_id', 'content_type')
        verbose_name = 'Payment'
        verbose_name_plural = 'Payment'

    def __str__(self):
        return '{} = {}'.format(self.description, self.total)

    def _description(self):
        return '{} ({} x £{:.2f})'.format(self.title, self.quantity, self.price)
    description = property(_description)

    def _set_payment_state(self, payment_state):
        """Mirror payment state to content object (to make queries easy)."""
        self.state = payment_state
        self.save()
        self.content_object.payment_state = payment_state
        self.content_object.save()

    def _total(self):
        return self.price * self.quantity
    total = property(_total)

    def check_can_pay(self):
        if not self.state.slug in (PaymentState.DUE, PaymentState.FAIL):
            raise PayError(
                'Cannot pay this transaction (it is not due or '
                'failed earlier) [{}]'.format(self.pk)
            )
        td = timezone.now() - self.created
        diff = td.days * 1440 + td.seconds / 60
        if abs(diff) > 5:
            raise PayError(
                'Cannot pay this transaction. '
                'It is too old (or has travelled in time).'
            )

    def check_can_pay_later(self):
        if not self.state.slug == PaymentState.LATER:
            raise PayError(
                'Cannot pay this transaction (it is not due to '
                'be paid later) [{}]'.format(self.pk)
            )

    def is_paid(self):
        return self.state.slug == PaymentState.PAID

    def mail_template_context(self):
        return {
            self.email: dict(
                description=self.description,
                name=self.name,
                total='£{:.2f}'.format(self.total),
            ),
        }

    def save_token(self, token):
        self.check_can_pay()
        self.token = token
        self.save()

    def set_paid(self):
        payment_state = PaymentState.objects.get(slug=PaymentState.PAID)
        self._set_payment_state(payment_state)

    def set_payment_failed(self):
        payment_state = PaymentState.objects.get(slug=PaymentState.FAIL)
        self._set_payment_state(payment_state)

    def set_pay_later(self):
        payment_state = PaymentState.objects.get(slug=PaymentState.LATER)
        self._set_payment_state(payment_state)

    def total_as_pennies(self):
        return int(self.total * Decimal('100'))

reversion.register(Payment)


class StripeCustomer(TimeStampedModel):

    email = models.EmailField(unique=True)
    customer_id = models.TextField()

    class Meta:
        ordering = ('pk',)
        verbose_name = 'Stripe customer'
        verbose_name_plural = 'Stripe customers'

    def __str__(self):
        return '{} ({})'.format(self.email, self.customer_id)

reversion.register(StripeCustomer)
