# Failure taxonomy

A pass rate says how often an agent failed. It cannot say *how*. "Claude Code
fails 40% of refactoring tasks" is a number; "two thirds of those failures are
under-editing and one third is hallucinated APIs" is a finding you can act on.

The taxonomy is stored in the `failure_categories` table so analyses join
definitions rather than hardcode strings.

## The categories

| Category | The agent… | Typical evidence |
| --- | --- | --- |
| `none` | passed | — |
| `misunderstood_requirement` | solved a different problem, competently | working code, wrong behaviour |
| `incomplete_implementation` | did part of the job | some acceptance tests still fail |
| `wrong_location` | edited the wrong place | expected files untouched, others changed |
| `regression` | broke what already worked | a baseline-passing test now fails |
| `hallucinated_api` | called something that does not exist | `ImportError`, `AttributeError`, `NameError` |
| `dependency_reasoning` | missed how a change propagates | callers left inconsistent |
| `context_loss` | forgot an earlier constraint or its own edit | contradictory edits within one attempt |
| `test_gaming` | went after the tests instead of the code | protected paths changed |
| `over_editing` | rewrote far more than needed | diff several times the expected footprint |
| `under_editing` | barely engaged | ≤ 3 lines changed |
| `timeout` | ran out of time | agent or acceptance suite timed out |
| `environment_failure` | could not run at all | missing credentials, tooling, a crash |
| `unclassified` | — | evidence insufficient; needs human review |

## How labels are assigned

`benchmark/failures.py` classifies from recorded evidence only — status, test
counts, regressions, diff statistics, and captured output. It is deliberately
**conservative**: where evidence cannot distinguish two categories (notably
"misunderstood the requirement" from "did not finish it"), it returns
`unclassified` rather than guessing.

Precedence runs from the mechanically certain to the merely suggestive:

```
passed -> none
tampered -> test_gaming
timeout -> timeout
agent/harness error, or an environment marker in the output -> environment_failure
regressions > 0 -> regression          (a distinct product harm, so it outranks "some tests fail")
import/attribute markers -> hallucinated_api
<= 3 lines changed -> under_editing
expected files untouched while others changed -> wrong_location
diff >= 3x the expected footprint -> over_editing
some tests passing -> incomplete_implementation
otherwise -> unclassified
```

**Every label records its source.** Classifier output is `classification_source =
'auto'`; a human relabel must set `'human'`, and the database rejects a relabel
that does not. A hand-coded study is therefore never diluted by machine guesses:

```sql
SELECT failure_category, COUNT(*) FROM attempts
WHERE classification_source = 'human' GROUP BY 1;
```

Relabel through `ResultsStore.relabel_failure(attempt_id, category, note)`.

## Refining the taxonomy

The categories were chosen against the eighteen tasks in the suite and should be
revised as real failures arrive. Two rules govern a change:

1. A category must be **distinguishable from evidence** or explicitly reserved
   for human review. A label nobody can apply consistently is noise.
2. Adding a category does not retroactively relabel stored attempts. Rows are
   append-only; a re-classification is a new pass over the data, recorded as
   `human`.

`unclassified` staying large is itself a finding: it means the evidence the
harness collects is not yet rich enough, and points at what to capture next.
