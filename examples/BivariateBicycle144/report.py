#!/usr/bin/env python3
"""Reduce a BB144 RTL sweep into logical-error, cycle, and plot artifacts."""

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path


STAGES = {
    "dispatch": "dispatch_cycles",
    "bp": "bp_cycles",
    "bp_output": "bp_output_cycles",
    "sort": "sort_cycles",
    "solver_rows": "solver_row_cycles",
    "solver_mesh": "solver_mesh_cycles",
    "osd_output": "osd_output_cycles",
    "osd_control": "osd_control_cycles",
}


def percentile(values, probability):
    ordered = sorted(values)
    return ordered[math.ceil(probability * len(ordered)) - 1]


def wilson(failures, shots):
    z = 1.959963984540054
    center = (failures / shots + z * z / (2 * shots)) / (1 + z * z / shots)
    radius = z * math.sqrt(
        failures * (shots - failures) / shots**3 + z * z / (4 * shots**2)
    ) / (1 + z * z / shots)
    return max(0.0, center - radius), min(1.0, center + radius)


def per_qec_cycle(probability, cycles):
    return 1.0 if probability == 1 else -math.expm1(math.log1p(-probability) / cycles)


def breakdown(rows):
    total = sum(int(row["total_cycles"]) for row in rows)
    return {
        name: {
            "cycles": sum(int(row[field]) for row in rows),
            "mean_cycles": sum(int(row[field]) for row in rows) / len(rows),
            "share": sum(int(row[field]) for row in rows) / total,
        }
        for name, field in STAGES.items()
    }


def summarize(p, rows, qec_cycles):
    failures = sum(int(row["logical_failure"]) for row in rows)
    word = failures / len(rows)
    word_low, word_high = wilson(failures, len(rows))
    clocks = [int(row["total_cycles"]) for row in rows]
    statuses = Counter(row["status"] for row in rows)
    selected = Counter(
        int(row["selected"]) for row in rows if row["status"] != "bp_converged"
    )
    return {
        "p": p,
        "shots": len(rows),
        "failures": failures,
        "word_failure_probability": word,
        "word_failure_ci95_low": word_low,
        "word_failure_ci95_high": word_high,
        "logical_failure_rate_per_qec_cycle": per_qec_cycle(word, qec_cycles),
        "logical_rate_ci95_low": per_qec_cycle(word_low, qec_cycles),
        "logical_rate_ci95_high": per_qec_cycle(word_high, qec_cycles),
        "bp_converged": statuses["bp_converged"],
        "osd_solved": statuses["osd_solved"],
        "osd_inconsistent": statuses["osd_inconsistent"],
        "status_counts": dict(statuses),
        "osd_prefix_counts": dict(selected),
        "decoder_clock_cycles_total": sum(clocks),
        "decoder_clock_cycles_mean": statistics.fmean(clocks),
        "decoder_clock_cycles_median": statistics.median(clocks),
        "decoder_clock_cycles_p95": percentile(clocks, 0.95),
        "decoder_clock_cycles_max": max(clocks),
        "timing": breakdown(rows),
    }


def plot_rate(axis, records):
    x = [row["p"] for row in records]
    rates = [row["logical_failure_rate_per_qec_cycle"] for row in records]
    low = [row["logical_rate_ci95_low"] for row in records]
    high = [row["logical_rate_ci95_high"] for row in records]
    measured = [i for i, value in enumerate(rates) if value > 0]
    if measured:
        axis.errorbar(
            [x[i] for i in measured], [rates[i] for i in measured],
            yerr=([rates[i] - low[i] for i in measured],
                  [high[i] - rates[i] for i in measured]),
            fmt="o-", capsize=3, label="estimate with Wilson 95% CI",
        )
    zero = [i for i, value in enumerate(rates) if value == 0]
    if zero:
        axis.scatter(
            [x[i] for i in zero], [high[i] for i in zero], marker="v",
            label="95% upper bound (zero failures)",
        )
    axis.set(xscale="log", yscale="log",
             ylabel="logical failure rate / QEC cycle")
    axis.grid(True, which="both", alpha=0.25)
    axis.legend()


