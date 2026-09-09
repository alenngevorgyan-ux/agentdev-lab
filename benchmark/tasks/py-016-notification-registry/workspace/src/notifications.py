"""Notification dispatch."""

from .errors import UnknownChannel


def _send_email(recipient, body):
    return {"channel": "email", "to": recipient, "body": body, "transport": "smtp"}


def _send_sms(recipient, body):
    return {"channel": "sms", "to": recipient, "body": body[:160], "transport": "gateway"}


def _send_push(recipient, body):
    return {"channel": "push", "to": recipient, "body": body, "transport": "fcm"}


def send(channel, recipient, body):
    """Send a notification over ``channel``."""
    if channel == "email":
        return _send_email(recipient, body)
    elif channel == "sms":
        return _send_sms(recipient, body)
    elif channel == "push":
        return _send_push(recipient, body)
    else:
        raise UnknownChannel(f"unknown channel: {channel}")
