"""The layering rule, enforced on the import graph."""

import ast
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

FORBIDDEN = {
    "domain": ("src.application", "src.infrastructure"),
    "application": ("src.infrastructure",),
}


def imports_of(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


class LayeringTest(unittest.TestCase):
    def test_dependencies_point_inward(self):
        violations = []
        for layer, forbidden in FORBIDDEN.items():
            for path in (SRC / layer).rglob("*.py"):
                for imported in imports_of(path):
                    if imported.startswith(forbidden):
                        violations.append(f"{path.relative_to(SRC)} imports {imported}")
        self.assertEqual(violations, [], f"layering violations: {violations}")


class ExistingUseCaseTest(unittest.TestCase):
    def test_complete_moves_a_placed_order(self):
        from src.application.complete_service import CompleteOrderService
        from src.domain.models import Order
        from src.infrastructure.memory_repository import InMemoryOrderRepository

        repository = InMemoryOrderRepository([Order("o1", state="placed")])
        service = CompleteOrderService(repository)
        self.assertEqual(service.complete("o1").state, "completed")


if __name__ == "__main__":
    unittest.main()
