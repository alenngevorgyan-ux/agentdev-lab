"""An existing use case, shown as the pattern to follow."""

from src.domain.errors import DomainError


class CompleteOrderService:
    """Marks a placed order as completed."""

    def __init__(self, repository):
        self._repository = repository

    def complete(self, order_id):
        order = self._repository.get(order_id)
        if order is None:
            raise DomainError(f"unknown order: {order_id}")
        if order.state != "placed":
            raise DomainError(f"cannot complete an order in state {order.state!r}")
        completed = order.with_state("completed")
        self._repository.save(completed)
        return completed
