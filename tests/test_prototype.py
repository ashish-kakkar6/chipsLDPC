import csv
import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

from chipsldpc.prototype import minsum_decode, run_prototype


class PrototypeTests(unittest.TestCase):
    def test_scaled_min_sum_corrects_low_prior_variable(self):
        rows = [[0, 1], [1, 2]]
        result = minsum_decode(rows, [4.0, 1.0, 4.0], [1, 1], 5)
        self.assertEqual(result, {"correction": [0, 1, 0], "iterations": 1})
        weak = minsum_decode(rows, [4.0, 1.0, 4.0], [1, 1], 1, scale=0.1)
        self.assertEqual(weak["correction"], [0, 0, 0])

    def test_vectorized_updates_match_direct_extrinsic_equations(self):
        rows = [[0, 1, 2], [1, 3], [0, 2, 3, 4]]
        edges = [(check, variable) for check, row in enumerate(rows) for variable in row]

        def direct(priors, syndrome, scale, budget):
            v2c = {(check, variable): priors[variable] for check, variable in edges}
            for iteration in range(1, budget + 1):
                c2v = {}
                for check, variable in edges:
                    others = [v2c[check, other] for other in rows[check] if other != variable]
                    sign = (-1) ** (syndrome[check] + sum(value < 0 for value in others))
                    c2v[check, variable] = scale * sign * min(abs(value) for value in others)
                marginal = [prior + sum(value for (_, other), value in c2v.items() if other == variable)
                            for variable, prior in enumerate(priors)]
                correction = [int(value < 0) for value in marginal]
                if all(sum(correction[v] for v in row) % 2 == bit for row, bit in zip(rows, syndrome)):
                    break
                v2c = {(check, variable): marginal[variable] - c2v[check, variable]
                       for check, variable in edges}
            return {"correction": correction, "iterations": iteration}

        rng = np.random.default_rng(12)
        for scale in (0.5, 0.75, 1.0):
            for _ in range(25):
                # Repeated values exercise tied and zero minima as well as signed messages.
                priors = rng.integers(-2, 6, size=5).astype(float).tolist()
                syndrome = rng.integers(0, 2, size=3).tolist()
                self.assertEqual(minsum_decode(rows, priors, syndrome, 8, scale=scale),
                                 direct(priors, syndrome, scale, 8))

    def make_corpus(self, directory):
        source = directory / "source"
        source.mkdir()
        (source / "sweep.json").write_text(json.dumps({
            "dem": {"row_ones": [[0, 1]], "logical_ones": [[0]], "probabilities": [[0.1, 0.2]]},
            "decoder": {"prior_scale": 2}, "sampling": {"p_values": [0.003]},
        }))
        # Identical syndrome, opposite truths: the decoder must get identical inputs.
        (source / "benchmark.txt").write_text(
            "1 2 1 3 1 1 4 7\n1 0\n0.003 2\n4 3\n1 0\n1 1\n")
        return source

    def test_custom_decoder_never_receives_truth_and_convergence_is_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = self.make_corpus(directory)
            plugin = directory / "decode.py"
            plugin.write_text(
                "import math\n"
                "def decode(row_ones, priors, syndrome, max_iterations):\n"
                "    assert row_ones == [[0, 1]] and syndrome == [1]\n"
                "    assert math.isclose(priors[0], math.log(9))\n"
                "    assert max_iterations in (1, 3)\n"
                "    row_ones[0][0] = 99\n"
                "    return {'correction': [1, 0], 'iterations': 1, 'converged': False}\n")
            output = directory / "run"
            path = run_prototype({"decoder": {"kind": "python", "path": str(plugin), "budgets": [1, 3]}},
                                 source, output)
            with path.open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 4)
            self.assertEqual([row["logical_failure"] for row in rows], ["1", "1", "0", "0"])
            self.assertTrue(all(row["converged"] == "1" for row in rows))
            config = json.loads((output / "artifact" / "config.json").read_text())
            self.assertEqual(config["prior_source"], "DEM log likelihood ratios")
            self.assertIn("not a bit-exact", config["arithmetic"])

    def test_vector_result_has_unknown_work_and_quantized_prior_fallback_is_labelled(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = self.make_corpus(directory)
            metadata = json.loads((source / "sweep.json").read_text())
            del metadata["dem"]["probabilities"]
            (source / "sweep.json").write_text(json.dumps(metadata))
            plugin = directory / "decode.py"
            plugin.write_text("def decode(rows, priors, syndrome, max_iterations):\n"
                              "    assert priors == [2.0, 1.5]\n    return [0, 0]\n")
            output = directory / "run"
            path = run_prototype({"decoder": {"path": str(plugin)}}, source, output)
            with path.open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(all(row["iterations"] == "" and row["converged"] == "0" for row in rows))
            metadata = json.loads((output / "artifact" / "config.json").read_text())
            self.assertFalse(metadata["iterations_complete"])
            self.assertIn("approximate", metadata["prior_source"])

    def test_invalid_correction_does_not_publish_a_partial_csv(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = self.make_corpus(directory)
            plugin = directory / "decode.py"
            plugin.write_text("def decode(*args):\n    return [2, 0]\n")
            output = directory / "run"
            with self.assertRaisesRegex(ValueError, "binary"):
                run_prototype({"decoder": {"path": str(plugin)}}, source, output)
            self.assertFalse((output / "raw" / "shots.csv").exists())
            self.assertFalse((output / "raw" / "shots.csv.tmp").exists())


if __name__ == "__main__":
    unittest.main()
