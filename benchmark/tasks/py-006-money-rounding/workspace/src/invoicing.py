"""Invoice assembly."""

from .money import round_money
from .pricing import line_total, subtotal


def tax_for(amount, tax_rate):
    """Tax due on an amount."""
    return round_money(amount * tax_rate / 100)


def invoice_total(lines, tax_rate=0):
    """Grand total for an invoice."""
    total = 0.0
    for line in lines:
        line_amount = line_total(line["unit_price"], line["quantity"], line.get("discount_pct", 0))
        total += line_amount + tax_for(line_amount, tax_rate)
    return round_money(total)


def invoice_breakdown(lines, tax_rate=0):
    """Structured invoice: subtotal, tax and total."""
    net = subtotal(lines)
    tax = tax_for(net, tax_rate)
    return {"subtotal": net, "tax": tax, "total": round_money(net + tax)}
