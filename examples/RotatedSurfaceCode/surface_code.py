#!/usr/bin/env python3
"""Generate one Stim surface-code problem and record its logical outcome."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import stim


DISTANCES = (3, 5, 7)
P = 0.05
PRIOR_BITS = 4
PRIOR_SCALE = 2


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def dem_problem(model) -> tuple[list[list[int]], list[list[int]], list[float]]:
    """Match systolicLDPC's parity-preserving DEM column construction."""
    effects = {}
    for instruction in model.flattened():
        if instruction.type in {"detector", "logical_observable"}:
            continue
        if instruction.type != "error":
            raise NotImplementedError(f"unsupported DEM instruction: {instruction.type}")
        detectors, observables = set(), set()
        for target in instruction.targets_copy():
            if target.is_relative_detector_id():
                detectors.symmetric_difference_update((target.val,))
            elif target.is_logical_observable_id():
                observables.symmetric_difference_update((target.val,))
            elif not target.is_separator():
                raise ValueError(f"unsupported DEM target: {target}")
        if not detectors and not observables:
            continue
        probability = float(instruction.args_copy()[0])
        if probability == 0.0:
            continue
        key = frozenset(detectors), frozenset(observables)
        previous = effects.get(key, 0.0)
        effects[key] = previous * (1.0 - probability) + probability * (1.0 - previous)

    rows = [[] for _ in range(model.num_detectors)]
    logicals = [[] for _ in range(model.num_observables)]
    probabilities = []
    for column, ((detectors, observables), probability) in enumerate(effects.items()):
        for detector in detectors:
            rows[detector].append(column)
        for observable in observables:
            logicals[observable].append(column)
        probabilities.append(probability)
    return rows, logicals, probabilities


def generate(distance: int, output: Path, iterations: int, shot: int, seed: int) -> None:
    if distance not in DISTANCES or iterations < 1 or shot < 0 or seed < 0:
        raise ValueError(
            "distance must be 3, 5, or 7; iterations positive; shot and seed nonnegative"
        )
    circuit = stim.Circuit.generated(
        "surface_code:rotated_memory_x",
        distance=distance,
        rounds=distance,
        after_clifford_depolarization=P,
        before_round_data_depolarization=P,
        after_reset_flip_probability=P,
        before_measure_flip_probability=P,
    )
    model = circuit.detector_error_model(decompose_errors=True)
    rows, logicals, probabilities = dem_problem(model)
    if not probabilities or any(not 0.0 < probability < 0.5 for probability in probabilities):
        raise ValueError("the unsigned prior ABI requires every DEM probability in (0, 0.5)")
    llr = [math.log((1.0 - probability) / probability) for probability in probabilities]
    prior = [min((1 << PRIOR_BITS) - 1, math.floor(value * PRIOR_SCALE + 0.5)) for value in llr]
    syndromes, observables = circuit.compile_detector_sampler(seed=seed + distance).sample(
        shots=shot + 1, separate_observables=True
    )
    syndrome = [int(bit) for bit in syndromes[shot]]
    actual = [int(bit) for bit in observables[shot]]
    source = output / "stim"
    source.mkdir(parents=True, exist_ok=True)
    (source / "circuit.stim").write_text(str(circuit) + "\n")
    (source / "detector_error_model.dem").write_text(str(model) + "\n")
    save(source / "problem.json", {
        "schema": 1,
        "n": len(probabilities),
        "row_ones": rows,
        "prior": prior,
        "syndrome": syndrome,
        "iterations": iterations,
    })
    save(source / "metadata.json", {
        "schema": "chipsldpc.rotated_surface.v1",
        "stim_version": stim.__version__,
        "circuit": {"generator": "surface_code:rotated_memory_x", "distance": distance,
                    "rounds": distance, "physical_error_rate": P,
                    "sampler_seed": seed + distance, "sample_count": shot + 1, "shot": shot},
        "graph": {"m": len(rows), "n": len(probabilities),
                  "e": sum(map(len, rows)), "logical_rows": len(logicals)},
        "quantization": {"definition": "log((1-p)/p)", "bits": PRIOR_BITS,
                         "scale": PRIOR_SCALE, "rounding": "nearest_ties_away",
                         "overflow": "unsigned_saturate"},
        "logical_ones": logicals,
        "actual_observables": actual,
        "stim_priors": probabilities,
        "prior_llr": llr,
    })
    print(f"d={distance}: m={len(rows)} n={len(probabilities)} e={sum(map(len, rows))}")


def outcome(output: Path, result, correction):
    source = json.loads((output / "stim" / "metadata.json").read_text())
    problem = json.loads((output / "stim" / "problem.json").read_text())
    if len(correction) != problem["n"] or any(bit not in (0, 1) for bit in correction):
        raise ValueError("RTL corrections disagree with the Stim graph")
    residual = [problem["syndrome"][row] ^ (sum(correction[v] for v in columns) & 1)
                for row, columns in enumerate(problem["row_ones"])]
    predicted = [sum(correction[v] for v in columns) & 1 for columns in source["logical_ones"]]
    if (not any(residual)) != result["converged"]:
        raise AssertionError("recorded RTL result is internally inconsistent")
    logical_match = predicted == source["actual_observables"] if result["converged"] else None
    return source, residual, predicted, logical_match


def check(output: Path) -> None:
    result = json.loads((output / "rtl" / "result.json").read_text())
    source, residual, predicted, logical_match = outcome(output, result, result["correction"])
    if residual != result["residual"]:
        raise AssertionError("recorded RTL residual is internally inconsistent")
    save(output / "logical_result.json", {
        "converged": result["converged"],
        "predicted_observables": predicted if result["converged"] else None,
        "actual_observables": source["actual_observables"],
        "logical_match": logical_match,
        "logical_failure": not result["converged"] or not logical_match,
    })
    print(f"logical result: converged={result['converged']} match={logical_match}")


def report(output: Path) -> None:
    path = output / "result.json"
    result = json.loads(path.read_text())
    if set(result) != {"soft_outputs", "corrections", "converged"}:
        raise ValueError("unexpected compact RTL result fields")
    if len(result["soft_outputs"]) != len(result["corrections"]):
        raise ValueError("soft output and correction lengths disagree")
    _, _, _, logical_match = outcome(output, result, result["corrections"])
    logical_failure = not result["converged"] or not logical_match
    save(path, {
        "soft_outputs": result["soft_outputs"],
        "corrections": result["corrections"],
        "converged": result["converged"],
        "logical_failure": logical_failure,
    })
    print(f"result: converged={result['converged']} logical_failure={logical_failure}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("generate")
    build.add_argument("distance", type=int, choices=DISTANCES)
    build.add_argument("output", type=Path)
    build.add_argument("--iterations", type=int, default=8)
    build.add_argument("--shot", type=int, default=1)
    build.add_argument("--seed", type=int, default=1)
    verify = commands.add_parser("check")
    verify.add_argument("output", type=Path)
    compact = commands.add_parser("report")
    compact.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "generate":
        generate(args.distance, args.output, args.iterations, args.shot, args.seed)
    elif args.command == "check":
        check(args.output)
    else:
        report(args.output)


if __name__ == "__main__":
    main()
