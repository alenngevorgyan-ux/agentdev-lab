"""Order records deterministically for downstream stages."""

def run(records, context):
    return sorted(records, key=lambda record: (record.get("account_key") or "", str(record.get("id"))))
