# Task format

A task lives in one directory under `benchmark/tasks/`:

```
benchmark/tasks/<task-id>/
    task.json      the specification
    workspace/     the tree handed to the agent, verbatim
    solution/      reference overlay applied by the oracle control
```

The directory name **must** equal `task.json`'s `id`.

## `task.json`

```json
{
  "id": "py-001-interval-merge",
  "title": "Fix boundary handling in interval merging",
  "language": "python",
  "category": "bugfix",
  "difficulty": "easy",
  "prompt": "What the agent is told. Precise, self-contained, no hints at the fix.",
  "protected_paths": ["tests"],
  "tags": ["algorithms", "edge-cases"],
  "verify": {
    "command": ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"],
    "timeout_sec": 120
  }
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `id` | yes | Must match the directory name. |
| `title` | yes | One line. |
| `language` | yes | Free-form; `python` today. |
| `category` | yes | `bugfix`, `feature`, `refactor`, `performance`. |
| `difficulty` | yes | `easy`, `medium`, `hard`. |
| `prompt` | yes | Exactly what the agent receives. |
| `protected_paths` | yes | Relative paths inside `workspace/` that the agent may not change. Must be non-empty and must exist. |
| `verify` | yes | `command` (argv list) and `timeout_sec` (1..3600). Run with `workspace/` as cwd. |
| `tags` | no | Free-form labels. |
| `workspace_dir` | no | Defaults to `workspace`. |
| `solution_dir` | no | Defaults to `solution`. |

Validation is strict: an unknown key is an error. A misspelled
`protected_paths` would otherwise silently disable tamper detection.

`python3` and `python` in a verification command are rewritten to the exact
interpreter running the harness, so the recorded runtime describes what really
ran.

## The workspace

- Self-contained; runs with the standard library only.
- Must **fail** verification as shipped. A task that already passes measures
  nothing, and `selfcheck` rejects it.
- Deterministic. Inject clocks and seeds rather than reading real time.
- Tests pin *behaviour*, including the edge cases the prompt describes, and
  should be hard to satisfy by special-casing.

## The reference solution

`solution/` is an overlay copied over the sandbox: same relative paths, correct
contents. It must make verification pass on its own — `selfcheck` asserts this.
It is a harness control, never a hint given to an agent.

## Adding a task

```bash
mkdir -p benchmark/tasks/py-004-my-task/{workspace,solution}
# write task.json, the fixture, and the reference solution
python3 -m benchmark selfcheck
```

Commit only once `selfcheck` is clean. Once a task has been measured, prefer a
new task id over editing it: an edit changes the fingerprint and makes results
either side of it non-comparable.
