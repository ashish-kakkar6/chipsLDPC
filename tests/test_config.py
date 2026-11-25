import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from chipsldpc.config import load_recipe, validate

ROOT = Path(__file__).resolve().parents[1]


class RecipeTest(unittest.TestCase):
    def test_conflicting_explicit_capacities_are_rejected(self):
        common = {"circuit": {"name": "repetition"}}
        for decoder in ({"kind": "vanilla", "iterations": 1, "budgets": [30]},
                        {"kind": "relay", "relay_legs": 1, "budgets": [4080]}):
            with self.subTest(decoder=decoder), self.assertRaisesRegex(ValueError, "conflicts"):
                validate({**common, "decoder": decoder})

    def test_all_shipped_recipes_validate(self):
        for path in (ROOT / "experiments").glob("*.toml"):
            with self.subTest(recipe=path.name):
                load_recipe(path)

    def test_main_figure_profile(self):
        value = load_recipe(ROOT / "experiments/bb144-p003.toml")
        self.assertEqual(value["sampling"]["shots"], 20000)
        self.assertEqual(value["noise"], {"p": 0.003})
        self.assertEqual(value["decoder"]["budgets"], [60, 120, 180, 300, 540, 1020, 2040, 4080])
        self.assertEqual(value["decoder"]["relay_legs"], 67)
        self.assertEqual(value["decoder"]["solutions"], 5)

    def test_invalid_scientific_settings_rejected(self):
        base = load_recipe(ROOT / "experiments/smoke.toml")
        cases = [("noise", "p", float("nan")), ("sampling", "shots", True),
                 ("decoder", "budgets", [1, 1]), ("decoder", "iterationss", 20),
                 ("circuit", "sampler", "legacy"), ("run", "workers", 0),
                 ("decoder", "scale", 0.75)]
        for section, name, value in cases:
            with self.subTest(setting=name):
                spec = copy.deepcopy(base)
                spec[section][name] = value
                with self.assertRaises(ValueError):
                    validate(spec)

    def test_python_rule_cannot_silently_run_existing_rtl(self):
        with self.assertRaisesRegex(ValueError, "no RTL implementation"):
            load_recipe(ROOT / "experiments/decoder-variant.toml", backend="verilator")

    def test_relay_budget_requires_complete_legs(self):
        value = load_recipe(ROOT / "experiments/bb144-p003.toml")
        value["decoder"]["budgets"] = [61]
        with self.assertRaisesRegex(ValueError, "each Relay budget"):
            validate(value)

    def test_decoder_fields_cannot_leak_between_algorithms(self):
        for decoder in (
            {"kind": "vanilla", "iterations": 30, "initial_iterations": 1},
            {"kind": "vanilla", "relay_legs": 2},
            {"kind": "relay", "iterations": 1},
            {"kind": "python", "solutions": 5},
        ):
            with self.subTest(decoder=decoder), self.assertRaisesRegex(ValueError, "not applicable"):
                validate({"circuit": {"name": "repetition"}, "decoder": decoder})

    def test_circuit_settings_are_specific_to_input_kind(self):
        for circuit in (
            {"kind": "stim", "path": str(ROOT / "experiments/circuits.py"), "distance": 5},
            {"kind": "factory", "path": str(ROOT / "experiments/circuits.py"), "distance": 5},
            {"kind": "builtin", "name": "repetition", "function": "make_circuit"},
        ):
            with self.subTest(circuit=circuit), self.assertRaisesRegex(ValueError, "not applicable"):
                validate({"circuit": circuit})

    def test_custom_decoder_does_not_silently_ignore_scale_or_function(self):
        for decoder, message in (
            ({"kind": "python", "path": str(ROOT / "experiments/decoders.py"), "scale": 0.5}, "custom decoder"),
            ({"kind": "python", "function": "my_decoder"}, "requires decoder.path"),
        ):
            with self.subTest(decoder=decoder), self.assertRaisesRegex(ValueError, message):
                validate({"circuit": {"name": "repetition"}, "decoder": decoder})


if __name__ == "__main__":
    unittest.main()
