# Task format

A task lives in one directory under `benchmark/tasks/`:

```
benchmark/tasks/<task-id>/
    task.json      the specification
    workspace/     the tree handed to the agent, verbatim
    acceptance/    hidden tests, overlaid by the evaluator AFTER the agent exits
    solution/      reference overlay applied by the oracle control
```

The directory name **must** equal `task.json`'s `id`.

Only `workspace/` is ever copied into the agent's environment. `acceptance/` and
`solution/` stay in the task directory, which the isolation boundary denies —
the agent cannot read them, and cannot even learn whether they exist.

## `task.json`

```json
{
  "id": "py-015-pagination",
  "title": "Fix off-by-one and boundary errors in pagination",
  "language": "python",
  "category": "bugfix_local",
  "difficulty": "medium",
  "prompt": "What the agent is told. Precise, self-contained, no hints at the fix.",
  "acceptance_criteria": [
    "Pages are 1-indexed and each holds at most per_page items.",
    "A page past the end returns an empty list, has_next False and has_prev True."
  ],
  "expected_files": ["src/pagination.py"],
  "protected_paths": ["tests"],
  "tags": ["off-by-one", "boundaries"],
  "verify": {
    "command": ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"],
    "timeout_sec": 120
  }
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `id` | yes | Must match the directory name. |
| `title` | yes | One line. |
| `language` | yes | Free-form; `python` today. |
| `category` | yes | One of the twelve capability categories (below). |
| `difficulty` | yes | `easy`, `medium`, `hard`. |
| `prompt` | yes | Exactly what the agent receives, verbatim. |
| `acceptance_criteria` | yes | The specification, in the agent's prompt. States *what must be true*, never how to do it. |
| `protected_paths` | yes | Relative paths inside `workspace/` the agent may not change. Non-empty; must exist. |
| `verify` | yes | `command` (argv) and `timeout_sec` (1..3600), run with the workspace as cwd. |
| `expected_files` | no | Files a correct fix is expected to touch. Feeds the wrong-location and over-editing failure signals; never shown to the agent. |
| `tags` | no | Free-form labels. |
| `workspace_dir`, `solution_dir`, `acceptance_dir` | no | Default to `workspace`, `solution`, `acceptance`. |

Validation is strict: an unknown key is an error. A misspelled `protected_paths`
would otherwise silently disable tamper detection.

`python3` and `python` in a verification command are rewritten to the exact
interpreter running the harness, so the recorded runtime describes what really
ran. The command should produce **verbose** output (`-v`): per-test outcomes are
what make partial credit and regression detection possible.

## Categories

`exploration`, `bugfix_local`, `bugfix_multifile`, `feature`, `refactor`,
`test_generation`, `requirements_following`, `ambiguous_requirements`,
`regression_avoidance`, `dependency_api`, `long_context_navigation`,
`architectural_constraints`.

## The workspace

- Self-contained; runs with the standard library only.
- Must **fail** verification as shipped — `selfcheck` rejects a task the `noop`
  control passes, because it measures nothing.
- **Deterministic.** Inject clocks and seeds rather than reading real time.
  `selfcheck --deterministic` evaluates each pristine fixture twice and fails the
  task if the two verdicts disagree: a flaky task manufactures phantom
  regressions that look like a capability difference.
- No file at the workspace root may be named after a standard-library module.
  Such a file is treated as an attempt to hijack the evaluator.

## Hidden acceptance tests

`acceptance/` is an overlay copied onto the workspace **after** the agent's turn,
using the same relative paths. Its files may not overwrite a file already in the
workspace — silently replacing an assertion the agent was shown would be a
different experiment, and the loader rejects it.

Hidden tests are written against the task's written specification, and the
specification is fixed before the tests. They exist so an agent cannot fit its
work to the exact assertions it will be graded on.

## The reference solution

`solution/` is an overlay copied over the sandbox: same relative paths, correct
contents. It must make verification pass on its own — `selfcheck` asserts this.
It is a harness control, and is **never** exposed to an agent under test.

## Adding a task

```bash
mkdir -p benchmark/tasks/py-019-my-task/{workspace,acceptance,solution}
# write task.json, the fixture, the hidden tests and the reference solution
python3 -m benchmark selfcheck --deterministic
```

Commit only once `selfcheck` is clean. Once a task has been measured, prefer a
new task id over editing it: an edit changes the fingerprint, makes results
either side non-comparable, and — if the task is named in a frozen experiment
manifest — is refused outright by the runner as fixture drift.

## A note on who writes these

The tasks and the harness currently share an author, which is a real bias risk
that no format rule removes. See
[comparison-protocol.md](comparison-protocol.md) section 9.
