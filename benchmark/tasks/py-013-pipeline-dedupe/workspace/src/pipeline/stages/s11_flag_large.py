"""Flag records above the large-transaction threshold."""

def run(records, context):
    threshold = context.get("large_threshold", 1000.0)
    for record in records:
        record["is_large"] = record.get("amount", 0.0) >= threshold
    return records
