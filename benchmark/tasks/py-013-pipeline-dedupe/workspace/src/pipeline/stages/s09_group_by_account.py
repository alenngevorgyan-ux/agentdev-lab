"""Group records by their account key."""

from ..helpers import keyed


def run(records, context):
    groups = {}
    for key, record in keyed(records, "account"):
        groups.setdefault(key, []).append(record)
    context["groups"] = groups
    return records
