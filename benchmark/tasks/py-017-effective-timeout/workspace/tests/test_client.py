import unittest

from src.client import HttpClient


class ClientTest(unittest.TestCase):
    def test_explicit_timeout_wins(self):
        self.assertEqual(HttpClient(timeout=1).timeout, 1)

    def test_request_carries_the_timeout(self):
        self.assertEqual(HttpClient(timeout=2).get("http://x")["timeout"], 2)


if __name__ == "__main__":
    unittest.main()
