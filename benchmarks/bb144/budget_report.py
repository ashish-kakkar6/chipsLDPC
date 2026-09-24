#!/usr/bin/env python3
"""Plot logical word failure against mean executed BP iterations."""

import argparse
import csv
import json
import math
import statistics
from pathlib import Path

from report import wilson


def summarize(budget, rows, config):
    values = [int(row["iterations"]) for row in rows]
    failures = sum(int(row["logical_failure"]) for row in rows)
    low, high = wilson(failures, len(rows))
    mean = statistics.fmean(values)
    mean_ci = (1.96 * statistics.stdev(values) / math.sqrt(len(values))
               if len(values) > 1 else 0.0)
    t0, tr = config.get("initial_iterations"), config.get("relay_iterations")
    relay_r = ((budget - t0) // tr if t0 is not None and tr is not None else None)
    return {
        "max_bp_iterations": budget,
        "paper_R": relay_r,
        "shots": len(rows),
        "failures": failures,
        "word_failure_probability": failures / len(rows),
        "word_failure_ci95_low": low,
        "word_failure_ci95_high": high,
        "mean_executed_iterations": mean,
        "mean_iterations_ci95_half_width": mean_ci,
        "p95_executed_iterations": sorted(values)[math.ceil(0.95 * len(values)) - 1],
        "nonconverged": sum(row["status"] == "bp_nonconverged" for row in rows),
        "mean_legs_executed": (statistics.fmean(int(row["legs_executed"]) for row in rows)
                               if "legs_executed" in rows[0] else None),
    }


def plot(records, output, label, p):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = [row["mean_executed_iterations"] for row in records]
    xerr = [min(row["mean_iterations_ci95_half_width"], value * (1 - 1e-9))
            for row, value in zip(records, x)]
    y = [row["word_failure_probability"] or row["word_failure_ci95_high"]
         for row in records]
    figure, axis = plt.subplots(figsize=(9.6, 5.2))
    line, = axis.plot(x, y, "-", linewidth=1.5, label=label)
    for index, row in enumerate(records):
        rate = row["word_failure_probability"]
        if rate:
            lower = min(rate - row["word_failure_ci95_low"], rate * (1 - 1e-9))
            axis.errorbar(x[index], rate, xerr=xerr[index],
                          yerr=([lower], [row["word_failure_ci95_high"] - rate]),
                          fmt="+", capsize=3, color=line.get_color())
        else:
            axis.errorbar(x[index], y[index], xerr=xerr[index], fmt="v", capsize=3,
                          color=line.get_color())
    axis.set(xscale="log", yscale="log", xlabel="Average BP iteration count for Z",
             ylabel="Logical word-failure probability",
             title=f"{label}; p={p:g}")
    axis.grid(True, which="both", alpha=0.2)
    axis.legend()
    figure.tight_layout()
    for suffix in ("png", "pdf"):
        figure.savefig(output / f"logical_failure_vs_average_iterations.{suffix}", dpi=180)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("sweep", type=Path)
    parser.add_argument("run", type=Path)
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    with args.raw.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or "max_bp_iterations" not in rows[0]:
        raise ValueError("expected budget-tagged shot rows")
    sweep = json.loads(args.sweep.read_text())
    run = json.loads(args.run.read_text())
    config = json.loads(args.config.read_text())
    probabilities = {float(row["p"]) for row in rows}
    if len(probabilities) != 1:
        raise ValueError("the iteration-budget plot requires exactly one p value")
    p = probabilities.pop()
    expected_shots = int(sweep["sampling"]["shots_per_p"])
    grouped = {}
    for row in rows:
        grouped.setdefault(int(row["max_bp_iterations"]), []).append(row)
    for budget, group in grouped.items():
        if len(group) != expected_shots or {int(row["shot"]) for row in group} != set(range(expected_shots)):
            raise ValueError(f"budget {budget}: incomplete or duplicate shots")
        if any(int(row["iterations"]) > budget for row in group):
            raise ValueError(f"budget {budget}: decoder exceeded its iteration limit")

    records = [summarize(budget, grouped[budget], config) for budget in sorted(grouped)]
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "chipsldpc.bb144-iteration-budget-sweep.v1",
        "decoder": args.label,
        "p": p,
        "logical_failure": "nonconvergence or any mismatch among 12 logical observables",
        "rate": "failures / shots (no per-QEC-cycle conversion)",
        "paper_reference": "arXiv:2510.21600v1 Figure 4",
        "simulation_wall_seconds": run["wall_seconds"],
        "decoder_configuration": config,
        "records": records,
    }
    (args.output / "budget_sweep.json").write_text(json.dumps(report, indent=2) + "\n")
    with (args.output / "budget_sweep.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0])
        writer.writeheader()
        writer.writerows(records)
    plot(records, args.output, args.label, p)
    print("budget mean_iterations failures/shots word_failure")
    for row in records:
        print(f"{row['max_bp_iterations']:>6} {row['mean_executed_iterations']:>15.3f} "
              f"{row['failures']}/{row['shots']} "
              f"{row['word_failure_probability']:.6g}")


if __name__ == "__main__":
    main()