def write_plots(records, overall, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    title = f"BB144 Z-check BP + OSD-0, {records[0]['shots']:,} shots/p"
    figure, axis = plt.subplots(figsize=(6.4, 4.2))
    plot_rate(axis, records)
    axis.set(xlabel="physical error probability p", title=title)
    figure.tight_layout()
    figure.savefig(output / "logical_failure_rate.png", dpi=180)
    plt.close(figure)

    figure, axes = plt.subplots(2, 1, figsize=(6.6, 7.4), sharex=True)
    plot_rate(axes[0], records)
    x = [row["p"] for row in records]
    axes[1].plot(x, [row["decoder_clock_cycles_mean"] for row in records],
                 "o-", label="mean")
    axes[1].plot(x, [row["decoder_clock_cycles_p95"] for row in records],
                 "s--", label="p95")
    axes[1].set(xscale="log", xlabel="physical error probability p",
                ylabel="decoder clocks / shot")
    axes[1].grid(True, which="both", alpha=0.25)
    axes[1].legend()
    figure.suptitle(
        f"{title}\n{overall['decoder_clock_cycles_total']:,} aggregate decoder clocks; "
        f"{overall['simulation_wall_seconds'] / 60:.1f} min RTL wall time"
    )
    figure.tight_layout()
    figure.savefig(output / "logical_failure_and_cycles.png", dpi=180)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("sweep", type=Path)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    with args.raw.open(newline="") as stream:
        raw = list(csv.DictReader(stream))
    sweep = json.loads(args.sweep.read_text())
    run = json.loads(args.run.read_text())
    if not raw:
        raise ValueError("raw result CSV is empty")
    for row in raw:
        if sum(int(row[field]) for field in STAGES.values()) != int(row["total_cycles"]):
            raise ValueError("timing stages do not sum to total_cycles")

    grouped = {}
    for row in raw:
        grouped.setdefault(float(row["p"]), []).append(row)
    expected = sorted(map(float, sweep["sampling"]["p_values"]))
    shots_per_p = int(sweep["sampling"]["shots_per_p"])
    if sorted(grouped) != expected:
        raise ValueError("raw and declared probability points differ")
    for p, rows in grouped.items():
        if len(rows) != shots_per_p or {int(row["shot"]) for row in rows} != set(range(shots_per_p)):
            raise ValueError(f"p={p}: incomplete or duplicate shot records")

    qec_cycles = int(sweep["code"]["cycles"])
    records = [summarize(p, grouped[p], qec_cycles) for p in expected]
    all_clocks = [int(row["total_cycles"]) for row in raw]
    overall = {
        "shots": len(raw),
        "probability_points": len(records),
        "qec_cycles_per_shot": qec_cycles,
        "decoder_clock_cycles_total": sum(all_clocks),
        "decoder_clock_cycles_mean": statistics.fmean(all_clocks),
        "simulation_wall_seconds": float(run["wall_seconds"]),
        "simulation_shots_per_second": float(run["shots_per_second"]),
        "timing": breakdown(raw),
    }
    report = {
        "schema": "chipsldpc.bb144-progressive-osd0-sweep.v1",
        "logical_failure": (
            "unsuccessful decoder status or any mismatch among the 12 "
            "Z-check-sector logical observables"
        ),
        "logical_rate": "1 - (1 - word_failure_probability)^(1 / qec_cycles_per_shot)",
        "cycle_accounting": (
            "sum of measured end-to-end architecture clocks across shots; parallel "
            "Verilator wall time is reported separately"
        ),
        "overall": overall,
        "records": records,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")

    flat = [
        {key: value for key, value in record.items()
         if key not in {"status_counts", "osd_prefix_counts", "timing"}}
        for record in records
    ]
    with (args.output / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=flat[0])
        writer.writeheader()
        writer.writerows(flat)
    with (args.output / "timing.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("p", "stage", "cycles", "mean_cycles", "share"))
        for p, timing in [("all", overall["timing"])] + [
                (record["p"], record["timing"]) for record in records]:
            for stage, values in timing.items():
                writer.writerow((p, stage, values["cycles"],
                                 values["mean_cycles"], values["share"]))

    write_plots(records, overall, args.output)
    print("p       shots failures P_word      p_L/QEC     total_clocks mean_clocks")
    for row in records:
        print(f"{row['p']:<7g} {row['shots']:>5} {row['failures']:>8} "
              f"{row['word_failure_probability']:<11.6g} "
              f"{row['logical_failure_rate_per_qec_cycle']:<11.6g} "
              f"{row['decoder_clock_cycles_total']:>12} "
              f"{row['decoder_clock_cycles_mean']:>11.2f}")
    print(f"PASS: {len(raw)} shots, {overall['decoder_clock_cycles_total']} total decoder "
          f"clocks; results: {args.output}")


if __name__ == "__main__":
    main()
