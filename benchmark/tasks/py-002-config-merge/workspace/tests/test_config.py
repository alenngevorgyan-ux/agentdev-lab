import copy
import unittest

from src.config import ConfigError, resolve_config


class ResolveConfigTest(unittest.TestCase):
    def test_no_layers(self):
        self.assertEqual(resolve_config([]), {})

    def test_single_layer_is_copied(self):
        layer = {"a": {"b": 1}}
        result = resolve_config([layer])
        self.assertEqual(result, {"a": {"b": 1}})
        result["a"]["b"] = 99
        self.assertEqual(layer, {"a": {"b": 1}})

    def test_later_layer_overrides_scalar(self):
        self.assertEqual(resolve_config([{"a": 1}, {"a": 2}]), {"a": 2})

    def test_nested_merge(self):
        base = {"db": {"host": "localhost", "port": 5432}}
        override = {"db": {"port": 6543}, "debug": True}
        self.assertEqual(
            resolve_config([base, override]),
            {"db": {"host": "localhost", "port": 6543}, "debug": True},
        )

    def test_deep_nesting(self):
        result = resolve_config([{"a": {"b": {"c": 1, "d": 2}}}, {"a": {"b": {"c": 9}}}])
        self.assertEqual(result, {"a": {"b": {"c": 9, "d": 2}}})

    def test_lists_are_replaced_not_concatenated(self):
        self.assertEqual(resolve_config([{"x": [1, 2]}, {"x": [3]}]), {"x": [3]})

    def test_inputs_are_not_mutated(self):
        base = {"db": {"host": "localhost"}}
        override = {"db": {"port": 1}}
        snapshot = (copy.deepcopy(base), copy.deepcopy(override))
        resolve_config([base, override])
        self.assertEqual((base, override), snapshot)

    def test_type_conflict_mapping_over_scalar(self):
        with self.assertRaises(ConfigError) as ctx:
            resolve_config([{"a": {"b": 1}}, {"a": 5}])
        self.assertIn("a", str(ctx.exception))

    def test_type_conflict_reports_dotted_path(self):
        with self.assertRaises(ConfigError) as ctx:
            resolve_config([{"a": {"b": 1}}, {"a": {"b": {"c": 2}}}])
        self.assertIn("a.b", str(ctx.exception))

    def test_three_layers(self):
        result = resolve_config([{"a": 1}, {"b": 2}, {"a": 3, "c": 4}])
        self.assertEqual(result, {"a": 3, "b": 2, "c": 4})


if __name__ == "__main__":
    unittest.main()
