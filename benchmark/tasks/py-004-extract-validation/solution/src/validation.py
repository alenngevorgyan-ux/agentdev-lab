"""Shared record validation."""


class ValidationError(ValueError):
    """Raised when a record does not satisfy its required shape."""


def validate_record(record, required_fields):
    """Return a normalised copy of ``record`` or raise ValidationError."""
    for field in required_fields:
        if field not in record:
            raise ValidationError(f"missing field: {field}")
        value = record[field]
        if isinstance(value, str) and not value.strip():
            raise ValidationError(f"empty field: {field}")

    clean = {
        key: value.strip() if isinstance(value, str) else value for key, value in record.items()
    }
    if "amount" in clean:
        try:
            clean["amount"] = float(clean["amount"])
        except (TypeError, ValueError):
            raise ValidationError("amount is not a number") from None
    return clean
