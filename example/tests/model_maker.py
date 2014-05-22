# -*- encoding: utf-8 -*-
from __future__ import unicode_literals

from base.tests.model_maker import clean_and_save

from example.models import SalesLedger


def make_sales_ledger(email, title, product, quantity, **kwargs):
    defaults = dict(
        email=email,
        title=title,
        product=product,
        quantity=quantity,
    )
    defaults.update(kwargs)
    return clean_and_save(SalesLedger(**defaults))
