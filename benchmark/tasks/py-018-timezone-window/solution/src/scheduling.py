"""Maintenance window parsing."""

from datetime import datetime, timedelta, timezone


def parse_window(spec, day=None):
    """Parse a "HH:MM-HH:MM" window into (start, end) aware UTC datetimes.

    ``day`` is the date the window opens on; today (UTC) is used when omitted.
    """
    start_text, end_text = spec.split("-")
    base = day or datetime.now(timezone.utc).date()

    start = datetime.combine(
        base, datetime.strptime(start_text, "%H:%M").time(), tzinfo=timezone.utc
    )
    end = datetime.combine(
        base, datetime.strptime(end_text, "%H:%M").time(), tzinfo=timezone.utc
    )
    # A window whose end is not after its start runs through midnight.
    if end <= start:
        end = end + timedelta(days=1)
    return start, end


def window_length(spec):
    start, end = parse_window(spec)
    return end - start
