"""Hidden acceptance tests for order archiving and its layering."""

import ast
import inspect
import unittest
from pathlib import Path

from src.domain.errors import DomainError
from src.domain.models import Order

SRC = Path(__file__).resolve().parent.parent / "src"


def build(orders=()):
    from src.application.archive_service import ArchiveOrderService
    from src.infrastructure.memory_archive import InMemoryArchive
    from src.infrastructure.memory_repository import InMemoryOrderRepository

    repository = InMemoryOrderRepository(orders)
    archive = InMemoryArchive()
    return ArchiveOrderService(repository, archive), repository, archive


class BehaviourTest(unittest.TestCase):
    def test_completed_order_is_archived(self):
        service, _, archive = build([Order("o1", state="completed")])
        result = service.archive_order("o1")
        self.assertTrue(result.archived)
        self.assertEqual(len(archive.archived()), 1)

    def test_archived_order_is_persisted_through_the_port(self):
        service, _, archive = build([Order("o1", state="completed")])
        service.archive_order("o1")
        self.assertTrue(archive.get("o1").archived)

    def test_non_completed_order_is_refused(self):
        service, _, archive = build([Order("o1", state="placed")])
        with self.assertRaises(DomainError):
            service.archive_order("o1")
        self.assertEqual(archive.archived(), [])

    def test_draft_order_is_refused(self):
        service, _, _ = build([Order("o1", state="draft")])
        with self.assertRaises(DomainError):
            service.archive_order("o1")

    def test_unknown_order_is_refused(self):
        service, _, _ = build([])
        with self.assertRaises(DomainError):
            service.archive_order("missing")

    def test_repository_reflects_the_archived_state(self):
        service, repository, _ = build([Order("o1", state="completed")])
        service.archive_order("o1")
        self.assertTrue(repository.get("o1").archived)


class PortTest(unittest.TestCase):
    def test_archive_port_is_declared_in_the_domain(self):
        import src.domain.ports as ports

        names = [name for name in dir(ports) if "Archive" in name]
        self.assertTrue(names, "declare an archive port in src/domain/ports.py")

    def test_adapter_implements_the_port(self):
        import src.domain.ports as ports
        from src.infrastructure.memory_archive import InMemoryArchive

        port = next(getattr(ports, name) for name in dir(ports) if "Archive" in name)
        self.assertTrue(issubclass(InMemoryArchive, port))

    def test_service_does_not_construct_its_own_adapter(self):
        import src.application.archive_service as module

        source = inspect.getsource(module)
        self.assertNotIn("InMemoryArchive", source, "adapters are injected, not constructed")


class LayeringTest(unittest.TestCase):
    """Re-checks the rule over the code the agent added."""

    FORBIDDEN = {
        "domain": ("src.application", "src.infrastructure"),
        "application": ("src.infrastructure",),
    }

    def _imports(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.append(node.module)
        return found

    def test_no_inward_rule_is_broken(self):
        violations = []
        for layer, forbidden in self.FORBIDDEN.items():
            for path in (SRC / layer).rglob("*.py"):
                for imported in self._imports(path):
                    if imported.startswith(forbidden):
                        violations.append(f"{path.relative_to(SRC)} -> {imported}")
        self.assertEqual(violations, [])

    def test_domain_has_no_infrastructure_imports_even_deferred(self):
        """A function-local import is still an import."""
        for path in (SRC / "domain").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("src.infrastructure", source)
            self.assertNotIn("src.application", source)


if __name__ == "__main__":
    unittest.main()
