"""The one task prompt every agent under test receives.

Comparing two agents on differently-worded instructions measures the wording as
much as the agents. There is therefore exactly one prompt builder, shared by
every adapter, and a parity test asserts that adapters produce byte-identical
text for the same task.

Anything agent-specific -- how the prompt is delivered, which flags the CLI
takes -- belongs in the adapter. The instructions themselves do not.
"""

from __future__ import annotations

from ..tasks import Task

PROMPT_TEMPLATE = """\
You are working inside an isolated benchmark workspace. Your working directory
already contains the project.

Task: {title}

{prompt}

Acceptance criteria:
{criteria}

Rules:
- Modify only the source files needed to complete the task.
- Do not edit, delete, weaken, or skip any test file. The following paths are
  protected and any change to them invalidates the attempt: {protected}
- Do not add third-party dependencies; the standard library only.
- Your work is graded by a test suite you cannot see, run after you exit.
- When you are done, stop. Do not ask questions.
"""


def build_task_prompt(task: Task) -> str:
    """Render the instructions handed to any agent for ``task``."""
    criteria = "\n".join(f"- {item}" for item in task.acceptance_criteria)
    return PROMPT_TEMPLATE.format(
        title=task.title,
        prompt=task.prompt.strip(),
        criteria=criteria,
        protected=", ".join(task.protected_paths),
    )
