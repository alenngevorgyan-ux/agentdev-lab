"""Job scheduling decisions."""

from datetime import datetime, timedelta, timezone

from .scheduling import parse_window


def is_within_window(moment, spec):
    """Whether ``moment`` falls inside the maintenance window."""
    start, end = parse_window(spec, day=moment.date())
    return start <= moment <= end


def next_run_after(moment, interval_minutes):
    """The next run time after ``moment``."""
    return moment + timedelta(minutes=interval_minutes)


def now():
    return datetime.now(timezone.utc)
