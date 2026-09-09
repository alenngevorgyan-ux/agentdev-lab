"""Notification dispatch."""

from .registry import get_channel


def send(channel, recipient, body):
    """Send a notification over ``channel``."""
    return get_channel(channel)["sender"](recipient, body)
