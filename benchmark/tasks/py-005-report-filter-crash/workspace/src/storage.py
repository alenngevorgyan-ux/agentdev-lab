"""In-memory persistence used by the reporting stack."""

from .models import sample_sales


class SalesRepository:
    def __init__(self, sales=None):
        self._sales = list(sales) if sales is not None else sample_sales()

    def all(self):
        return list(self._sales)

    def by_region(self, region):
        return [sale for sale in self._sales if sale.region == region]
