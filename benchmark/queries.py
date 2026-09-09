"""Discovery and execution of the curated SQL analyses in ``sql/queries``.

Keeping the analyses as plain ``.sql`` files means a reviewer can read them
without reading any Python, and means the same text is what runs -- there is no
query builder that could quietly differ from the file on disk.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .config import QUERIES_DIR
from .storage import ResultsStore


@dataclass(frozen=True)
class Query:
    name: str
    path: Path
    sql: str

    @property
    def title(self) -> str:
        """The description on the query's first comment line."""
        first = self.sql.splitlines()[0].strip()
        if first.startswith("--"):
            body = first.lstrip("-").strip()
            return body.split("|", 1)[1].strip() if "|" in body else body
        return self.name


def load_queries(directory: Path | None = None) -> list[Query]:
    root = directory or QUERIES_DIR
    if not root.is_dir():
        return []
    return [
        Query(name=path.stem, path=path, sql=path.read_text(encoding="utf-8"))
        for path in sorted(root.glob("*.sql"))
    ]


def find_query(name: str, directory: Path | None = None) -> Query:
    """Resolve a query by full name or by its numeric prefix."""
    queries = load_queries(directory)
    for query in queries:
        if query.name == name or query.name.startswith(f"{name}_") or query.name[:2] == name:
            return query
    raise KeyError(f"unknown query {name!r}; available: {[q.name for q in queries]}")


def run_query(store: ResultsStore, query: Query) -> list[sqlite3.Row]:
    """Execute a query against the results database."""
    return store.query(query.sql)
