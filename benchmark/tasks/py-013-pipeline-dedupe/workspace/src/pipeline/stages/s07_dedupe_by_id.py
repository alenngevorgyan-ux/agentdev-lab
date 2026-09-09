"""Drop duplicate records sharing an id, keeping the first."""

def run(records, context):
    seen = set()
    out = []
    for record in records:
        identifier = record.get("id")
        if identifier in seen:
            continue
        seen.add(identifier)
        out.append(record)
    return out
