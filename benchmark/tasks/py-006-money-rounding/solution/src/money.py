"""Money helpers."""

from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


def round_money(amount):
    """Round a monetary amount to cents, half-up.

    Decimal's default rounding is half-even, which is not what invoicing
    expects; the mode is therefore stated explicitly.
    """
    return Decimal(amount).quantize(CENTS, rounding=ROUND_HALF_UP)
