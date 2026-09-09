"""Money helpers."""

from decimal import Decimal

CENTS = Decimal("0.01")


def round_money(amount):
    """Round a monetary amount to cents."""
    return round(float(amount), 2)
