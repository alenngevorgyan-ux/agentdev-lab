"""Audit trail for order events."""


class AuditLog:
    """Records order events published on an EventBus.

    Args:
        bus: the EventBus to subscribe to.
    """

    ORDER_TOPICS = ("order.created", "order.paid", "order.cancelled")

    def __init__(self, bus):
        raise NotImplementedError

    def records(self):
        """Recorded events, in arrival order."""
        raise NotImplementedError

    def detach(self):
        """Unsubscribe from every topic this log subscribed to."""
        raise NotImplementedError
