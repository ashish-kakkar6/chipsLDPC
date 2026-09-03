#!/usr/bin/env python3
"""Summarize one BB144 progressive-OSD0 RTL benchmark."""

import csv
import json
import math
import statistics
import sys
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


def breakdown(rows):
    total_cycles = sum(int(row["total_cycles"]) for row in rows)
    return {
        name: {
            "cycles": sum(int(row[field]) for row in rows),
            "mean_cycles": sum(int(row[field]) for row in rows) / len(rows),
            "share": sum(int(row[field]) for row in rows) / total_cycles,
        }
        for name, field in STAGES.items()
    }


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: report.py <shots.csv> <output-directory>")
    source, output = Path(sys.argv[1]), Path(sys.argv[2])
    with source.open() as stream:
        rows = list(csv.DictReader(stream))
    if not rows or len({row["p"] for row in rows}) != 1:
        raise ValueError("expected one nonempty p point")
    for row in rows:
        if sum(int(row[field]) for field in STAGES.values()) != int(row["total_cycles"]):
            raise ValueError("timing stages do not sum to total_cycles")

    shots = len(rows)
    failures = sum(int(row["logical_failure"]) for row in rows)
    word = failures / shots
    low, high = wilson(failures, shots)
    per_cycle = lambda value: 1 - (1 - value) ** (1 / 12)
    totals = [int(row["total_cycles"]) for row in rows]
    eligible = [int(row["eligible"]) for row in rows]
    fallback = [row for row in rows if row["status"] != "bp_converged"]
    report = {
        "schema": "chipsldpc.bb144-progressive-osd0-report.v1",
        "p": float(rows[0]["p"]),
        "shots": shots,
        "logical_failure": "unsuccessful status or mismatch among 12 Z-check-sector observables",
        "failures": failures,
        "word_failure_probability": word,
        "logical_failure_rate_per_cycle": per_cycle(word),
        "ci95_per_cycle": [per_cycle(low), per_cycle(high)],
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "osd_prefix_counts": dict(Counter(row["selected"] for row in fallback)),
        "latency_cycles": {
            "min": min(totals), "median": statistics.median(totals),
            "mean": statistics.fmean(totals), "p95": percentile(totals, 0.95),
            "max": max(totals),
        },
        "ranked_columns": {
            "mean": statistics.fmean(eligible), "median": statistics.median(eligible),
            "p95": percentile(eligible, 0.95), "max": max(eligible),
        },
        "timing_all_shots": breakdown(rows),
        "timing_fallback_shots": breakdown(fallback) if fallback else {},
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    with (output / "timing.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("scope", "stage", "cycles", "mean_cycles", "share"))
        for scope, values in (("all", report["timing_all_shots"]),
                              ("fallback", report["timing_fallback_shots"])):
            for stage, values_by_stage in values.items():
                writer.writerow((scope, stage, *values_by_stage.values()))
    print(json.dumps({key: report[key] for key in (
        "p", "shots", "failures", "word_failure_probability",
        "logical_failure_rate_per_cycle", "status_counts", "latency_cycles",
        "osd_prefix_counts", "ranked_columns",
    )}, indent=2))


if __name__ == "__main__":
    main()
