"""Template selection."""

from .registry import get_channel


def render(channel, context):
    """Render the message body for ``channel``."""
    return get_channel(channel)["template"].format(**context)
