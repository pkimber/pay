# -*- encoding: utf-8 -*-
import pytest

from example_pay.tests.factories import CardRefreshFactory
from finance.tests.factories import VatSettingsFactory
from pay.tests.helper import check_payment


@pytest.mark.django_db
def test_link_to_payment():
    VatSettingsFactory()
    card_refresh = CardRefreshFactory()
    check_payment(card_refresh)