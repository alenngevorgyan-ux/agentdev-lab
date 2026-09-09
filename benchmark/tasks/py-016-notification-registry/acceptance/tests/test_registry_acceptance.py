"""Hidden acceptance tests for the registry refactor."""

import ast
import inspect
import unittest

from src.errors import UnknownChannel
from src.notifications import send
from src.renderer import render

CONTEXT = {"name": "Ada", "message": "Your order shipped"}


class RegistryApiTest(unittest.TestCase):
    def test_registry_exposes_the_api(self):
        from src.registry import available_channels, register_channel

        self.assertTrue(callable(register_channel))
        self.assertTrue(callable(available_channels))

    def test_builtin_channels_are_registered(self):
        from src.registry import available_channels

        self.assertEqual(set(available_channels()) >= {"email", "sms", "push"}, True)


class BehaviourPreservedTest(unittest.TestCase):
    def test_email_payload_unchanged(self):
        self.assertEqual(
            send("email", "a@b.c", "hi"),
            {"channel": "email", "to": "a@b.c", "body": "hi", "transport": "smtp"},
        )

    def test_sms_truncation_unchanged(self):
        self.assertEqual(send("sms", "+1", "y" * 200)["body"], "y" * 160)

    def test_push_payload_unchanged(self):
        self.assertEqual(send("push", "device", "hi")["transport"], "fcm")

    def test_email_template_unchanged(self):
        self.assertEqual(
            render("email", CONTEXT),
            "Dear Ada,\n\nYour order shipped\n\nRegards,\nThe team",
        )

    def test_sms_template_unchanged(self):
        self.assertEqual(render("sms", CONTEXT), "Ada: Your order shipped")


class ExtensibilityTest(unittest.TestCase):
    def setUp(self):
        from src.registry import register_channel

        register_channel(
            "webhook",
            lambda recipient, body: {"channel": "webhook", "to": recipient,
                                     "body": body, "transport": "https"},
            "[{name}] {message}",
        )

    def test_new_channel_can_send(self):
        self.assertEqual(send("webhook", "https://x", "hi")["transport"], "https")

    def test_new_channel_can_render(self):
        self.assertEqual(render("webhook", CONTEXT), "[Ada] Your order shipped")

    def test_new_channel_is_listed(self):
        from src.registry import available_channels

        self.assertIn("webhook", available_channels())


class UnknownChannelTest(unittest.TestCase):
    def test_send_rejects_unknown(self):
        with self.assertRaises(UnknownChannel):
            send("nope", "x", "y")

    def test_render_rejects_unknown(self):
        with self.assertRaises(UnknownChannel):
            render("nope", CONTEXT)


class StructureTest(unittest.TestCase):
    """The chain must be gone, not merely shortened."""

    def _branch_count(self, module):
        tree = ast.parse(inspect.getsource(module))
        return sum(1 for node in ast.walk(tree) if isinstance(node, ast.If))

    def test_notifications_has_no_dispatch_chain(self):
        import src.notifications as module

        self.assertLessEqual(self._branch_count(module), 1)

    def test_renderer_has_no_dispatch_chain(self):
        import src.renderer as module

        self.assertLessEqual(self._branch_count(module), 1)

    def test_channel_names_are_not_hardcoded_in_the_renderer(self):
        import src.renderer as module

        source = inspect.getsource(module)
        for name in ("email", "sms", "push"):
            self.assertNotIn(f'"{name}"', source)


if __name__ == "__main__":
    unittest.main()
