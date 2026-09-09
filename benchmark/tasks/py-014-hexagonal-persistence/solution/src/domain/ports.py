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


class ArchivePort(ABC):
    """Long-term storage for completed orders."""

    @abstractmethod
    def store(self, order):
        """Place an archived order into long-term storage."""

    @abstractmethod
    def get(self, order_id):
        """Return an archived order, or None."""
