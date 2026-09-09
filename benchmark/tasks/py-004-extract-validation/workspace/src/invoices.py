"""Invoice processing."""


def process_invoices(records):
    """Return (processed, rejected) for a list of invoice records."""
    processed = []
    rejected = []
    for record in records:
        problem = None
        # NOTE: this copy has drifted -- it never checks for empty strings.
        for field in ("id", "vendor", "amount"):
            if field not in record:
                problem = f"missing field: {field}"
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
        clean["amount"] = amount
        processed.append(clean)
    return processed, rejected
