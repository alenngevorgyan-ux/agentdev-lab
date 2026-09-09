"""Stamp the ingest source onto every record."""

def run(records, context):
    source = context.get("source", "nightly")
    for record in records:
        record.setdefault("source", source)
    return records
