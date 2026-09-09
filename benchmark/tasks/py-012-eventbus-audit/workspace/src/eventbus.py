"""A small synchronous event bus.

Semantics that callers must respect:

* ``subscribe(topic, handler)`` returns an opaque **subscription token**.
  Pass that token to ``unsubscribe`` -- the handler object itself is not a
  valid key, because the same callable may be subscribed more than once.
* Handlers are invoked synchronously in subscription order.
* A handler that raises is **automatically unsubscribed**, and the exception
  is swallowed. A handler that must survive bad input has to catch its own
  errors.
* ``publish`` returns the number of handlers that were invoked without
  raising.
* Re-entrant publishing is capped at ``MAX_DEPTH`` to stop event loops; the
  cap is silently enforced by dropping deeper publishes.
"""

import itertools

MAX_DEPTH = 4


class EventBus:
    def __init__(self):
        self._subscriptions = {}          # token -> (topic, handler)
        self._tokens = itertools.count(1)
        self._depth = 0

    def subscribe(self, topic, handler):
        """Register ``handler`` for ``topic``; returns a subscription token."""
        token = next(self._tokens)
        self._subscriptions[token] = (topic, handler)
        return token

    def unsubscribe(self, token):
        """Remove a subscription by token. Unknown tokens are ignored."""
        self._subscriptions.pop(token, None)

    def publish(self, topic, payload):
        """Deliver ``payload`` to every handler of ``topic``."""
        if self._depth >= MAX_DEPTH:
            return 0
        self._depth += 1
        try:
            delivered = 0
            for token, (subscribed_topic, handler) in list(self._subscriptions.items()):
                if subscribed_topic != topic:
                    continue
                try:
                    handler(topic, payload)
                    delivered += 1
                except Exception:
                    # Documented behaviour: a raising handler is dropped.
                    self._subscriptions.pop(token, None)
            return delivered
        finally:
            self._depth -= 1

    def subscription_count(self, topic=None):
        """How many live subscriptions exist, optionally for one topic."""
        if topic is None:
            return len(self._subscriptions)
        return sum(1 for subscribed, _ in self._subscriptions.values() if subscribed == topic)
