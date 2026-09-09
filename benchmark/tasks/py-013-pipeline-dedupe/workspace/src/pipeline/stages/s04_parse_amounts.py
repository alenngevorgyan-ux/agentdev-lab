"""Coerce the amount field to a float."""

from ..helpers import as_float


def run(records, context):
    for record in records:
        record["amount"] = as_float(record.get("amount"))
    return records
