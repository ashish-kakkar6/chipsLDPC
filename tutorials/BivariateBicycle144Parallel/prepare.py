#!/usr/bin/env python3
"""Stream the BB144 reference preparation without buffering every shot."""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "examples" / "BivariateBicycle144"))
import bb144 as bb  # noqa: E402


def reduce_batch(detectors, observables, raw_rows, raw_logicals, fixed, kept_checks):
    """Vectorized equivalent of bb144.reduce_sample for one probability point."""
    reduced = detectors[:, kept_checks].copy()
    check_index = {check: index for index, check in enumerate(kept_checks)}
    for column, source_check in fixed.items():
        value = detectors[:, source_check]
        for check, row in enumerate(raw_rows):
            if column in row and check in check_index:
                reduced[:, check_index[check]] ^= value
        for logical, row in enumerate(raw_logicals):
            if column in row:
                observables[:, logical] ^= value
    return reduced.astype(np.uint8), observables.astype(np.uint8)


def prepare(output, p_values, shots, iterations, seed):
    if shots < 1 or iterations < 1 or any(not 0 < p < 0.02 for p in p_values):
        raise ValueError("shots and iterations must be positive; require 0 < p < 0.02")
    config = bb.upstream_config()
    output.mkdir(parents=True, exist_ok=True)
    benchmark_path = output / "benchmark.txt"
    temporary = benchmark_path.with_suffix(".tmp")
    canonical_keys = reduced = raw_m = benchmark = None
    priors = []
    try:
        benchmark = temporary.open("w")
        for index, p in enumerate(p_values):
            circuits, dem, keys, probabilities = bb.combined_model(config, p)
            if canonical_keys is None:
                canonical_keys, raw_m = keys, dem.num_detectors
                (output / "x_sector.stim").write_text(str(circuits[0]) + "\n")
                (output / "z_sector.stim").write_text(str(circuits[1]) + "\n")
                reduced = bb.reduce_degree_one(keys, raw_m)
                raw_rows, raw_logicals, fixed, kept_checks, kept_variables, rows, logicals = reduced
                if any(not row for row in rows) or any(not ds for ds, _ in keys):
                    raise ValueError("the static decoder requires nonempty rows and columns")
                benchmark.write(f"{len(rows)} {len(kept_variables)} 24 {iterations} 12 "
                                f"{len(p_values)} {bb.PRIOR_BITS} {bb.CONTROL_MAX}\n")
                for row in logicals:
                    benchmark.write(" ".join(map(str, (len(row), *row))) + "\n")
            elif keys != canonical_keys or dem.num_detectors != raw_m:
                raise ValueError("DEM topology changed across the p sweep")

            tag = f"p{p:.4f}".replace(".", "_")
            (output / f"{tag}.dem").write_text(str(dem) + "\n")
            quantized = bb.quantize(probabilities)
            prior = [quantized[column] for column in kept_variables]
            priors.append(prior)
            detectors, observables = bb.sample_physical(config, p, shots, seed + index)
            first_observables = observables[0].copy()
            reduced_syndrome, reduced_observables = reduce_batch(
                detectors, observables, raw_rows, raw_logicals, fixed, kept_checks)
            expected = bb.reduce_sample(detectors[0], first_observables, raw_rows,
                                        raw_logicals, fixed, kept_checks)
            if expected != (reduced_syndrome[0].tolist(), reduced_observables[0].tolist()):
                raise AssertionError("vectorized reduction differs from scalar reference")

            benchmark.write(f"{p:.12g} {shots}\n")
            benchmark.write(" ".join(map(str, prior)) + "\n")
            np.savetxt(benchmark, np.hstack((reduced_syndrome, reduced_observables)), fmt="%d")
            bb.save(output / "verify" / tag / "problem.json", {
                "schema": 1, "n": len(kept_variables), "row_ones": rows,
                "prior": prior, "syndrome": reduced_syndrome[0].tolist(),
                "iterations": iterations,
            })
            bb.save(output / "verify" / tag / "actual.json", {
                "p": p, "observables": reduced_observables[0].tolist(),
            })
            print(f"prepared p={p:.4g}: {shots} shots", flush=True)
    finally:
        if benchmark:
            benchmark.close()
    os.replace(temporary, benchmark_path)

    raw_rows, raw_logicals, fixed, kept_checks, kept_variables, rows, logicals = reduced
    sweep = {
        "schema": "chipsldpc.bb144.v1", "tools": {"stim": bb.stim.__version__},
        "upstream": {"url": "https://github.com/sbravyi/BivariateBicycleCodes",
                     "commit": config["commit"]},
        "code": {"n": 144, "k": 12, "d": 12, "cycles": config["num_cycles"],
                 "ell": config["ell"], "m": config["m"],
                 "a": [config["a1"], config["a2"], config["a3"]],
                 "b": [config["b1"], config["b2"], config["b3"]]},
        "decoder": {"iterations": iterations, "quantization_bits": bb.PRIOR_BITS,
                    "prior_scale": bb.PRIOR_SCALE},
        "sampling": {"p_values": list(p_values), "shots_per_p": shots, "seed": seed,
                     "model": "one correlated circuit-level Pauli process"},
        "dem": {"m": len(rows), "n": len(kept_variables), "e": sum(map(len, rows)),
                "row_ones": rows, "logical_ones": logicals, "priors": priors,
                "factorization": "independent X/Z sector DEMs",
                "exact_preprocessing": {
                    "raw_m": raw_m, "raw_n": len(canonical_keys),
                    "fixed_variable_detector": [[column, check]
                                                for column, check in fixed.items()]}},
    }
    bb.save(output / "sweep.json", sweep)
    print(f"PASS m={len(rows)} n={len(kept_variables)} shots={shots * len(p_values)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--p", type=float, nargs="+", default=bb.DEFAULT_P)
    parser.add_argument("--shots", type=int, default=10000)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--seed", type=int, default=14412)
    args = parser.parse_args()
    prepare(args.output, args.p, args.shots, args.iterations, args.seed)


if __name__ == "__main__":
    main()
