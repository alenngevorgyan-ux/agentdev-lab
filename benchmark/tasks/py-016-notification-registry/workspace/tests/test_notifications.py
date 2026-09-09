import unittest

from src.errors import UnknownChannel
from src.notifications import send
from src.renderer import render

CONTEXT = {"name": "Ada", "message": "Your order shipped"}


class SendTest(unittest.TestCase):
    def test_email(self):
        self.assertEqual(send("email", "a@b.c", "hi")["transport"], "smtp")

    def test_sms_is_truncated(self):
        self.assertEqual(len(send("sms", "+1", "x" * 500)["body"]), 160)

    def test_push(self):
        self.assertEqual(send("push", "device", "hi")["transport"], "fcm")

    def test_unknown_channel(self):
        with self.assertRaises(UnknownChannel):
            send("carrier-pigeon", "nest", "hi")


class RenderTest(unittest.TestCase):
    def test_email_template(self):
        self.assertTrue(render("email", CONTEXT).startswith("Dear Ada,"))

    def test_sms_template(self):
        self.assertEqual(render("sms", CONTEXT), "Ada: Your order shipped")

    def test_push_template(self):
        self.assertEqual(render("push", CONTEXT), "Your order shipped")

    def test_unknown_channel(self):
        with self.assertRaises(UnknownChannel):
            render("carrier-pigeon", CONTEXT)


if __name__ == "__main__":
    unittest.main()
