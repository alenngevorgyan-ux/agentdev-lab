# AgentDev Lab

A reproducible benchmark and research lab for evaluating AI coding agents.

The lab answers one question honestly: **given a real repository and a real
task, does an agent produce code that passes tests it was not allowed to
touch?** Everything here exists to make that number trustworthy rather than
flattering.

## Why another agent benchmark

Most agent evaluations are easy to fool, usually by accident:

- the agent edits or deletes the tests it is graded against;
- the task was already passing before the agent started;
- the reference solution is wrong, so nothing could ever pass;
- the fixture changed between runs, so two numbers describe two experiments;
- a result gets "corrected" after the fact.

AgentDev Lab closes each of those holes mechanically, not by convention. See
[docs/integrity.md](docs/integrity.md).

## Requirements

Python 3.11 or newer. **No third-party packages.** A benchmark that needs a
package index to run stops being reproducible the moment that index changes.

## Quick start

```bash
python3 -m benchmark list                      # registered tasks
python3 -m benchmark adapters                  # adapters and their versions
python3 -m benchmark selfcheck                 # validate the harness itself
python3 -m benchmark run --adapter oracle      # upper control: must score 100%
python3 -m benchmark run --adapter noop        # lower control: must score 0%
python3 -m benchmark report --leaderboard
```

Measuring a real agent:

```bash
python3 -m benchmark run --adapter claude-code --attempts 3
python3 -m benchmark verify-integrity
```

Results are appended to `results/agentdev.sqlite3` (override with `AGENTDEV_DB`).
The database is never committed; it is generated evidence, not source.

## How one attempt works

```
fresh sandbox  ->  digest protected paths  ->  agent's turn  ->  digest again
              ->  run the task's own verification command     ->  score  ->  append
```

The agent never reports its own success. The only evidence admitted is the exit
code of the task's verification command, plus the two digests taken around the
agent's turn. An attempt that modified a protected test path is recorded as
`tampered` and can never be a pass, no matter what the tests then said.

## Adapters

| Adapter | Role | Meaning |
| --- | --- | --- |
| `noop` | control | Changes nothing. A task it passes is a broken task. |
| `oracle` | control | Applies the reference solution. A task it fails is a broken task. |
| `claude-code` | agent under test | Drives the Claude Code CLI headlessly inside the sandbox. |

The two controls bound the scale. They are not competitors on it, and reports
label them as such.

## Repository layout

| Path | Contents |
| --- | --- |
| `benchmark/` | The harness: tasks, sandboxing, adapters, scoring, storage, CLI. |
| `benchmark/tasks/` | Task definitions: spec, fixture workspace, reference solution. |
| `sql/` | Results schema (`schema.sql`) and analysis queries. |
| `tests/` | The harness's own test suite. |
| `docs/` | Task format, adapter contract, integrity rules, methodology. |
| `tests.json` | The authoritative test commands. Never weakened. |
| `progress.md` | Running project log, updated at the end of every session. |
| `ARCHITECTURE.md` | Design and the reasoning behind it. |
| `CLAUDE.md` | Persistent context for Claude Code sessions. |

## Tests

The authoritative commands live in [`tests.json`](tests.json) and are run
verbatim:

```bash
python3 -m unittest discover -s tests -t . -v
python3 -m benchmark selfcheck
python3 -m benchmark verify-integrity
```

## License

Unreleased research code. All rights reserved.
