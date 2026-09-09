"""Assemble the output rows the loader will write."""

def run(records, context):
    context["output"] = [
        {
            "id": record.get("id"),
            "account_key": record.get("account_key"),
            "amount_base": record.get("amount_base", 0.0),
            "region": record.get("region"),
        }
        for record in records
    ]
    return records
