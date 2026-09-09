"""Archiving use case."""

from src.domain.errors import DomainError


class ArchiveOrderService:
    """Archives a completed order through the archive port.

    Both collaborators are ports, injected by the composition root; this layer
    never learns which adapter it is talking to.
    """

    def __init__(self, repository, archive):
        self._repository = repository
        self._archive = archive

    def archive_order(self, order_id):
        order = self._repository.get(order_id)
        if order is None:
            raise DomainError(f"unknown order: {order_id}")
        if order.state != "completed":
            raise DomainError(f"cannot archive an order in state {order.state!r}")

        archived = order.archive()
        self._archive.store(archived)
        self._repository.save(archived)
        return archived
