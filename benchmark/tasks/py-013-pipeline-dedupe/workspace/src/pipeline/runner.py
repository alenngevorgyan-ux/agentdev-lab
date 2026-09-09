"""Pipeline driver."""

from .registry import STAGES


def run_pipeline(records, context=None):
    """Run every registered stage in order, returning (records, context)."""
    context = dict(context or {})
    current = [dict(record) for record in records]
    for stage in STAGES:
        current = stage.run(current, context)
    return current, context
