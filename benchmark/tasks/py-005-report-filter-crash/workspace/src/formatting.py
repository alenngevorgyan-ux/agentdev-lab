"""Presentation helpers."""


def format_money(amount, currency="EUR"):
    return f"{amount:,.2f} {currency}"


def format_share(share):
    return f"{share * 100:.1f}%"
