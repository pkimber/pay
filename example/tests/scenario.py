# -*- encoding: utf-8 -*-
from __future__ import unicode_literals

from decimal import Decimal

from stock.tests.model_maker import (
    make_product,
    make_product_category,
    make_product_type,
)

from example.tests.model_maker import make_sales_ledger


def default_scenario_pay():
    stock = make_product_type('Stock', 'stock')
    stationery = make_product_category('Stationery', 'stationery', stock)
    pencil = make_product('Pencil', 'pencil', Decimal('1.32'), stationery)
    make_sales_ledger('test@pkimber.net', 'Carol', pencil, 2)
    make_sales_ledger('test@pkimber.net', 'Andi', pencil, 1)
