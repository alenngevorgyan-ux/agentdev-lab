"""Low-level transport."""

from .pool import ConnectionPool

#: Fallback used only when the client passes nothing at all, which it never does.
FALLBACK_TIMEOUT_SECONDS = 5


class Transport:
    def __init__(self, timeout=FALLBACK_TIMEOUT_SECONDS, pool=None):
        self.timeout = timeout
        self.pool = pool or ConnectionPool()

    def request(self, method, url):
        return {"method": method, "url": url, "timeout": self.timeout}
