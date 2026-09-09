"""Normalise the email field to lowercase."""

def run(records, context):
    for record in records:
        if record.get("email"):
            record["email"] = record["email"].lower()
    return records
