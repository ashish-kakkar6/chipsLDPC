"""Scientific invariants for the Stim-to-RTL corpus conversion."""

import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import stim

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from chipsldpc.prepare import apply_reduction, extract_dem, prepare, preprocess, sample_circuit


class PreparationTest(unittest.TestCase):
    def test_singletons_preserve_all_syndromes_and_logical_actions(self):
        # Duplicate singleton checks, two cascading eliminations, an empty check,
        # and a nontrivial three-variable cycle. Test every latent error pattern.
        rows = [{0}, {0}, {0, 1}, {1, 2}, set(), {3, 4}, {4, 5}, {3, 5}]
        logicals = [{0, 2, 3}, {1, 5}]
        keys = [(tuple(i for i, row in enumerate(rows) if v in row),
                 tuple(i for i, row in enumerate(logicals) if v in row)) for v in range(6)]
        reduction = preprocess(keys, len(rows), len(logicals))
        errors = np.array(list(itertools.product((0, 1), repeat=6)), dtype=np.uint8)
        h = np.array([[v in row for v in range(6)] for row in rows], dtype=np.uint8)
        logical = np.array([[v in row for v in range(6)] for row in logicals], dtype=np.uint8)
        detector_samples, actual_samples = (errors @ h.T) % 2, (errors @ logical.T) % 2
        syndrome, actual = apply_reduction(reduction, detector_samples, actual_samples)
        reduced_errors = errors[:, reduction.kept_variables]
        reduced_h = np.array([[v in row for v in range(3)] for row in reduction.rows], dtype=np.uint8)
        reduced_l = np.array([[v in row for v in range(3)] for row in reduction.logicals], dtype=np.uint8)
        np.testing.assert_array_equal(syndrome, (reduced_errors @ reduced_h.T) % 2)
        np.testing.assert_array_equal(actual, (reduced_errors @ reduced_l.T) % 2)
        for check in (1, 4):
            inconsistent = detector_samples.copy()
            inconsistent[0, check] ^= 1
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                apply_reduction(reduction, inconsistent, actual_samples)

    def test_dem_contract_and_odd_parity_merging(self):
        keys, values = extract_dem(stim.DetectorErrorModel("error(0.1) D0 L0\nerror(0.2) D0 L0"))
        self.assertEqual(keys, [((0,), (0,))])
        self.assertAlmostEqual(values[0], 0.26)
        for model, message in (
            ("error(0.01) L0", "detector-free"),
            ("error(0.6) D0", "prior probabilities"),
            ("error(0.01) D0 ^ D1", "decomposed"),
        ):
            with self.assertRaisesRegex(ValueError, message):
                extract_dem(stim.DetectorErrorModel(model))

    def test_stim_sample_prefix_is_independent_of_shot_count(self):
        circuit = stim.Circuit.generated("repetition_code:memory", distance=3, rounds=3,
                                         after_clifford_depolarization=0.03)
        short = sample_circuit(circuit, 0.03, 9, 19)
        long = sample_circuit(circuit, 0.03, 300, 19)
        for a, b in zip(short, long):
            np.testing.assert_array_equal(a, b[:9])

    def test_corpus_probability_order_and_decoder_independence(self):
        base = {"circuit": {"kind": "builtin", "name": "repetition", "distance": 3, "rounds": 3},
                "noise": {"probabilities": [0.003, 0.01]}, "sampling": {"shots": 40, "seed": 8},
                "decoder": {"kind": "vanilla", "iterations": 30}}
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "one", Path(temporary) / "two"
            metadata = prepare(base, first)
            same_corpus = prepare({**base, "decoder": {"kind": "relay", "initial_iterations": 60}},
                                  Path(temporary) / "other-decoder")
            self.assertEqual(metadata["sampling"]["corpus_sha256"], same_corpus["sampling"]["corpus_sha256"])
            self.assertNotEqual(metadata["sampling"]["benchmark_sha256"], same_corpus["sampling"]["benchmark_sha256"])
            changed = {**base, "noise": {"probabilities": [0.01, 0.003]},
                       "decoder": {"kind": "relay", "initial_iterations": 60}}
            prepare(changed, second)
            for tag in ("p0_003", "p0_01"):
                with np.load(first / f"{tag}.samples.npz") as a, np.load(second / f"{tag}.samples.npz") as b:
                    for key in a:
                        np.testing.assert_array_equal(a[key], b[key])
            self.assertGreater(metadata["dem"]["n"], 0)
            self.assertTrue(all(len(row) >= 2 for row in metadata["dem"]["row_ones"]))
            self.assertTrue((first / "verify/p0_003/problem.json").is_file())
            self.assertGreater(len(list(first.glob("verify/**/problem.json"))), 2)
            self.assertNotIn("decoder", json.loads((first / "prepare-spec.json").read_text()))

    def test_synthetic_verification_inputs_do_not_enter_statistics(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            sweep = prepare({"circuit": {"kind": "builtin", "name": "repetition"},
                             "sampling": {"shots": 1, "verification_shots": 8}}, output)
            fixture_metadata = [json.loads(path.read_text()) for path in output.glob("verify/**/actual.json")]
            self.assertEqual(sum(value["source"] == "sampled" for value in fixture_metadata), 1)
            self.assertTrue(any(value["source"].startswith("synthetic") for value in fixture_metadata))
            self.assertEqual(sweep["sampling"]["shots_per_p"], 1)
            with np.load(output / "p0_003.samples.npz") as samples:
                self.assertEqual(len(samples["syndrome"]), 1)

    def test_factory_and_static_stim_have_explicit_noise_semantics(self):
        factory = Path(__file__).resolve().parents[1] / "experiments/circuits.py"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            config = {"circuit": {"kind": "factory", "path": str(factory)}, "sampling": {"shots": 5}}
            generated = prepare(config, output / "factory")
            self.assertFalse(generated["code"]["cycles_explicit"])
            config["circuit"]["rounds"] = 6
            six_rounds = prepare(config, output / "six-rounds")
            self.assertTrue(six_rounds["code"]["cycles_explicit"])
            self.assertEqual(six_rounds["code"]["cycles"], 6)
            self.assertGreater(six_rounds["dem"]["m"], generated["dem"]["m"])
            circuit_path = output / "factory/p0_003.stim"
            static = {"circuit": {"kind": "stim", "path": str(circuit_path)}, "sampling": {"shots": 5}}
            saved = prepare(static, output / "static")
            self.assertEqual(saved["code"]["probability_role"], "label_only")
            static["noise"] = {"probabilities": [0.003, 0.004]}
            with self.assertRaisesRegex(ValueError, "already contains"):
                prepare(static, output / "invalid")

    def test_more_than_32_observables_are_preserved(self):
        circuit = stim.Circuit.generated("repetition_code:memory", distance=3, rounds=3,
                                         after_clifford_depolarization=0.01)
        for index in range(1, 33):
            circuit.append("OBSERVABLE_INCLUDE", [stim.target_rec(-1)], index)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "many.stim"
            circuit.to_file(str(path))
            sweep = prepare({"circuit": {"kind": "stim", "path": str(path)},
                             "sampling": {"shots": 4}}, Path(temporary) / "source")
            self.assertEqual(len(sweep["dem"]["logical_ones"]), 33)
            header = (Path(temporary) / "source/benchmark.txt").read_text().splitlines()[0].split()
            self.assertEqual(int(header[2]), 33)

    def test_missing_logical_observable_is_actionable(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "no-logical.stim"
            path.write_text("R 0\nX_ERROR(0.01) 0\nM 0\nDETECTOR rec[-1]\n")
            with self.assertRaisesRegex(ValueError, "OBSERVABLE_INCLUDE"):
                prepare({"circuit": {"kind": "stim", "path": str(path)}}, Path(temporary) / "source")


if __name__ == "__main__":
    unittest.main()
