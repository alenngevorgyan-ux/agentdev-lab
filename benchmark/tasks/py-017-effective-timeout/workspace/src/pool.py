"""Connection pooling."""

from .settings import POOL_IDLE_TIMEOUT_SECONDS


class ConnectionPool:
    def __init__(self, idle_timeout=POOL_IDLE_TIMEOUT_SECONDS):
        self.idle_timeout = idle_timeout

    def acquire(self):
        return {"idle_timeout": self.idle_timeout}
