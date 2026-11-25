"""Exercise input integrity, paired-corpus reuse and non-destructive resume."""

import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from chipsldpc.config import load_recipe, validate
from chipsldpc.workflow import ROOT, corpus_copy, digest, run, scientific_spec, plotting_environment, execute, _compiler_stack
import os


class RunnerTest(unittest.TestCase):
    def test_compiler_launch_tolerates_platform_stack_restrictions(self):
        for error in (ValueError("unsupported limit"), OSError("not permitted")):
            with patch("chipsldpc.workflow.resource.setrlimit", side_effect=error):
                _compiler_stack()
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "compiler.log"
            execute([sys.executable, "-c", "print('compiler child started')"], log, compiler=True)
            self.assertIn("compiler child started", log.read_text())

    def test_plotting_does_not_move_the_mill_download_cache(self):
        before = os.environ.get("XDG_CACHE_HOME")
        with plotting_environment():
            self.assertTrue(os.environ.get("XDG_CACHE_HOME"))
        self.assertEqual(os.environ.get("XDG_CACHE_HOME"), before)

    def test_resume_and_reject_changed_inputs(self):
        recipe = ROOT / "experiments/python-baseline.toml"
        spec = load_recipe(recipe, shots=12)
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            output = Path(temporary) / "experiment"
            run(spec, recipe, out=output, prepare_only=True)
            benchmark = output / "source/benchmark.txt"
            original = benchmark.read_bytes()
            modified_workers = copy.deepcopy(spec)
            modified_workers["run"]["workers"] = 1
            run(modified_workers, recipe, out=output, prepare_only=True)
            self.assertEqual(benchmark.read_bytes(), original)
            changed = copy.deepcopy(spec)
            changed["sampling"]["shots"] = 13
            with self.assertRaisesRegex(ValueError, "different experiment"):
                run(changed, recipe, out=output, prepare_only=True)
            self.assertEqual(benchmark.read_bytes(), original)
            benchmark.write_bytes(original + b"changed\n")
            with self.assertRaisesRegex(ValueError, "prepared input changed"):
                run(spec, recipe, out=output, prepare_only=True)

    def test_corpus_reuse_keeps_samples_and_updates_capacity_receipt(self):
        recipe = ROOT / "experiments/python-baseline.toml"
        original = load_recipe(recipe, shots=12)
        other = copy.deepcopy(original)
        other["decoder"]["budgets"] = [32]
        other["decoder"]["iterations"] = 32
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            first, second = Path(temporary) / "first", Path(temporary) / "second"
            run(original, recipe, out=first, prepare_only=True)
            run(other, recipe, out=second, samples=first / "source", prepare_only=True)
            a = (first / "source/benchmark.txt").read_text().splitlines()
            b = (second / "source/benchmark.txt").read_text().splitlines()
            self.assertEqual(a[1:], b[1:])
            self.assertEqual(b[0].split()[3], "32")
            metadata = json.loads((second / "source/sweep.json").read_text())
            self.assertEqual(metadata["sampling"]["benchmark_sha256"], digest(second / "source/benchmark.txt"))
            wrong_seed = copy.deepcopy(other)
            wrong_seed["sampling"]["seed"] += 1
            with self.assertRaisesRegex(ValueError, "seed"):
                corpus_copy(first / "source", Path(temporary) / "wrong", wrong_seed)

    def test_never_clears_unrelated_output(self):
        recipe = ROOT / "experiments/python-baseline.toml"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            sentinel = output / "keep.txt"
            sentinel.write_text("important experiment")
            with self.assertRaisesRegex(ValueError, "not empty"):
                run(load_recipe(recipe), recipe, out=output, prepare_only=True)
            self.assertEqual(sentinel.read_text(), "important experiment")

    def test_toolchain_change_cannot_replace_an_existing_run(self):
        recipe = ROOT / "experiments/smoke.toml"
        spec = load_recipe(recipe, shots=1)
        tools = {"python": "3.12.test", "platform": "test-platform", "machine": "test-machine",
                 "packages": {name: "test-version" for name in ("stim", "numpy", "matplotlib")},
                 **{name: {"available": True, "version": "test-version-1"}
                    for name in ("java", "verilator", "c++", "make")}}
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()), \
                patch("chipsldpc.workflow.versions", return_value=tools) as versions, \
                patch("chipsldpc.workflow.producer_files", return_value={}):
            output = Path(temporary) / "run"
            run(spec, recipe, out=output, prepare_only=True)
            benchmark = (output / "source/benchmark.txt").read_bytes()
            receipt = (output / "run.json").read_bytes()
            for field in ("verilator", "java", "c++", "machine", "platform"):
                changed = copy.deepcopy(tools)
                if isinstance(changed[field], dict):
                    changed[field]["version"] = "test-version-2"
                else:
                    changed[field] += "-changed"
                versions.return_value = changed
                with self.subTest(tool=field), self.assertRaisesRegex(ValueError, "different experiment"):
                    run(spec, recipe, out=output, prepare_only=True)
                self.assertEqual((output / "source/benchmark.txt").read_bytes(), benchmark)
                self.assertEqual((output / "run.json").read_bytes(), receipt)

    def test_reused_corpus_rejects_changed_circuit_contents_at_same_path(self):
        from chipsldpc.prepare import prepare
        import stim

        for kind in ("factory", "stim"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                circuit_path = directory / ("circuit.py" if kind == "factory" else "circuit.stim")
                if kind == "factory":
                    circuit_path.write_bytes((ROOT / "experiments/circuits.py").read_bytes())
                else:
                    stim.Circuit.generated("repetition_code:memory", distance=3, rounds=3,
                                           after_clifford_depolarization=0.003).to_file(str(circuit_path))
                spec = validate({"circuit": {"kind": kind, "path": str(circuit_path)},
                                 "sampling": {"shots": 2}})
                source = directory / "source"
                prepare(spec, source)
                benchmark = (source / "benchmark.txt").read_bytes()
                # A path match is insufficient: the recipe now names different
                # source bytes from those that produced the saved circuit.
                circuit_path.write_text(circuit_path.read_text() + "\n# changed input\n")
                destination = directory / "must-not-copy"
                with self.assertRaisesRegex(ValueError, "changed since these samples"):
                    corpus_copy(source, destination, spec)
                self.assertFalse(destination.exists())
                self.assertEqual((source / "benchmark.txt").read_bytes(), benchmark)


if __name__ == "__main__":
    unittest.main()
