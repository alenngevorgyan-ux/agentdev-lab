"""Audit trail for order events."""

import copy


class AuditLog:
    """Records order events published on an EventBus."""

    ORDER_TOPICS = ("order.created", "order.paid", "order.cancelled")

    def __init__(self, bus):
        self._bus = bus
        self._records = []
        # The bus keys subscriptions by token, not by handler, so the tokens
        # are what must be kept in order to detach later.
        self._tokens = [bus.subscribe(topic, self._handle) for topic in self.ORDER_TOPICS]

    def _handle(self, topic, payload):
        # The bus unsubscribes any handler that raises, so a malformed payload
        # must never escape from here.
        try:
            snapshot = copy.deepcopy(payload)
        except Exception:
            snapshot = None
        self._records.append({"topic": topic, "payload": snapshot})

    def records(self):
        """Recorded events, in arrival order."""
        return list(self._records)

    def detach(self):
        """Unsubscribe from every topic this log subscribed to."""
        for token in self._tokens:
            self._bus.unsubscribe(token)
        self._tokens = []
