"""Report construction."""

from .filters import apply_filters


def summarise_by_category(sales):
    totals = {}
    for sale in sales:
        totals[sale.category] = totals.get(sale.category, 0.0) + sale.amount
    return totals


def build_report(repository, filter_names):
    """Build a category breakdown of the filtered sales."""
    sales = apply_filters(repository.all(), filter_names)
    totals = summarise_by_category(sales)
    grand_total = sum(totals.values())

    lines = []
    for category in sorted(totals, key=lambda name: (-totals[name], name)):
        amount = totals[category]
        # An empty or zero-valued result set is a legitimate report, not an error.
        share = amount / grand_total if grand_total else 0.0
        lines.append({"category": category, "amount": amount, "share": share})
    return {"total": grand_total, "rows": lines, "filters": list(filter_names)}
