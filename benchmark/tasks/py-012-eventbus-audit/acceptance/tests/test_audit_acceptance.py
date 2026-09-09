"""Hidden acceptance tests for correct use of the bus API."""

import unittest

from src.audit import AuditLog
from src.eventbus import EventBus


class SubscriptionTest(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.log = AuditLog(self.bus)

    def test_subscribes_to_exactly_three_topics(self):
        self.assertEqual(self.bus.subscription_count(), 3)
        for topic in ("order.created", "order.paid", "order.cancelled"):
            self.assertEqual(self.bus.subscription_count(topic), 1)

    def test_detach_removes_every_subscription(self):
        self.log.detach()
        self.assertEqual(self.bus.subscription_count(), 0)

    def test_detach_is_idempotent(self):
        self.log.detach()
        self.log.detach()
        self.assertEqual(self.bus.subscription_count(), 0)

    def test_two_logs_on_one_bus_are_independent(self):
        second = AuditLog(self.bus)
        self.bus.publish("order.paid", {"id": "o9"})
        self.assertEqual(len(self.log.records()), 1)
        self.assertEqual(len(second.records()), 1)
        second.detach()
        self.bus.publish("order.paid", {"id": "o10"})
        self.assertEqual(len(self.log.records()), 2)
        self.assertEqual(len(second.records()), 1)


class RecordingTest(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.log = AuditLog(self.bus)

    def test_arrival_order_is_preserved(self):
        self.bus.publish("order.created", {"id": "o1"})
        self.bus.publish("order.paid", {"id": "o1"})
        self.bus.publish("order.cancelled", {"id": "o1"})
        self.assertEqual(
            [record["topic"] for record in self.log.records()],
            ["order.created", "order.paid", "order.cancelled"],
        )

    def test_records_carry_the_payload(self):
        self.bus.publish("order.created", {"id": "o1", "total": 10})
        record = self.log.records()[0]
        self.assertEqual(record["payload"]["id"], "o1")

    def test_records_are_snapshots_not_live_references(self):
        payload = {"id": "o1", "state": "new"}
        self.bus.publish("order.created", payload)
        payload["state"] = "mutated"
        self.assertEqual(self.log.records()[0]["payload"]["state"], "new")

    def test_returned_list_cannot_corrupt_the_log(self):
        self.bus.publish("order.created", {"id": "o1"})
        self.log.records().clear()
        self.assertEqual(len(self.log.records()), 1)


class ResilienceTest(unittest.TestCase):
    """The bus drops a handler that raises, so the handler must not raise."""

    def setUp(self):
        self.bus = EventBus()
        self.log = AuditLog(self.bus)

    def test_malformed_payload_does_not_kill_the_subscription(self):
        self.bus.publish("order.created", None)
        self.assertEqual(self.bus.subscription_count("order.created"), 1)

    def test_recording_continues_after_a_malformed_event(self):
        self.bus.publish("order.created", None)
        self.bus.publish("order.created", {"id": "o2"})
        self.assertTrue(
            any(record["payload"] and record["payload"].get("id") == "o2"
                for record in self.log.records())
        )

    def test_publish_reports_the_handler_as_delivered(self):
        self.assertEqual(self.bus.publish("order.created", {"id": "o1"}), 1)


class ApiRespectTest(unittest.TestCase):
    """The bus must be used through its public API only.

    This checks private *access on the bus object*, not the mere appearance of
    a private name: an AuditLog keeping its own ``self._tokens`` is correct.
    """

    def test_no_private_attribute_is_read_from_the_bus(self):
        import ast
        import inspect

        import src.audit as module

        tree = ast.parse(inspect.getsource(module))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or not node.attr.startswith("_"):
                continue
            target = node.value
            name = None
            if isinstance(target, ast.Name):
                name = target.id
            elif isinstance(target, ast.Attribute):
                name = target.attr
            if name in ("bus", "_bus", "event_bus"):
                offenders.append(f"{name}.{node.attr}")
        self.assertEqual(offenders, [], f"use the bus's public API only: {offenders}")

    def test_unsubscribe_is_called_through_the_public_api(self):
        import inspect

        import src.audit as module

        self.assertIn("unsubscribe", inspect.getsource(module))


if __name__ == "__main__":
    unittest.main()
