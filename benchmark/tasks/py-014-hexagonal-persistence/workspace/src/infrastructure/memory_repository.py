"""In-memory adapter for the order repository port."""

from src.domain.ports import OrderRepositoryPort


class InMemoryOrderRepository(OrderRepositoryPort):
    def __init__(self, orders=()):
        self._orders = {order.id: order for order in orders}

    def get(self, order_id):
        return self._orders.get(order_id)

    def save(self, order):
        self._orders[order.id] = order

    def all(self):
        return list(self._orders.values())
