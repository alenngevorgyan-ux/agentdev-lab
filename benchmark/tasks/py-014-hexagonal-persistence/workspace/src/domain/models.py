"""Domain entities."""

from dataclasses import dataclass, field, replace

VALID_STATES = ("draft", "placed", "completed", "cancelled")


@dataclass(frozen=True)
class Order:
    id: str
    state: str = "draft"
    total: float = 0.0
    archived: bool = False
    tags: tuple = field(default_factory=tuple)

    def with_state(self, state):
        if state not in VALID_STATES:
            raise ValueError(f"unknown state: {state}")
        return replace(self, state=state)

    def archive(self):
        """Return an archived copy of this order."""
        return replace(self, archived=True)
