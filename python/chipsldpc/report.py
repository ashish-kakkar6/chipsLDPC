"""Summarize detector-decoding runs without assuming a code or logical count."""

from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
import textwrap


SUCCESS_STATUSES = {"bp_converged", "osd_solved"}
FAILURE_STATUSES = {"bp_nonconverged", "osd_inconsistent", "osd_overflow"}


def wilson(failures: int, shots: int) -> tuple[float, float]:
    """Two-sided 95% Wilson interval for a binomial proportion."""
    if shots < 1 or not 0 <= failures <= shots:
        raise ValueError("require 0 <= failures <= shots and shots > 0")
    z = 1.959963984540054
    denominator = 1 + z * z / shots
    center = (failures / shots + z * z / (2 * shots)) / denominator
    radius = z * math.sqrt(failures * (shots - failures) / shots**3 + z * z / (4 * shots**2)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def _read_optional(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def _bit(row, name):
    if row.get(name) not in ("0", "1"):
        raise ValueError(f"{name} must be 0 or 1")
    return int(row[name])


def _summarize(p, budget, rows):
    failures = sum(_bit(row, "logical_failure") for row in rows)
    mismatches = sum(int(row["predicted_observables"], 0) != int(row["actual_observables"], 0)
                     for row in rows)
    # A successful OSD result can follow BP nonconvergence. Keep these distinct.
    nonconverged = sum(row["status"] in FAILURE_STATUSES for row in rows)
    converged_mismatches = sum(row["status"] in SUCCESS_STATUSES and
                              int(row["predicted_observables"], 0) != int(row["actual_observables"], 0)
                              for row in rows)
    bp_nonconverged = sum(1 - _bit(row, "converged") for row in rows) if "converged" in rows[0] else None
    counts = [int(row["iterations"]) for row in rows if row.get("iterations", "") != ""]
    cycles = [int(row["total_cycles"]) for row in rows if row.get("total_cycles", "") != ""]
    if any(value < 0 for value in counts + cycles):
        raise ValueError("iterations and cycles must be nonnegative")
    low, high = wilson(failures, len(rows))
    return {"p": p, "max_bp_iterations": budget, "shots": len(rows), "failures": failures,
            "decoder_nonconverged": nonconverged, "observable_mismatches": mismatches,
            "converged_logical_mismatches": converged_mismatches,
            "bp_nonconverged": bp_nonconverged,
            "word_failure_probability": failures / len(rows),
            "word_failure_ci95_low": low, "word_failure_ci95_high": high,
            "mean_iterations": statistics.fmean(counts) if len(counts) == len(rows) else None,
            "iteration_counts_available": len(counts),
            "mean_decoder_cycles": statistics.fmean(cycles) if len(cycles) == len(rows) else None}


def _series(axis, records, xkey, label, color):
    measured = [row for row in records if row["failures"]]
    zero = [row for row in records if not row["failures"]]
    if measured:
        rates = [row["word_failure_probability"] for row in measured]
        axis.errorbar([row[xkey] for row in measured], rates,
                      yerr=([value - row["word_failure_ci95_low"] for value, row in zip(rates, measured)],
                            [row["word_failure_ci95_high"] - value for value, row in zip(rates, measured)]),
                      fmt="o", capsize=3, color=color, label=label)
    if zero:
        bound_label = (f"{label}: " if label.startswith("Budget ") else "") + "95% upper bound (zero failures)"
        axis.scatter([row[xkey] for row in zero], [row["word_failure_ci95_high"] for row in zero],
                     marker="v", facecolors="none", edgecolors=color,
                     label=bound_label)
    # Bounds are not point estimates and are never joined to measured rates.


def _plots(records, metadata, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    probabilities = sorted({row["p"] for row in records})
    budgets = sorted({row["max_bp_iterations"] for row in records}, key=lambda value: -1 if value is None else value)
    budget_sweep = len(probabilities) == 1 and len(budgets) > 1
    label_only = metadata.get("probability_role") == "label_only"
    measured_iterations = all(row["mean_iterations"] is not None for row in records)
    xkey = "mean_iterations" if budget_sweep and measured_iterations else "max_bp_iterations" if budget_sweep else "p"
    xlabel = {"mean_iterations": "Mean decoder iterations per shot",
              "max_bp_iterations": "Maximum BP iterations",
              "p": "Declared p label" if label_only else "Physical error probability p"}[xkey]
    figure, axis = plt.subplots(figsize=(6.4, 4.2))
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    if budget_sweep:
        _series(axis, records, xkey, "Estimate (95% Wilson interval)", colors[0])
        annotations = defaultdict(int)
        for row in records:
            y = row["word_failure_probability"] if row["failures"] else row["word_failure_ci95_high"]
            offset = annotations[row[xkey], y]
            axis.annotate(str(row["max_bp_iterations"]), (row[xkey], y),
                          xytext=(5, 5 + 11 * offset), textcoords="offset points", fontsize=8)
            annotations[row[xkey], y] += 1
        axis.text(0.02, 0.02, "Labels: maximum iteration budget", transform=axis.transAxes, fontsize=8)
    else:
        for index, budget in enumerate(budgets):
            subset = [row for row in records if row["max_bp_iterations"] == budget]
            label = "Estimate (95% Wilson interval)" if len(budgets) == 1 else f"Budget {budget}"
            _series(axis, subset, xkey, label, colors[index % len(colors)])
    axis.set(xlabel=xlabel, ylabel="Word failure probability", yscale="log")
    if xkey == "p" and min(probabilities) > 0:
        axis.set_xscale("log")
        if len(probabilities) == 1:
            axis.set_xlim(probabilities[0] / 1.25, probabilities[0] * 1.25)
    observable_label = "observable" if metadata["observable_count"] == 1 else "observables"
    title = f"{metadata['label']} · {metadata['observable_count']} {observable_label}"
    if len(probabilities) == 1:
        title += f" · {'p label' if label_only else 'p'}={probabilities[0]:g}"
    if label_only:
        title += " (noise embedded in circuit)"
    title = textwrap.fill(title, width=78)
    axis.set_title(title, fontsize=10)
    axis.grid(True, which="both", alpha=0.25)
    axis.legend(fontsize=8)
    figure.tight_layout()
    for extension in ("png", "pdf"):
        figure.savefig(output / f"logical_failure.{extension}", dpi=180)
    plt.close(figure)
    if budget_sweep and measured_iterations:
        figure, axis = plt.subplots(figsize=(6.4, 4.2))
        ordered = sorted(records, key=lambda row: row["max_bp_iterations"])
        axis.plot([row["max_bp_iterations"] for row in ordered],
                  [row["mean_iterations"] for row in ordered], "o-")
        axis.set(xlabel="Maximum BP iterations", ylabel="Mean decoder iterations per shot", title=title)
        axis.grid(True, alpha=0.25)
        figure.tight_layout()
        for extension in ("png", "pdf"):
            figure.savefig(output / f"iteration_budget.{extension}", dpi=180)
        plt.close(figure)


def generate_report(run_dir: Path) -> Path:
    """Write summary CSV/JSON and figures; return the results directory.

    A word fails if decoding fails to return a valid correction or any declared
    observable differs. The two counts may overlap. Probabilities are per
    sampled circuit, without assuming independence between QEC rounds.
    """
    run_dir = Path(run_dir)
    source = json.loads((run_dir / "source" / "sweep.json").read_text())
    resolved = _read_optional(run_dir / "resolved.json")
    artifact = _read_optional(run_dir / "artifact" / "config.json")
    receipt = _read_optional(run_dir / "run.json")
    run_metadata = {key: receipt[key] for key in
                    ("identity", "hardware_key", "verification_frames", "samples_from") if key in receipt}
    dem = source.get("dem", {})
    logical_rows = dem.get("logical_ones")
    observable_count = len(logical_rows) if logical_rows is not None else artifact.get("observable_count")
    if observable_count is None or observable_count < 1:
        raise ValueError("source metadata must declare at least one logical observable")
    grouped = defaultdict(list)
    seen = set()
    with (run_dir / "raw" / "shots.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"p", "shot", "status", "predicted_observables", "actual_observables", "logical_failure"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"shot CSV is missing columns: {sorted(required - set(reader.fieldnames or []))}")
        for row in reader:
            p = float(row["p"])
            budget = int(row["max_bp_iterations"]) if row.get("max_bp_iterations", "") != "" else None
            shot = int(row["shot"])
            if not math.isfinite(p) or p < 0 or shot < 0 or (budget is not None and budget < 1):
                raise ValueError("invalid p, shot index or iteration budget")
            key = p, budget, shot
            if key in seen:
                raise ValueError(f"duplicate shot {shot} for p={p:g}, budget={budget}")
            seen.add(key)
            predicted, actual = int(row["predicted_observables"], 0), int(row["actual_observables"], 0)
            if min(predicted, actual) < 0 or max(predicted, actual).bit_length() > observable_count:
                raise ValueError("observable bit string exceeds the declared observable count")
            if row["status"] not in SUCCESS_STATUSES | FAILURE_STATUSES:
                raise ValueError(f"unknown decoder status: {row['status']}")
            if "converged" in row and _bit(row, "converged") != int(row["status"] == "bp_converged"):
                raise ValueError("converged flag disagrees with decoder status")
            if row.get("iterations", "") != "":
                iterations = int(row["iterations"])
                if iterations < 0 or (budget is not None and iterations > budget):
                    raise ValueError("reported iterations exceed the budget or are negative")
            failed = row["status"] in FAILURE_STATUSES
            if _bit(row, "logical_failure") != int(failed or predicted != actual):
                raise ValueError("logical_failure disagrees with status and observable predictions")
            grouped[p, budget].append(row)
    if not grouped:
        raise ValueError("cannot report an empty shot CSV")
    sampling = source.get("sampling", {})
    expected_p = {float(format(p, ".12g")) for p in sampling.get("p_values", {key[0] for key in grouped})}
    expected_budgets = set(resolved.get("decoder", {}).get("budgets",
                           artifact.get("budgets", {key[1] for key in grouped})))
    expected_groups = {(p, budget) for p in expected_p for budget in expected_budgets}
    if set(grouped) != expected_groups:
        missing = sorted(expected_groups - set(grouped), key=str)
        extra = sorted(set(grouped) - expected_groups, key=str)
        raise ValueError(f"incomplete p/budget groups: missing {missing}; unexpected {extra}")
    expected_shots = sampling.get("shots_per_p")
    if expected_shots is not None and (type(expected_shots) is not int or expected_shots < 1):
        raise ValueError("sampling.shots_per_p must be a positive integer")
    for (p, budget), rows in grouped.items():
        shots = {int(row["shot"]) for row in rows}
        count = expected_shots if expected_shots is not None else len(rows)
        if shots != set(range(count)):
            raise ValueError(f"incomplete shots for p={p:g}, budget={budget}: expected indices 0..{count - 1}")
    records = [_summarize(p, budget, rows) for (p, budget), rows in sorted(
        grouped.items(), key=lambda pair: (pair[0][0], -1 if pair[0][1] is None else pair[0][1]))]
    backend = resolved.get("run", {}).get("backend", artifact.get("backend", "verilator"))
    decoder = artifact.get("decoder", resolved.get("decoder", {}).get("kind", "decoder"))
    decoder_name = decoder.get("name", "decoder") if isinstance(decoder, dict) else str(decoder)
    decoder_name = {"early_terminating_min_sum_bp": "Vanilla BP", "relay_bp_s": "Relay-BP",
                    "vanilla": "Vanilla BP", "relay": "Relay-BP"}.get(decoder_name, decoder_name)
    code = source.get("code", {})
    code_name = code.get("name", code.get("label", "Detector circuit"))
    label = f"{code_name} · {decoder_name}"
    if backend == "python":
        label += " (Python float prototype)"
    metadata = {"schema": "chipsldpc.results.v1", "label": label, "backend": backend,
                "observable_count": observable_count,
                "probability_role": code.get("probability_role", "noise_parameter"),
                "failure_definition": "decoder_nonconverged + converged_logical_mismatches; observable_mismatches may overlap either class",
                "normalization": "per sampled circuit (word failure probability)",
                "interval": "two-sided 95% Wilson; zero-failure points show only its upper bound",
                "arithmetic": artifact.get("arithmetic", "floating-point prototype" if backend == "python" else "quantized RTL"),
                "sector": dem.get("sector", "observables declared by the supplied circuit"),
                "sampling": source.get("sampling", {}), "circuit": code,
                "decoder_config": artifact, "resolved_config": resolved,
                "run": run_metadata, "results": records}
    output = run_dir / "results"
    output.mkdir(parents=True, exist_ok=True)
    with (output / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    (output / "summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
    _plots(records, metadata, output)
    return output


report = generate_report
