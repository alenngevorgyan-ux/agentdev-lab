"""Job scheduling decisions."""

from datetime import datetime, timedelta, timezone

from .scheduling import parse_window


def is_within_window(moment, spec):
    """Whether ``moment`` falls inside the maintenance window."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("moment must be timezone-aware")

    # Windows are defined in UTC, so the moment is normalised before comparison
    # rather than compared against a window built from a local date.
    moment_utc = moment.astimezone(timezone.utc)
    start, end = parse_window(spec, day=moment_utc.date())
    if start <= moment_utc <= end:
        return True

    # A window that opened on the previous day may still be running.
    previous_start, previous_end = parse_window(
        spec, day=moment_utc.date() - timedelta(days=1)
    )
    return previous_start <= moment_utc <= previous_end


def next_run_after(moment, interval_minutes):
    """The next run time after ``moment``."""
    return moment + timedelta(minutes=interval_minutes)


def now():
    return datetime.now(timezone.utc)
