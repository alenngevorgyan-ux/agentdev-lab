"""Invoice assembly."""

from decimal import Decimal

from .money import round_money
from .pricing import subtotal

HUNDRED = Decimal("100")


def tax_for(amount, tax_rate):
    """Tax due on an amount, rounded once."""
    return round_money(Decimal(amount) * Decimal(tax_rate) / HUNDRED)


def invoice_total(lines, tax_rate=0):
    """Grand total: rounded subtotal plus tax on that subtotal."""
    net = subtotal(lines)
    return round_money(net + tax_for(net, tax_rate))


def invoice_breakdown(lines, tax_rate=0):
    """Structured invoice: subtotal, tax and total."""
    net = subtotal(lines)
    tax = tax_for(net, tax_rate)
    return {"subtotal": net, "tax": tax, "total": round_money(net + tax)}
