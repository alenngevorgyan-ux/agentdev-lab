import unittest

from src.audit import AuditLog
from src.eventbus import EventBus


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.log = AuditLog(self.bus)

    def test_records_a_created_event(self):
        self.bus.publish("order.created", {"id": "o1"})
        self.assertEqual(len(self.log.records()), 1)

    def test_ignores_unrelated_topics(self):
        self.bus.publish("user.registered", {"id": "u1"})
        self.assertEqual(self.log.records(), [])

    def test_detach_stops_recording(self):
        self.log.detach()
        self.bus.publish("order.created", {"id": "o1"})
        self.assertEqual(self.log.records(), [])


if __name__ == "__main__":
    unittest.main()
