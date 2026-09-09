"""Invoice processing."""

from src.validation import ValidationError, validate_record

REQUIRED_FIELDS = ("id", "vendor", "amount")


def process_invoices(records):
    """Return (processed, rejected) for a list of invoice records."""
    processed = []
    rejected = []
    for record in records:
        try:
            processed.append(validate_record(record, REQUIRED_FIELDS))
        except ValidationError as exc:
            rejected.append((record, str(exc)))
    return processed, rejected
