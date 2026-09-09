"""Convert amounts into the reporting currency."""

def run(records, context):
    rates = context.get("fx_rates", {})
    for record in records:
        rate = rates.get(record.get("currency"), 1.0)
        record["amount_base"] = round(record.get("amount", 0.0) * rate, 2)
    return records
