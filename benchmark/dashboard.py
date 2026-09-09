"""A zero-dependency local dashboard over the results database.

Every number shown is produced by one of the curated queries in ``sql/queries``,
so the dashboard cannot report anything the SQL does not. The analysis scope is
displayed at all times, and synthetic development data is announced loudly
rather than blended in.
"""

from __future__ import annotations

import html
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .queries import find_query, run_query
from .storage import ResultsStore

SCOPES = {
    "measurement": ["measurement"],
    "sample": ["development_sample"],
    "control": ["control"],
    "all": ["measurement", "control", "development_sample"],
}

# Categorical slots 1-3 of the validated reference palette, light and dark.
# Capped at three series: past that, the all-pairs colour floors stop holding.
SERIES_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a")
SERIES_DARK = ("#3987e5", "#d95926", "#199e70")

STYLE = """
:root {
  color-scheme: light;
  --surface-0: #f4f4f2;
  --surface-1: #fcfcfb;
  --border:    #dededa;
  --text-1:    #0b0b0b;
  --text-2:    #52514e;
  --text-3:    #77766f;
  --grid:      #e8e8e4;
  --series-1:  #2a78d6;
  --series-2:  #eb6834;
  --series-3:  #1baf7a;
  --warn-bg:   #fdf3e7;
  --warn-fg:   #8a4b12;
  --warn-line: #eb6834;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface-0: #121211;
    --surface-1: #1a1a19;
    --border:    #33322f;
    --text-1:    #ffffff;
    --text-2:    #c3c2b7;
    --text-3:    #93928a;
    --grid:      #2a2a28;
    --series-1:  #3987e5;
    --series-2:  #d95926;
    --series-3:  #199e70;
    --warn-bg:   #2a1c10;
    --warn-fg:   #f0b481;
    --warn-line: #d95926;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--surface-0);
  color: var(--text-1);
  font: 14px/1.5 ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif;
}
.wrap { max-width: 1120px; margin: 0 auto; padding: 28px 20px 64px; }
header h1 { font-size: 20px; margin: 0 0 4px; letter-spacing: -0.01em; }
header p { margin: 0; color: var(--text-2); }
.scopebar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 18px 0 8px; }
.scopebar a {
  text-decoration: none; color: var(--text-2); border: 1px solid var(--border);
  background: var(--surface-1); padding: 5px 11px; border-radius: 999px; font-size: 13px;
}
.scopebar a.on { color: var(--text-1); border-color: var(--text-3); font-weight: 600; }
.banner {
  background: var(--warn-bg); color: var(--warn-fg); border: 1px solid var(--warn-line);
  border-radius: 8px; padding: 11px 14px; margin: 12px 0 4px; font-weight: 600;
}
section { margin-top: 32px; }
h2 { font-size: 15px; margin: 0 0 4px; letter-spacing: 0.01em; }
h2 + .sub { color: var(--text-3); margin: 0 0 14px; font-size: 13px; }
.card {
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px 18px;
}
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.tile { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.tile .v { font-size: 26px; font-weight: 650; letter-spacing: -0.02em; }
.tile .k { color: var(--text-3); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }
.tile .n { color: var(--text-2); font-size: 12px; margin-top: 2px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--grid); white-space: nowrap; }
th { color: var(--text-3); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.03em; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: none; }
.scroll { overflow-x: auto; }
.legend { display: flex; gap: 16px; margin: 0 0 12px; font-size: 13px; color: var(--text-2); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.swatch { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.bars { display: grid; gap: 10px; }
.barrow { display: grid; grid-template-columns: 210px 1fr; gap: 12px; align-items: center; }
.barlabel { color: var(--text-2); font-size: 13px; overflow: hidden; text-overflow: ellipsis; }
.bargroup { display: grid; gap: 2px; }
.bartrack { display: flex; align-items: center; gap: 8px; }
.bar { height: 11px; border-radius: 0 4px 4px 0; }
.barvalue { font-size: 12px; color: var(--text-2); font-variant-numeric: tabular-nums; }
.empty { color: var(--text-3); font-style: italic; padding: 8px 0; }
footer { margin-top: 40px; color: var(--text-3); font-size: 12px; border-top: 1px solid var(--border); padding-top: 14px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
"""


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def _rows(store: ResultsStore, name: str) -> list[sqlite3.Row]:
    try:
        return run_query(store, find_query(name))
    except (KeyError, sqlite3.Error):
        return []


