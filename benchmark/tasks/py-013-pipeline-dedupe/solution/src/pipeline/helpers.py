"""Helpers shared by several pipeline stages."""

UNASSIGNED = "<unassigned>"


def coerce_key(record, field):
    """Return the grouping key for ``field`` in ``record``.

    A missing, null or blank value is a legitimate state, not a reason to drop
    the record: it groups under UNASSIGNED.
    """
    value = record.get(field)
    if value is None:
        return UNASSIGNED
    key = str(value).strip().lower()
    return key or UNASSIGNED


def keyed(records, field):
    """Pair each record with its key. Every record is yielded."""
    for record in records:
        yield coerce_key(record, field), record


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
