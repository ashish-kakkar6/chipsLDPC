#!/usr/bin/env python3
"""Summarize BB144 logical failures, cycle lifetimes, and RTL wall time."""

import argparse
import csv
import json
import math
from pathlib import Path


def wilson(failures, shots):
    z = 1.959963984540054
    center = (failures / shots + z * z / (2 * shots)) / (1 + z * z / shots)
    radius = z * math.sqrt(failures * (shots - failures) / shots**3
                           + z * z / (4 * shots**2)) / (1 + z * z / shots)
    return max(0.0, center - radius), min(1.0, center + radius)


def reciprocal(value):
    return 1 / value if value else None


def analyze(raw_path, sweep_path, manifest_path, run_path, output):
    import matplotlib.pyplot as plt
    import numpy as np

    with raw_path.open() as stream:
        raw = list(csv.DictReader(stream))
    if not raw:
        raise ValueError("raw result CSV is empty")
    sweep = json.loads(sweep_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    timing = json.loads(run_path.read_text())
    qec_cycles = manifest["metrics"]["qec_cycles_per_shot"]
    decoder_clocks = manifest["metrics"]["decoder_clock_cycles_per_shot"]
    grouped = {}
    for row in raw:
        grouped.setdefault(float(row["p"]), []).append(row)

    records = []
    for p, rows in sorted(grouped.items()):
        shots = len(rows)
        failures = sum(int(row["logical_failure"]) for row in rows)
        converged = sum(int(row["converged"]) for row in rows)
        word = failures / shots
        word_lo, word_hi = wilson(failures, shots)
        rate = 1 - (1 - word) ** (1 / qec_cycles)
        rate_lo = 1 - (1 - word_lo) ** (1 / qec_cycles)
        rate_hi = 1 - (1 - word_hi) ** (1 / qec_cycles)
        records.append({
            "p": p, "shots": shots, "failures": failures,
            "converged": converged, "convergence_probability": converged / shots,
            "word_failure_probability": word,
            "logical_failure_rate_per_qec_cycle": rate,
            "logical_rate_ci95_low": rate_lo, "logical_rate_ci95_high": rate_hi,
            "expected_qec_cycles_to_failure": reciprocal(rate),
            "qec_cycles_ci95_low": reciprocal(rate_hi),
            "qec_cycles_ci95_high": reciprocal(rate_lo),
            "decoder_clock_cycles_per_shot": decoder_clocks,
            "expected_decoder_clocks_per_failure": decoder_clocks / word if word else None,
            "decoder_clocks_ci95_low": decoder_clocks / word_hi,
            "decoder_clocks_ci95_high": decoder_clocks / word_lo if word_lo else None,
        })

    output.mkdir(parents=True, exist_ok=True)
    metadata = {
        "code": sweep["code"], "dem": {key: sweep["dem"][key] for key in ("m", "n", "e")},
        "decoder": sweep["decoder"], "qec_cycles_per_shot": qec_cycles,
        "decoder_clock_cycles_per_shot": decoder_clocks,
        "clock_formula": "1 reset + 1 load + 2 clocks per fixed iteration",
        "timing": timing,
        "logical_failure": "any mismatch among the 24 logical observables",
        "records": records,
    }
    (output / "results.json").write_text(json.dumps(metadata, indent=2) + "\n")
    with (output / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0])
        writer.writeheader()
        writer.writerows(records)

    def values(key):
        return np.array([row[key] if row[key] else np.nan for row in records])
    x = values("p")
    rate, rate_lo, rate_hi = map(values, ("logical_failure_rate_per_qec_cycle",
                                          "logical_rate_ci95_low", "logical_rate_ci95_high"))
    qec_life, qec_lo, qec_hi = map(values, ("expected_qec_cycles_to_failure",
                                             "qec_cycles_ci95_low", "qec_cycles_ci95_high"))
    clock_life, clock_lo, clock_hi = map(values, ("expected_decoder_clocks_per_failure",
                                                   "decoder_clocks_ci95_low",
                                                   "decoder_clocks_ci95_high"))

    fig, axis = plt.subplots(figsize=(6.4, 4.2))
    axis.errorbar(x, rate, yerr=(rate - rate_lo, rate_hi - rate), fmt="o-", capsize=3)
    axis.set(xlabel="physical error probability p",
             ylabel="logical failure rate / QEC cycle", xscale="log", yscale="log",
             title=f"[[144,12,12]] BB decoder, {records[0]['shots']:,} shots/p")
    axis.grid(True, which="both", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output / "logical_failure_rate.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(6.6, 7.4), sharex=True)
    axes[0].errorbar(x, rate, yerr=(rate - rate_lo, rate_hi - rate), fmt="o-", capsize=3)
    axes[0].set(ylabel="logical failure rate / QEC cycle", yscale="log")
    axes[1].errorbar(x, qec_life, yerr=(qec_life - qec_lo, qec_hi - qec_life),
                     fmt="o-", capsize=3, label="QEC syndrome cycles")
    axes[1].errorbar(x, clock_life, yerr=(clock_life - clock_lo, clock_hi - clock_life),
                     fmt="s--", capsize=3, label="decoder clocks of work")
    axes[1].set(xlabel="physical error probability p", ylabel="expected cycles to failure",
                xscale="log", yscale="log")
    axes[1].legend()
    for axis in axes:
        axis.grid(True, which="both", alpha=0.25)
    fig.suptitle(f"[[144,12,12]] BB decoder: {records[0]['shots']:,} shots/p, "
                 f"{timing['wall_seconds'] / 60:.1f} min RTL wall time")
    fig.tight_layout()
    fig.savefig(output / "logical_failure_and_cycles.png", dpi=180)
    plt.close(fig)
    print(f"PASS analyzed {len(raw)} shots; results: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("sweep", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    analyze(args.raw, args.sweep, args.manifest, args.run, args.output)


if __name__ == "__main__":
    main()
