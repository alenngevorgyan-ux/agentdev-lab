"""The HTTP client used across the service."""

from .settings import HTTP_TIMEOUT_SECONDS
from .transport import Transport

UNSET = object()


class HttpClient:
    """Args:
    timeout: seconds per request; None disables the timeout entirely.
    """

    def __init__(self, timeout=UNSET, transport=None):
        effective = HTTP_TIMEOUT_SECONDS if timeout is UNSET else timeout
        self.timeout = effective
        self._transport = transport or Transport(timeout=effective)

    def get(self, url):
        return self._transport.request("GET", url)
