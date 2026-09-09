"""Channel registry.

A channel is described once -- how to send it and how to render it -- so
adding one no longer means editing every module that dispatches on channel.
"""

from .errors import UnknownChannel

_CHANNELS = {}


def register_channel(name, sender, template):
    """Register a channel with its sender callable and its template."""
    _CHANNELS[name] = {"sender": sender, "template": template}


def get_channel(name):
    """Return the registered channel, or raise UnknownChannel."""
    try:
        return _CHANNELS[name]
    except KeyError:
        raise UnknownChannel(f"unknown channel: {name}") from None


def available_channels():
    """Names of every registered channel."""
    return sorted(_CHANNELS)


def _send_email(recipient, body):
    return {"channel": "email", "to": recipient, "body": body, "transport": "smtp"}


def _send_sms(recipient, body):
    return {"channel": "sms", "to": recipient, "body": body[:160], "transport": "gateway"}


def _send_push(recipient, body):
    return {"channel": "push", "to": recipient, "body": body, "transport": "fcm"}


register_channel("email", _send_email, "Dear {name},\n\n{message}\n\nRegards,\nThe team")
register_channel("sms", _send_sms, "{name}: {message}")
register_channel("push", _send_push, "{message}")