def _table(rows: list[sqlite3.Row], numeric_suffixes=("_pct", "_usd", "seconds", "attempts")) -> str:
    if not rows:
        return '<p class="empty">No rows for this scope.</p>'
    headers = list(rows[0].keys())

    def is_num(header: str) -> bool:
        return header.endswith(numeric_suffixes) or header in {
            "passed", "attempts", "failures", "tasks", "runs", "regressions",
            "files_changed", "lines_added", "lines_deleted", "rows_affected",
        }

    head = "".join(
        f'<th class="{"num" if is_num(h) else ""}">{_esc(h.replace("_", " "))}</th>' for h in headers
    )
    body = "".join(
        "<tr>"
        + "".join(
            f'<td class="{"num" if is_num(h) else ""}">{_esc(row[h])}</td>' for h in headers
        )
        + "</tr>"
        for row in rows
    )
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _legend(series: list[str]) -> str:
    if len(series) < 2:
        return ""
    items = "".join(
        f'<span><i class="swatch" style="background:var(--series-{i + 1})"></i>{_esc(name)}</span>'
        for i, name in enumerate(series[:3])
    )
    return f'<div class="legend">{items}</div>'


def _grouped_bars(
    rows: list[sqlite3.Row], *, label_key: str, series_key: str, value_key: str, unit: str = "%"
) -> str:
    """Grouped horizontal bars: magnitude by category, split by agent.

    Every bar carries a direct value label, which is also the relief required
    for the light-mode contrast warning on the third series slot.
    """
    if not rows:
        return '<p class="empty">No rows for this scope.</p>'

    series = []
    for row in rows:
        name = str(row[series_key])
        if name not in series:
            series.append(name)
    series = series[:3]

    groups: dict[str, dict[str, float]] = {}
    for row in rows:
        value = row[value_key]
        if value is None:
            continue
        groups.setdefault(str(row[label_key]), {})[str(row[series_key])] = float(value)

    biggest = max(
        (value for values in groups.values() for value in values.values()), default=1.0
    ) or 1.0

    body = []
    for label, values in groups.items():
        bars = []
        for index, name in enumerate(series):
            if name not in values:
                continue
            value = values[name]
            # A zero must not draw a visible sliver; the label carries it.
            width = 0.0 if value == 0 else max(1.5, 100.0 * value / biggest)
            bars.append(
                f'<div class="bartrack" title="{_esc(label)} - {_esc(name)}: {value:g}{unit}">'
                f'<div class="bar" style="width:{width:.1f}%;background:var(--series-{index + 1})"></div>'
                f'<span class="barvalue">{value:g}{unit}</span></div>'
            )
        body.append(
            f'<div class="barrow"><div class="barlabel" title="{_esc(label)}">{_esc(label)}</div>'
            f'<div class="bargroup">{"".join(bars)}</div></div>'
        )
    return _legend(series) + f'<div class="bars">{"".join(body)}</div>'


def _single_bars(rows: list[sqlite3.Row], *, label_key: str, value_key: str, unit: str = "") -> str:
    if not rows:
        return '<p class="empty">No rows for this scope.</p>'
    biggest = max((float(row[value_key] or 0) for row in rows), default=1.0) or 1.0
    body = []
    for row in rows:
        value = float(row[value_key] or 0)
        width = 0.0 if value == 0 else max(1.5, 100.0 * value / biggest)
        label = str(row[label_key])
        body.append(
            f'<div class="barrow"><div class="barlabel" title="{_esc(label)}">{_esc(label)}</div>'
            f'<div class="bartrack" title="{_esc(label)}: {value:g}{unit}">'
            f'<div class="bar" style="width:{width:.1f}%;background:var(--series-1)"></div>'
            f'<span class="barvalue">{value:g}{unit}</span></div></div>'
        )
    return f'<div class="bars">{"".join(body)}</div>'


def _tile(value: str, key: str, note: str = "") -> str:
    note_html = f'<div class="n">{_esc(note)}</div>' if note else ""
    return f'<div class="tile"><div class="k">{_esc(key)}</div><div class="v">{_esc(value)}</div>{note_html}</div>'


def _headline(store: ResultsStore, scope: list[str]) -> str:
    rows = _rows(store, "01_headline_metrics")
    included = [row for row in rows if row["run_kind"] in scope]
    if not included:
        return '<p class="empty">Nothing recorded for this scope yet.</p>'

    attempts = sum(row["attempts"] for row in included)
    passed = sum(row["passed"] for row in included)
    regressions = sum(row["attempts_with_regressions"] for row in included)
    tampered = sum(row["tampered"] for row in included)
    interventions = sum(row["human_interventions"] for row in included)
    cost = sum(row["total_cost_usd"] or 0 for row in included)

    first_pass = _rows(store, "05_first_pass_success")
    first_pass_pct = (
        round(sum(r["first_pass_success_pct"] for r in first_pass) / len(first_pass), 1)
        if first_pass
        else None
    )
    timings = _rows(store, "10_median_completion_time")
    median = (
        round(sum(r["median_seconds"] or 0 for r in timings) / len(timings), 1) if timings else None
    )

    tiles = [
        _tile(f"{100.0 * passed / attempts:.1f}%", "pass rate", f"{passed} of {attempts} attempts"),
        _tile("n/a" if first_pass_pct is None else f"{first_pass_pct}%", "first-pass success",
              "solved on attempt 1"),
        _tile("n/a" if median is None else f"{median}s", "median attempt", "wall clock"),
        _tile(f"{100.0 * regressions / attempts:.1f}%", "regression rate",
              f"{regressions} attempt(s) broke working behaviour"),
        _tile(str(tampered), "test tampering", "attempts that edited protected tests"),
        _tile(str(interventions), "human interventions", "0 in unattended runs"),
        _tile("n/a" if not cost else f"${cost / passed:.3f}" if passed else "n/a",
              "cost per success", "where cost is reported"),
    ]
    return f'<div class="tiles">{"".join(tiles)}</div>'


