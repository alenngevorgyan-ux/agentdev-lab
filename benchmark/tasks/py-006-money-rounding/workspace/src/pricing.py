"""Line pricing."""

from .money import round_money


def line_total(unit_price, quantity, discount_pct=0):
    """Total for one invoice line, after discount."""
    unit = round_money(unit_price)
    discounted = unit * (1 - discount_pct / 100)
    return round_money(discounted * quantity)


def subtotal(lines):
    """Sum of the line totals."""
    return round_money(
        sum(line_total(line["unit_price"], line["quantity"], line.get("discount_pct", 0))
            for line in lines)
    )
