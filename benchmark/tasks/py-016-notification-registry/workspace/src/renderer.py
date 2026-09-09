"""Template selection."""

from .errors import UnknownChannel


def render(channel, context):
    """Render the message body for ``channel``."""
    if channel == "email":
        template = "Dear {name},\n\n{message}\n\nRegards,\nThe team"
    elif channel == "sms":
        template = "{name}: {message}"
    elif channel == "push":
        template = "{message}"
    else:
        raise UnknownChannel(f"unknown channel: {channel}")
    return template.format(**context)
