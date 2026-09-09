# Dashboard

```bash
python3 -m benchmark dashboard                  # http://127.0.0.1:8765
python3 -m benchmark dashboard --scope sample   # include synthetic data
python3 -m benchmark dashboard --render out.html
```

Standard library only: `http.server` plus one generated HTML page. No build
step, no framework, no CDN.

## What it shows

| Section | Source query |
| --- | --- |
| Headline metrics (pass rate, first-pass, median attempt, regression rate, tampering, interventions, cost per success) | 01, 05, 10 |
| Agent comparison | 02 |
| Success by capability category | 03 |
| Success by difficulty | 04 |
| Completion time (median, p25, p90, tail) | 10 |
| Latency distribution | 11 |
| Failure taxonomy | 07 |
| Failure mix by category | 08 |
| Hardest tasks | 09 |
| Human interventions | 14 |
| Integrity audit | 23 |
| Run explorer | 24 |

**The dashboard performs no arithmetic of its own.** Every figure comes from a
query in `sql/queries/`, so the page cannot report something the SQL does not.

## Scope is always visible

The scope selector maps to the `analysis_scope` table. When synthetic rows are
included the page carries a banner saying so, in the same words as the CLI:
these numbers are not evidence about any real agent.

## Design notes

- Charts are horizontal bars, because every quantity shown is a magnitude
  compared across a small set of named categories.
- Two series maximum (agent A against agent B), with a legend and a direct value
  label on every bar, so identity and value never depend on colour alone.
- The palette is categorical slots 1–3 of a validated reference palette, checked
  for colour-vision deficiency separation and contrast in **both** light and dark
  modes; dark mode is a selected set of steps, not an inverted light one.
- A zero draws no bar; its label carries the value.
- Every chart section is accompanied by the underlying table, which is also the
  accessible view.
