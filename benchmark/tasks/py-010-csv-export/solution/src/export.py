"""Report export to CSV.

The request said only "as CSV so they can open it in Excel". Choices made
where the ticket was silent, and why:

* **Header row** -- included. Spreadsheet users expect column names, and the
  ticket names Excel explicitly.
* **Column order** -- the key order of the first row, which is the order the
  report itself defines. Sorting alphabetically would silently reorder a
  report someone designed.
* **Row order** -- preserved exactly as given (newest first). Re-sorting would
  discard an ordering decision made upstream.
* **Quoting** -- the standard library's csv module with default quoting, which
  is RFC 4180 compliant: only fields needing quotes get them.
* **Line endings** -- ``\\r\\n``, which is what RFC 4180 specifies and what
  Excel handles most predictably across platforms.
* **Empty input** -- still emits a header, so a downstream parser sees a
  well-formed empty table rather than an empty file.
"""

import csv
import io

#: Column names used when the report has no rows to describe its own shape.
DEFAULT_COLUMNS = ("date", "customer", "amount", "note")


def export_csv(rows):
    """Render report rows as CSV text."""
    rows = list(rows)
    columns = list(rows[0].keys()) if rows else list(DEFAULT_COLUMNS)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()