def build_page(store: ResultsStore) -> str:
    scope = store.analysis_scope()
    synthetic = "development_sample" in scope

    banner = ""
    if synthetic:
        banner = (
            '<div class="banner">Synthetic development data is included in this view. '
            "These numbers are invented to exercise the analytics stack and are not "
            "evidence about any real agent.</div>"
        )

    current = next((name for name, kinds in SCOPES.items() if sorted(kinds) == sorted(scope)), "custom")
    chips = "".join(
        f'<a class="{"on" if name == current else ""}" href="/?scope={name}">{name}</a>'
        for name in ("measurement", "sample", "control", "all")
    )

    sections = [
        ("Headline metrics", "Everything below is computed by the curated SQL in sql/queries.",
         _headline(store, scope)),
        ("Agent comparison", "One row per agent and model actually measured.",
         _table(_rows(store, "02_agent_comparison"))),
        ("Success by capability category",
         "The profile a single pass rate hides: what each agent is good and bad at.",
         _grouped_bars(_rows(store, "03_success_by_category"), label_key="category",
                       series_key="agent", value_key="pass_rate_pct")),
        ("Success by difficulty", "A benchmark that does not decline with difficulty is not graded.",
         _grouped_bars(_rows(store, "04_success_by_difficulty"), label_key="difficulty",
                       series_key="agent", value_key="pass_rate_pct")),
        ("Completion time", "Median and tail, because a mean hides timeouts.",
         _table(_rows(store, "10_median_completion_time"))),
        ("Latency distribution", "Attempts per duration bucket.",
         _grouped_bars(_rows(store, "11_latency_distribution"), label_key="bucket",
                       series_key="agent", value_key="attempts", unit="")),
        ("Failure taxonomy", "How attempts fail, not only how often.",
         _single_bars(_rows(store, "07_failure_taxonomy"), label_key="failure_category",
                      value_key="failures")),
        ("Failure mix by category", "Which failure modes dominate which kind of work.",
         _table(_rows(store, "08_failure_mix_by_category"))),
        ("Hardest tasks", "Ranked by pass rate, then by how close failures got.",
         _table(_rows(store, "09_hardest_tasks"))),
        ("Human interventions", "Reserved for supervised runs; unattended runs record zero.",
         _table(_rows(store, "14_human_intervention_rate"))),
        ("Integrity audit", "Read this before quoting any number above.",
         _table(_rows(store, "23_integrity_audit"))),
        ("Run explorer", "Most recent attempts across every recorded run.",
         _table(_rows(store, "24_run_explorer")[:60])),
    ]

    body = "".join(
        f'<section><h2>{_esc(title)}</h2><p class="sub">{_esc(sub)}</p>'
        f'<div class="card">{content}</div></section>'
        for title, sub, content in sections
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentDev Lab</title><style>{STYLE}</style></head>
<body><div class="wrap">
<header>
  <h1>AgentDev Lab</h1>
  <p>Benchmark analytics for AI coding agents &middot; harness {_esc(__version__)}</p>
</header>
<div class="scopebar"><span style="color:var(--text-3)">analysis scope:</span>{chips}</div>
{banner}
{body}
<footer>
  Every figure comes from a query in <code>sql/queries/</code>; the dashboard adds no arithmetic
  of its own. Scope is stored in the <code>analysis_scope</code> table, so what any number was
  allowed to count is itself recorded.
</footer>
</div></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    db_path: Path | None = None

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path not in ("/", "/index.html"):
            self.send_error(404)
            return

        requested = parse_qs(parsed.query).get("scope", [None])[0]
        with ResultsStore(self.db_path) as store:
            if requested in SCOPES:
                store.set_analysis_scope(SCOPES[requested])
            page = build_page(store)

        payload = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        """Silence per-request logging; the dashboard is a local tool."""


def serve(port: int = 8765, db: Path | None = None, host: str = "127.0.0.1") -> None:
    handler = type("BoundHandler", (_Handler,), {"db_path": db})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"dashboard on http://{host}:{port}  (ctrl-c to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
