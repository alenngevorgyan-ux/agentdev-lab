"""Reject an output batch that lost records."""

def run(records, context):
    output = context.get("output", [])
    context["validated"] = len(output) == len(records)
    return records
