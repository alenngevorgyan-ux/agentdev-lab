"""Default the currency to the pipeline default."""

def run(records, context):
    default = context.get("default_currency", "EUR")
    for record in records:
        record["currency"] = (record.get("currency") or default).upper()
    return records
