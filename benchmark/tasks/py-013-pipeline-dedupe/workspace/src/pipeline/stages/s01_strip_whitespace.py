"""Trim surrounding whitespace from every string field."""

def run(records, context):
    out = []
    for record in records:
        out.append({k: (v.strip() if isinstance(v, str) else v) for k, v in record.items()})
    return out
