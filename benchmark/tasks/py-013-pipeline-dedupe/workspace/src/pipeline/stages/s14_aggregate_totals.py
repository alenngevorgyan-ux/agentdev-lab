"""Compute per-account totals into the context."""

from ..helpers import keyed


def run(records, context):
    totals = {}
    for key, record in keyed(records, "account"):
        totals[key] = round(totals.get(key, 0.0) + record.get("amount_base", 0.0), 2)
    context["totals"] = totals
    return records
