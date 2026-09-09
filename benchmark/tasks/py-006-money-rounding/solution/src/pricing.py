"""Line pricing."""

from decimal import Decimal

from .money import round_money

HUNDRED = Decimal("100")


def line_total(unit_price, quantity, discount_pct=0):
    """Total for one invoice line, after discount.

    Quantity and discount are applied at full precision; the result is rounded
    exactly once, so no intermediate rounding can accumulate into cent drift.
    """
    unit = Decimal(unit_price)
    factor = (HUNDRED - Decimal(discount_pct)) / HUNDRED
    return round_money(unit * Decimal(quantity) * factor)


def subtotal(lines):
    """Sum of the already-rounded line totals."""
    total = Decimal("0")
    for line in lines:
        total += line_total(line["unit_price"], line["quantity"], line.get("discount_pct", 0))
    return round_money(total)
