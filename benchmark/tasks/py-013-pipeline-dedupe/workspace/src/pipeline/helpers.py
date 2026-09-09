"""Helpers shared by several pipeline stages."""

UNASSIGNED = "<unassigned>"


def coerce_key(record, field):
    """Return the grouping key for ``field`` in ``record``.

    Records that carry no value for the field are meant to be grouped under
    UNASSIGNED rather than dropped.
    """
    value = record.get(field)
    if not value:
        return None
    return str(value).strip().lower()


def keyed(records, field):
    """Pair each record with its key, skipping records without one."""
    for record in records:
        key = coerce_key(record, field)
        if key is None:
            continue
        yield key, record


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
