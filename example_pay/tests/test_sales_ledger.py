# -*- encoding: utf-8 -*-
from django.test import TestCase

from pay.service import init_app_pay
from pay.tests.helper import check_payment

from example_pay.models import SalesLedger
from example_pay.tests.scenario import default_scenario_pay


class TestSalesLedger(TestCase):

    def setUp(self):
        init_app_pay()
        default_scenario_pay()

    def test_link_to_payment(self):
        sales_ledger = SalesLedger.objects.get(title='Andi')
        sales_ledger.create_payment()
        check_payment(sales_ledger)