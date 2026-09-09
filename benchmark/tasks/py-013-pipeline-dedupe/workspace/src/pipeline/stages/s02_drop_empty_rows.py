"""Remove records that carry no field at all."""

def run(records, context):
    return [record for record in records if any(value not in (None, "") for value in record.values())]
