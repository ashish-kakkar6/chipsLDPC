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


def histogram_percentile(counts, probability):
    target = math.ceil(probability * sum(counts.values()))
    seen = 0
    for value, count in sorted(counts.items()):
        seen += count
        if seen >= target:
            return value


def histogram_median(counts):
    size = sum(counts.values())
    targets = {(size - 1) // 2, size // 2}
    values = []
    seen = 0
    for value, count in sorted(counts.items()):
        values.extend(value for target in targets if seen <= target < seen + count)
        seen += count
    return statistics.fmean(values)


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


def leg_trace(row):
    if "leg_trace" not in row:
        return []
    try:
        trace = [tuple(map(int, item.split(":")))
                 for item in row["leg_trace"].split("|") if item]
    except ValueError as error:
        raise ValueError("malformed Relay leg_trace") from error
    if (len(trace) != int(row["legs_executed"])
            or any(len(item) != 4 for item in trace)
            or [item[0] for item in trace] != list(range(len(trace)))
            or any(iterations < 1 or cycles < 1 or converged not in (0, 1)
                   for _, iterations, cycles, converged in trace)
            or sum(item[1] for item in trace) != int(row["iterations"])
            or sum(item[2] for item in trace) != int(row["bp_cycles"])
            or sum(item[3] for item in trace) != int(row["solutions_found"])):
        raise ValueError("Relay leg_trace violates decoder totals")
    return trace


def observable_mismatch(row):
    return int(row["predicted_observables"], 0) != int(row["actual_observables"], 0)


def summarize(p, rows, qec_cycles):
    failures = sum(int(row["logical_failure"]) for row in rows)
    word = failures / len(rows)
    word_low, word_high = wilson(failures, len(rows))
    clocks = [int(row["total_cycles"]) for row in rows]
    statuses = Counter(row["status"] for row in rows)
    converged = [row for row in rows if row["status"] == "bp_converged"]
    converged_failures = sum(observable_mismatch(row) for row in converged)
    if converged:
        converged_word = converged_failures / len(converged)
        converged_low, converged_high = wilson(converged_failures, len(converged))
        converged_rate = per_qec_cycle(converged_word, qec_cycles)
        converged_rate_low = per_qec_cycle(converged_low, qec_cycles)
        converged_rate_high = per_qec_cycle(converged_high, qec_cycles)
    else:
        converged_word = converged_low = converged_high = None
        converged_rate = converged_rate_low = converged_rate_high = None
    selected = Counter(int(row["selected"]) for row in rows if int(row["selected"]) > 0)
    result = {
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
        "bp_nonconverged": statuses["bp_nonconverged"],
        "bp_converged_logical_failures": converged_failures,
        "bp_converged_word_failure_probability": converged_word,
        "bp_converged_word_failure_ci95_low": converged_low,
        "bp_converged_word_failure_ci95_high": converged_high,
        "bp_converged_logical_failure_rate_per_qec_cycle": converged_rate,
        "bp_converged_logical_rate_ci95_low": converged_rate_low,
        "bp_converged_logical_rate_ci95_high": converged_rate_high,
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
    if "legs_executed" in rows[0]:
        legs = [int(row["legs_executed"]) for row in rows]
        solutions = [int(row["solutions_found"]) for row in rows]
        result.update({
            "relay_legs_mean": statistics.fmean(legs),
            "relay_legs_median": statistics.median(legs),
            "relay_legs_p95": percentile(legs, 0.95),
            "relay_legs_max": max(legs),
            "relay_solutions_found_mean": statistics.fmean(solutions),
            "relay_solutions_found_max": max(solutions),
        })
    if "leg_trace" in rows[0]:
        cycles = Counter()
        count = total = 0
        initial_count = initial_total = subsequent_count = subsequent_total = 0
        for row in rows:
            for index, _, leg_cycles, _ in leg_trace(row):
                cycles[leg_cycles] += 1
                count += 1
                total += leg_cycles
                if index == 0:
                    initial_count += 1
                    initial_total += leg_cycles
                else:
                    subsequent_count += 1
                    subsequent_total += leg_cycles
        result.update({
            "relay_leg_clock_cycles_total": total,
            "relay_leg_clock_cycles_mean": total / count,
            "relay_leg_clock_cycles_median": histogram_median(cycles),
            "relay_leg_clock_cycles_p95": histogram_percentile(cycles, 0.95),
            "relay_leg_clock_cycles_max": max(cycles),
            "relay_initial_leg_clock_cycles_mean": initial_total / initial_count,
            "relay_subsequent_leg_clock_cycles_mean": (
                subsequent_total / subsequent_count if subsequent_count else None
            ),
        })
    return result


def plot_rate(
        axis, records, *,
        rate_key="logical_failure_rate_per_qec_cycle",
        low_key="logical_rate_ci95_low",
        high_key="logical_rate_ci95_high",
        ylabel="logical failure rate / QEC cycle",
        estimate_label="estimate with Wilson 95% CI"):
    x = [row["p"] for row in records]
    rates = [row[rate_key] for row in records]
    low = [row[low_key] for row in records]
    high = [row[high_key] for row in records]
    measured = [i for i, value in enumerate(rates) if value is not None and value > 0]
    if measured:
        axis.errorbar(
            [x[i] for i in measured], [rates[i] for i in measured],
            yerr=([rates[i] - low[i] for i in measured],
                  [high[i] - rates[i] for i in measured]),
            fmt="o-", capsize=3, label=estimate_label,
        )
    zero = [i for i, value in enumerate(rates) if value == 0]
    if zero:
        axis.scatter(
            [x[i] for i in zero], [high[i] for i in zero], marker="v",
            label="95% upper bound (zero failures)",
        )
    axis.set(xscale="log", yscale="log",
             ylabel=ylabel)
    axis.grid(True, which="both", alpha=0.25)
    if measured or zero:
        axis.legend()
    else:
        axis.text(0.5, 0.5, "no converged samples", ha="center", va="center",
                  transform=axis.transAxes)


def write_plots(records, overall, output, label):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    title = f"{label}, {records[0]['shots']:,} shots/p"
    figure, axis = plt.subplots(figsize=(6.4, 4.2))
    plot_rate(axis, records)
    axis.set(xlabel="physical error probability p", title=title)
    figure.tight_layout()
    figure.savefig(output / "logical_failure_rate.png", dpi=180)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(6.4, 4.2))
    plot_rate(
        axis, records,
        rate_key="bp_converged_logical_failure_rate_per_qec_cycle",
        low_key="bp_converged_logical_rate_ci95_low",
        high_key="bp_converged_logical_rate_ci95_high",
        ylabel="logical failure rate / QEC cycle\nconditioned on BP convergence",
        estimate_label="conditional estimate with Wilson 95% CI",
    )
    axis.set(
        xlabel="physical error probability p",
        title=f"{label}, converged BP samples only\n"
              f"{records[0]['shots']:,} generated shots/p; conditional denominator varies",
    )
    figure.tight_layout()
    figure.savefig(output / "logical_failure_rate_converged_only.png", dpi=180)
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


def write_relay_leg_outputs(rows, output, label):
    if "leg_trace" not in rows[0]:
        return None
    fields = ("p", "shot", "leg", "iterations", "cycles", "converged")
    grouped = {}
    by_p_cycles = {}
    total_legs = total_cycles = 0
    with (output / "relay_leg_timing.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        for row in rows:
            p, shot = float(row["p"]), int(row["shot"])
            for index, iterations, cycles, converged in leg_trace(row):
                writer.writerow((p, shot, index + 1, iterations, cycles, converged))
                bucket = grouped.setdefault(
                    (p, index + 1), [0, 0, Counter(), Counter()],
                )
                bucket[0] += 1
                bucket[1] += converged
                bucket[2][iterations] += 1
                bucket[3][cycles] += 1
                by_p_cycles.setdefault(p, Counter())[cycles] += 1
                total_legs += 1
                total_cycles += cycles

    if not total_legs:
        raise ValueError("Relay leg trace is empty")
    summary = []
    for (p, leg), (executions, converged, iterations, cycles) in sorted(grouped.items()):
        summary.append({
            "p": p, "leg": leg, "executions": executions,
            "converged": converged,
            "convergence_rate": converged / executions,
            "mean_iterations": (
                sum(value * count for value, count in iterations.items()) / executions
            ),
            "p95_iterations": histogram_percentile(iterations, 0.95),
            "mean_cycles": sum(value * count for value, count in cycles.items()) / executions,
            "p95_cycles": histogram_percentile(cycles, 0.95), "max_cycles": max(cycles),
        })
    with (output / "relay_leg_timing_summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=summary[0])
        writer.writeheader()
        writer.writerows(summary)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    probabilities = sorted(by_p_cycles)
    figure, axes = plt.subplots(2, 1, figsize=(7.2, 7.6))
    axes[0].plot(probabilities, [sum(value * count for value, count in by_p_cycles[p].items()) /
                                sum(by_p_cycles[p].values()) for p in probabilities],
                 "o-", label="mean")
    axes[0].plot(probabilities, [histogram_percentile(by_p_cycles[p], 0.95)
                                 for p in probabilities],
        "s--", label="p95")
    axes[0].set(xscale="log", xlabel="physical error probability p",
                ylabel="decoder clocks / executed leg")
    axes[0].grid(True, which="both", alpha=0.25)
    axes[0].legend()

    for p in probabilities:
        rows = [row for row in summary if row["p"] == p]
        axes[1].plot([row["leg"] for row in rows],
                     [row["mean_cycles"] for row in rows], label=f"p={p:g}")
    axes[1].set(xlabel="Relay leg number (initial leg = 1)",
                ylabel="mean decoder clocks")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(ncol=2)
    figure.suptitle(f"{label}: measured per-leg decoder clocks")
    figure.tight_layout()
    figure.savefig(output / "relay_leg_timing.png", dpi=180)
    plt.close(figure)
    return {"count": total_legs, "cycles": total_cycles}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("sweep", type=Path)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--label", default="BB144 Z-check decoder")
    parser.add_argument("--decoder-config", type=Path)
    args = parser.parse_args()

    with args.raw.open(newline="") as stream:
        raw = list(csv.DictReader(stream))
    sweep = json.loads(args.sweep.read_text())
    run = json.loads(args.run.read_text())
    if not raw:
        raise ValueError("raw result CSV is empty")
    args.output.mkdir(parents=True, exist_ok=True)
    for row in raw:
        if sum(int(row[field]) for field in STAGES.values()) != int(row["total_cycles"]):
            raise ValueError("timing stages do not sum to total_cycles")
    leg_stats = write_relay_leg_outputs(raw, args.output, args.label)

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
    if leg_stats:
        overall.update({
            "relay_legs_traced": leg_stats["count"],
            "relay_leg_clock_cycles_total": leg_stats["cycles"],
            "relay_leg_clock_cycles_mean": leg_stats["cycles"] / leg_stats["count"],
        })
    report = {
        "schema": "chipsldpc.bb144-decoder-sweep.v1",
        "decoder": args.label,
        "logical_failure": (
            "unsuccessful decoder status or any mismatch among the 12 "
            "Z-check-sector logical observables"
        ),
        "bp_converged_logical_failure": (
            "any mismatch among the 12 logical observables, conditioned on "
            "status=bp_converged; nonconverged shots are excluded from both "
            "the numerator and denominator"
        ),
        "logical_rate": "1 - (1 - word_failure_probability)^(1 / qec_cycles_per_shot)",
        "cycle_accounting": (
            "sum of measured end-to-end architecture clocks across shots; parallel "
            "Verilator wall time is reported separately"
        ),
        "overall": overall,
        "records": records,
    }
    if args.decoder_config:
        report["decoder_configuration"] = json.loads(args.decoder_config.read_text())
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

    write_plots(records, overall, args.output, args.label)
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
