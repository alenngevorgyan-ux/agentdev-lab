"""In-memory adapter for the archive port."""

from src.domain.ports import ArchivePort


class InMemoryArchive(ArchivePort):
    def __init__(self):
        self._archived = {}

    def store(self, order):
        self._archived[order.id] = order

    def get(self, order_id):
        return self._archived.get(order_id)

    def archived(self):
        return list(self._archived.values())
