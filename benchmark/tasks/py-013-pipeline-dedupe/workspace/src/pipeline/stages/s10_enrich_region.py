"""Derive a region from the account key prefix."""

def run(records, context):
    regions = context.get("regions", {})
    for record in records:
        key = record.get("account_key") or ""
        record["region"] = regions.get(key.split("-")[0], "unknown")
    return records
