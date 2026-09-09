"""Ports: the interfaces the domain requires of the outside world."""

from abc import ABC, abstractmethod


class OrderRepositoryPort(ABC):
    """Reads and writes orders."""

    @abstractmethod
    def get(self, order_id):
        """Return the order, or None when it does not exist."""

    @abstractmethod
    def save(self, order):
        """Persist an order."""
