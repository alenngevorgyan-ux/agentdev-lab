# Isolation

The claim this document supports:

> The hidden acceptance tests were not hidden by prompt instruction. They were
> structurally unavailable to the evaluated agent.

A changed working directory is not a boundary. What follows is the mechanism
that makes the claim true, and the evidence that it holds.

## What the agent may reach

| Resource | Reachable during the agent turn? |
| --- | --- |
| Its own task workspace (read/write) | **yes** — this is the point |
| A private scratch and home directory | yes, empty, per attempt |
| System libraries and the interpreter | read-only |
| The agent CLI's own install prefix | read-only |
| Hidden acceptance tests (`acceptance/`) | no — not in the workspace, and the task directory is denied |
| Reference solution (`solution/`) | no |
| Task definition (`task.json`) | no |
| Harness source (`benchmark/`) | no |
| Results database | no |
| Any other attempt | no |
| Host home directory | no |
| Anything else on the filesystem | no |
| Network | only if the adapter declares it needs it; never during evaluation |

Denial is total: a denied path cannot even be stat-ed, so its *existence* does
not leak.

## Backends

| Backend | Status here | Boundary |
| --- | --- | --- |
| `docker` | implemented; **unavailable on the authoring machine** (CLI present, no daemon) | container; only the workspace is bind-mounted, all capabilities dropped, `no-new-privileges`, `--network none` unless requested |
| `seatbelt` | **active and used for every measurement in this repository** | macOS kernel policy, deny-by-default, via `sandbox-exec` |
| `none` | never automatic | no boundary; marks runs NON-PUBLISHABLE |

```bash
python3 -m benchmark isolation     # what works on this machine
```

`--isolation auto` picks the strongest active backend and **refuses to run** if
none can enforce anything. Running without a boundary requires `--isolation
none` by name, and every resulting run is recorded with `isolation_active = 0`
and `publishable = 0`, plus a banner on the console.

## Where the boundary sits in the protocol

```
                    ┌─ isolation boundary ─────────────┐
 fixture ──copy──▶  │  workspace  ◀── the agent's turn  │   network: as declared
                    └──────────────────────────────────┘
                              │ agent has exited
        host applies hidden acceptance tests to the workspace
                              │
                    ┌─ isolation boundary ─────────────┐
                    │  evaluation runs the acceptance   │   network: always denied
                    │  suite; the host reads the verdict│
                    └──────────────────────────────────┘
```

Two properties follow. The hidden tests are applied *between* the boundaries, so
they were never on a filesystem the agent could see. And the verdict is computed
after the agent process is gone, so it is the host's, never the agent's.

## The three deliberate holes

Every hole in a deny-by-default policy has to be justified.

| Hole | Why it exists | What it could leak |
| --- | --- | --- |
| Read on `/usr`, `/System`, `/Library`, `/usr/local` | the interpreter and the agent CLI must load | no benchmark data lives there |
| `file-read-metadata` on `/` and `/usr` | the interpreter resolves its own path before `main` | existence of *guessed* system paths; the home directory, `/tmp` and the checkout stay unstat-able |
| Read on the agent binary's install prefix | the agent must execute | CLI builds only — notably **not** the CLI's config or login file, which is why a credential must be passed explicitly |

## Credentials

Only the variables an adapter names are passed in, read from the host
environment at call time. They are never stored, never logged, and never
written to the database — captured output is redacted at the point of capture
(`benchmark/redaction.py`), and `verify-integrity` re-checks stored evidence for
credential-shaped values.

A consequence worth stating: a CLI authenticated by a login file in the home
directory **cannot** authenticate inside the boundary. That is not a bug to work
around — exposing the home directory would defeat the isolation. Supply an API
key instead.

## `bypassPermissions` and `--dangerously-bypass-approvals-and-sandbox`

Both agent adapters disable their CLI's own approval prompts. That is only
defensible because the process is externally confined — Codex's own help says
these flags are "intended solely for running in environments that are externally
sandboxed". The harness makes that structural rather than aspirational:
`Sandbox.exec` raises if no boundary is attached, so an agent turn cannot run
unconfined, and the flags can never act as a host-level permission bypass.

## The evidence

`benchmark/adapters/canary.py` is an adversarial adapter that behaves like a
hostile agent. From inside the boundary it attempts parent traversal, the
filesystem root, the host home directory, a file inside it, the hidden
acceptance directory and a specific hidden test, the reference solution
directory and file, the harness source, the repository listing, the task
definition, the results database, a *real* sibling attempt directory, an
existence probe on a hidden test, a search of the task registry, mutation of a
tracked benchmark file, and network egress.

```bash
python3 -m unittest tests.test_isolation -v
```

Every probe must be denied, and the tracked file must be byte-identical
afterwards. If any probe succeeds, the suite fails with `ISOLATION BREACH`.

## What this is not

Seatbelt is a filesystem and network policy, not a virtual machine: it bounds
neither CPU nor memory, and Apple has deprecated `sandbox-exec` (the backend
records the OS build so a behaviour change becomes visible). Docker is the
stronger backend and `auto` prefers it wherever a daemon exists.

The boundary protects the *benchmark* from the agent. It is not a containment
solution for genuinely untrusted code: the agent turn has network access because
it must reach its provider, and nothing here constrains what it sends.
