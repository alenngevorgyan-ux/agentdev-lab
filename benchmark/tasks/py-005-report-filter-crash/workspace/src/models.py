"""Domain records used across the reporting stack."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Sale:
    id: str
    category: str
    region: str
    amount: float
    currency: str = "EUR"


def sample_sales():
    """A small deterministic dataset used by tests and the demo report."""
    return [
        Sale("s1", "hardware", "eu", 120.0),
        Sale("s2", "hardware", "us", 80.0),
        Sale("s3", "services", "eu", 200.0),
        Sale("s4", "training", "apac", 100.0),
    ]
