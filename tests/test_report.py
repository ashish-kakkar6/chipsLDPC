import csv
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from chipsldpc.report import _series, generate_report, wilson


class ReportTests(unittest.TestCase):
    def make_run(self, directory, rows, observable_count=1):
        run = Path(directory)
        (run / "source").mkdir()
        (run / "raw").mkdir()
        (run / "source" / "sweep.json").write_text(json.dumps({
            "code": {"name": "Test circuit", "cycles": 12},
            "dem": {"logical_ones": [[] for _ in range(observable_count)]},
            "sampling": {"p_values": sorted({row["p"] for row in rows}),
                         "shots_per_p": max(row["shot"] for row in rows) + 1},
        }))
        fields = ["p", "shot", "max_bp_iterations", "status", "converged", "iterations",
                  "predicted_observables", "actual_observables", "logical_failure"]
        with (run / "raw" / "shots.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return run

    def row(self, shot, converged=True, mismatch=False, budget=10, p=0.003):
        return {"p": p, "shot": shot, "max_bp_iterations": budget,
                "status": "bp_converged" if converged else "bp_nonconverged",
                "converged": int(converged), "iterations": 1 if converged else budget,
                "predicted_observables": "0x1" if mismatch else "0x0", "actual_observables": "0x0",
                "logical_failure": int(not converged or mismatch)}

    def test_failure_counts_overlap_without_double_counting_and_preserve_word_normalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = self.make_run(temporary, [self.row(0), self.row(1, False), self.row(2, mismatch=True),
                                            self.row(3, False, True)])
            results = generate_report(run)
            data = json.loads((results / "summary.json").read_text())
            record = data["results"][0]
            self.assertEqual(record["failures"], 3)
            self.assertEqual(record["decoder_nonconverged"], 2)
            self.assertEqual(record["observable_mismatches"], 2)
            self.assertEqual(record["converged_logical_mismatches"], 1)
            self.assertEqual(record["failures"], record["decoder_nonconverged"] + record["converged_logical_mismatches"])
            self.assertEqual(record["word_failure_probability"], 0.75)
            self.assertIn("per sampled circuit", data["normalization"])
            self.assertTrue((results / "logical_failure.png").is_file())
            self.assertTrue((results / "logical_failure.pdf").is_file())

    def test_zero_failures_draw_only_an_upper_bound(self):
        low, high = wilson(0, 1000)
        self.assertAlmostEqual(low, 0.0)
        self.assertGreater(high, 0)
        self.assertLess(high, 0.004)
        axis = Mock()
        _series(axis, [{"p": 0.003, "failures": 0, "word_failure_ci95_high": high}], "p", "test", "blue")
        axis.errorbar.assert_not_called()
        axis.plot.assert_not_called()
        self.assertEqual(axis.scatter.call_args.args, ([0.003], [high]))

    def test_budget_groups_reuse_shot_ids_and_plot_measured_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            rows = [self.row(shot, budget=budget) for budget in (10, 20) for shot in (0, 1)]
            run = self.make_run(temporary, rows)
            results = generate_report(run)
            data = json.loads((results / "summary.json").read_text())
            self.assertEqual([row["shots"] for row in data["results"]], [2, 2])
            self.assertEqual([row["mean_iterations"] for row in data["results"]], [1, 1])
            self.assertTrue((results / "iteration_budget.pdf").is_file())

    def test_more_than_32_observables_and_python_label(self):
        with tempfile.TemporaryDirectory() as temporary:
            row = self.row(0, mismatch=True)
            row["predicted_observables"] = hex(1 << 100)
            run = self.make_run(temporary, [row], observable_count=101)
            (run / "artifact").mkdir()
            (run / "artifact" / "config.json").write_text(json.dumps({"backend": "python", "decoder": {"name": "variant"}}))
            results = generate_report(run)
            data = json.loads((results / "summary.json").read_text())
            self.assertEqual(data["results"][0]["observable_mismatches"], 1)
            self.assertIn("Python float prototype", data["label"])

    def test_duplicate_shots_and_inconsistent_failure_flags_are_rejected(self):
        for rows, message in (([self.row(0), self.row(0)], "duplicate"),
                              ([dict(self.row(0), logical_failure=1)], "disagrees")):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temporary:
                run = self.make_run(temporary, rows)
                with self.assertRaisesRegex(ValueError, message):
                    generate_report(run)

    def test_missing_probability_budget_and_shot_are_rejected(self):
        for missing, message in (("point", "groups"), ("budget", "groups"), ("shot", "incomplete shots")):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                rows = [self.row(shot, budget=budget, p=p)
                        for p in (0.003, 0.004) for budget in (10, 20) for shot in (0, 1)]
                run = self.make_run(temporary, rows)
                (run / "resolved.json").write_text(json.dumps({"decoder": {"budgets": [10, 20]}}))
                csv_path = run / "raw" / "shots.csv"
                with csv_path.open() as stream:
                    reader = csv.DictReader(stream)
                    fields, saved = reader.fieldnames, list(reader)
                if missing == "point":
                    saved = [row for row in saved if row["p"] != "0.004"]
                elif missing == "budget":
                    saved = [row for row in saved if row["max_bp_iterations"] != "20"]
                else:
                    saved.pop()
                with csv_path.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(saved)
                with self.assertRaisesRegex(ValueError, message):
                    generate_report(run)

    def test_iteration_cap_and_unknown_status_are_rejected(self):
        for row, message in ((dict(self.row(0), iterations=11), "iterations"),
                             (dict(self.row(0), status="mystery"), "unknown decoder status")):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temporary:
                run = self.make_run(temporary, [row])
                with self.assertRaisesRegex(ValueError, message):
                    generate_report(run)

    def test_osd_success_is_not_counted_as_decoder_nonconvergence(self):
        with tempfile.TemporaryDirectory() as temporary:
            row = dict(self.row(0, mismatch=True), status="osd_solved", converged=0)
            run = self.make_run(temporary, [row])
            results = generate_report(run)
            record = json.loads((results / "summary.json").read_text())["results"][0]
            self.assertEqual(record["decoder_nonconverged"], 0)
            self.assertEqual(record["bp_nonconverged"], 1)
            self.assertEqual(record["converged_logical_mismatches"], 1)

    def test_static_stim_probability_is_labelled_as_metadata_not_embedded_noise(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = self.make_run(temporary, [self.row(0)])
            source_path = run / "source" / "sweep.json"
            source = json.loads(source_path.read_text())
            source["code"]["probability_role"] = "label_only"
            source_path.write_text(json.dumps(source))
            figure, axis = Mock(), Mock()
            with patch("matplotlib.pyplot.subplots", return_value=(figure, axis)), patch("matplotlib.pyplot.close"):
                results = generate_report(run)
            self.assertEqual(axis.set.call_args.kwargs["xlabel"], "Declared p label")
            title = axis.set_title.call_args.args[0]
            self.assertIn("p label=0.003", title)
            self.assertIn("noise embedded in circuit", title.replace("\n", " "))
            self.assertEqual(json.loads((results / "summary.json").read_text())["probability_role"], "label_only")

    @unittest.skipUnless(shutil.which("c++"), "C++ compiler unavailable")
    def test_cpp_observable_serialization_across_word_boundaries(self):
        source = (Path(__file__).resolve().parents[1] / "benchmarks/bb144/sim_main.cpp").read_text()
        helper = source[source.index("static std::string packObservableBits"):source.index("static int benchmarkMain")]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / "test.cpp").write_text(
                "#include <string>\n#include <vector>\n#include <cassert>\n" + helper +
                "int main() {\n"
                "  assert(packObservableBits(std::vector<int>(144, 0)) == \"0x0\");\n"
                "  assert(packObservableBits(std::vector<int>(32, 1)) == \"0xffffffff\");\n"
                "  std::vector<int> bits(130, 0); bits[0]=1; bits[32]=1; bits[64]=1; bits[129]=1;\n"
                "  assert(packObservableBits(bits) == \"0x200000000000000010000000100000001\");\n}\n")
            subprocess.run(["c++", "-std=c++17", str(path / "test.cpp"), "-o", str(path / "test")], check=True)
            subprocess.run([str(path / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
