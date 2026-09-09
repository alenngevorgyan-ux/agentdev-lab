"""Order processing."""


def process_orders(records):
    """Return (processed, rejected) for a list of order records."""
    processed = []
    rejected = []
    for record in records:
        problem = None
        for field in ("id", "customer", "amount"):
            if field not in record:
                problem = f"missing field: {field}"
                break
            value = record[field]
            if isinstance(value, str) and not value.strip():
                problem = f"empty field: {field}"
                break
        if problem is None:
            try:
                amount = float(record["amount"])
            except (TypeError, ValueError):
                problem = "amount is not a number"

        if problem is not None:
            rejected.append((record, problem))
            continue

        clean = dict(record)
        for key, value in clean.items():
            if isinstance(value, str):
                clean[key] = value.strip()
        clean["amount"] = amount
        processed.append(clean)
    return processed, rejected
