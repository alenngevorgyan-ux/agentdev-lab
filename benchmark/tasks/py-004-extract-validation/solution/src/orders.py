"""Order processing."""

from src.validation import ValidationError, validate_record

REQUIRED_FIELDS = ("id", "customer", "amount")


def process_orders(records):
    """Return (processed, rejected) for a list of order records."""
    processed = []
    rejected = []
    for record in records:
        try:
            processed.append(validate_record(record, REQUIRED_FIELDS))
        except ValidationError as exc:
            rejected.append((record, str(exc)))
    return processed, rejected
