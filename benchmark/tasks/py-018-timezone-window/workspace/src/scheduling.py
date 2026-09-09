"""Maintenance window parsing."""

from datetime import datetime, timedelta


def parse_window(spec, day=None):
    """Parse a "HH:MM-HH:MM" window into (start, end) datetimes.

    ``day`` is the date the window opens on; today is used when omitted.
    """
    start_text, end_text = spec.split("-")
    base = day or datetime.utcnow().date()

    start = datetime.combine(base, datetime.strptime(start_text, "%H:%M").time())
    end = datetime.combine(base, datetime.strptime(end_text, "%H:%M").time())
    if end <= start:
        end = end + timedelta(days=1)
    return start, end


def window_length(spec):
    start, end = parse_window(spec)
    return end - start
