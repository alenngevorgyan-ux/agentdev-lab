"""Report rows consumed by the export layer."""


def build_rows():
    """Return the report as a list of ordered dicts, newest first."""
    return [
        {"date": "2026-03-01", "customer": "Acme, Inc.", "amount": "1200.00", "note": ""},
        {"date": "2026-02-27", "customer": 'Bob "The Builder" Ltd', "amount": "340.50",
         "note": "priority"},
        {"date": "2026-02-25", "customer": "Zeta\nHoldings", "amount": "75.25", "note": ""},
    ]
