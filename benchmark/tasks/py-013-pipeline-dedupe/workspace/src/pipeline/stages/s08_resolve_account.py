"""Attach the grouping account key used downstream."""

from ..helpers import coerce_key


def run(records, context):
    for record in records:
        record["account_key"] = coerce_key(record, "account")
    return records
