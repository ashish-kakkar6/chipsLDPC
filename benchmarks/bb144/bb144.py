#!/usr/bin/env python3
"""Build the pinned [[144,12,12]] Z-check decoding problem and samples."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import stim
from bposd.css import css_code


HERE = Path(__file__).resolve().parent
UPSTREAM_URL = "https://github.com/sbravyi/BivariateBicycleCodes"
UPSTREAM_COMMIT = "fa77e3333d3ec44c79d8f914dd24c040d1da471b"
DEFAULT_P = (0.005,)
PRIOR_BITS, PRIOR_SCALE = 4, 2
CONTROL_MAX = 7
LOGICAL_COUNT = 12


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def upstream_config() -> dict:
    """Return the circuit parameters pinned to UPSTREAM_COMMIT."""
    return {"ell": 12, "m": 6, "a1": 3, "a2": 1, "a3": 2,
            "b1": 3, "b2": 1, "b3": 2, "num_cycles": 12,
            "sX": ["idle", 1, 4, 3, 5, 0, 2],
            "sZ": [3, 5, 0, 1, 2, 4, "idle"],
            "commit": UPSTREAM_COMMIT}


def code_data(config: dict):
    ell, m = config["ell"], config["m"]
    eye_l, eye_m = np.eye(ell, dtype=np.uint8), np.eye(m, dtype=np.uint8)
    x = [np.kron(np.roll(eye_l, i, axis=1), eye_m) for i in range(ell)]
    y = [np.kron(eye_l, np.roll(eye_m, i, axis=1)) for i in range(m)]
    a_parts = [x[config["a1"]], y[config["a2"]], y[config["a3"]]]
    b_parts = [y[config["b1"]], x[config["b2"]], x[config["b3"]]]
    a, b = np.bitwise_xor.reduce(a_parts), np.bitwise_xor.reduce(b_parts)
    hx, hz = np.hstack((a, b)), np.hstack((b.T, a.T))
    code = css_code(hx, hz)
    lx = code.lx.toarray().astype(np.uint8)
    lz = code.lz.toarray().astype(np.uint8)
    if hx.shape != (72, 144) or hz.shape != (72, 144) or lx.shape != (12, 144):
        raise ValueError("unexpected upstream code dimensions")
    if np.any((hx @ hz.T) & 1) or np.any((lx @ hz.T) & 1) or np.any((lz @ hx.T) & 1):
        raise ValueError("invalid CSS or logical matrices")
    return a_parts, b_parts, lx, lz


def neighbors(parts, offset: int, transpose: bool = False) -> list[list[int]]:
    return [[offset + int(np.flatnonzero(part[:, i] if transpose else part[i])[0])
             for part in parts] for i in range(72)]


def circuit(config: dict, p: float, sector: str) -> stim.Circuit:
    a_parts, b_parts, lx, lz = code_data(config)
    xchecks, left, right, zchecks = range(72), range(72, 144), range(144, 216), range(216, 288)
    data = list(left) + list(right)
    nx = [a + b for a, b in zip(neighbors(a_parts, 72), neighbors(b_parts, 144))]
    nz = [a + b for a, b in zip(neighbors(b_parts, 72, True), neighbors(a_parts, 144, True))]
    c = stim.Circuit()
    c.append("R" if sector == "x" else "RX", data)

    def pairs(checks, table, direction, reverse=False):
        return [q for i, check in enumerate(checks)
                for q in ((table[i][direction], check) if reverse else (check, table[i][direction]))]

    def gate(name, targets, probability, noise=None):
        c.append(name, targets)
        if probability and noise:
            c.append(noise, targets, probability)

    def measure(name, targets, probability, round_index, relevant):
        c.append(name, targets, probability) if probability else c.append(name, targets)
        if relevant:
            for i in range(72):
                records = [stim.target_rec(i - 72)]
                if round_index:
                    records.append(stim.target_rec(i - 216))
                c.append("DETECTOR", records)

    for round_index in range(config["num_cycles"] + 2):
        probability = p if round_index < config["num_cycles"] else 0.0
        gate("RX", xchecks, probability, "Z_ERROR")
        z0 = pairs(zchecks, nz, config["sZ"][0], True)
        gate("CX", z0, probability, "DEPOLARIZE2")
        gate("I", sorted(set(data) - set(z0[::2])), probability, "DEPOLARIZE1")
        c.append("TICK")
        for stage in range(1, 6):
            gate("CX", pairs(xchecks, nx, config["sX"][stage]), probability, "DEPOLARIZE2")
            gate("CX", pairs(zchecks, nz, config["sZ"][stage], True), probability, "DEPOLARIZE2")
            c.append("TICK")
        measure("M", zchecks, probability, round_index, sector == "x")
        x6 = pairs(xchecks, nx, config["sX"][6])
        gate("CX", x6, probability, "DEPOLARIZE2")
        gate("I", sorted(set(data) - set(x6[1::2])), probability, "DEPOLARIZE1")
        c.append("TICK")
        gate("I", data, probability, "DEPOLARIZE1")
        measure("MX", xchecks, probability, round_index, sector == "z")
        gate("R", zchecks, probability, "X_ERROR")
        c.append("TICK")

    logical = lz if sector == "x" else lx
    c.append("M" if sector == "x" else "MX", data)
    for observable, row in enumerate(logical):
        c.append("OBSERVABLE_INCLUDE",
                 [stim.target_rec(int(i) - 144) for i in np.flatnonzero(row)], observable)
    return c


def effects(dem: stim.DetectorErrorModel):
    merged = {}
    for instruction in dem.flattened():
        if instruction.type in {"detector", "logical_observable"}:
            continue
        if instruction.type != "error":
            raise ValueError(f"unsupported DEM instruction {instruction.type}")
        detectors, logicals = [], []
        for target in instruction.targets_copy():
            if target.is_relative_detector_id():
                detectors.append(target.val)
            elif target.is_logical_observable_id():
                logicals.append(target.val)
            elif target.is_separator():
                raise ValueError("decomposed DEM errors are not supported")
        key = tuple(detectors), tuple(logicals)
        probability = float(instruction.args_copy()[0])
        old = merged.get(key, 0.0)
        merged[key] = old * (1 - probability) + probability * (1 - old)
    return merged


def z_check_model(config: dict, p: float):
    """Build the X-error component observed by Z-check measurements."""
    built = circuit(config, p, "x")
    model = built.detector_error_model(decompose_errors=False)
    effective = stim.DetectorErrorModel()
    keys, probabilities = [], []
    for key, probability in effects(model).items():
        detectors, logicals = key
        targets = ([stim.target_relative_detector_id(i) for i in detectors] +
                   [stim.target_logical_observable_id(i) for i in logicals])
        effective.append("error", probability, targets)
        keys.append(key)
        probabilities.append(probability)
    return built, effective, keys, probabilities


def sample_physical(config: dict, p: float, shots: int, seed: int):
    """Vectorized Z-check-sector sampling of the circuit-level Pauli model."""
    a_parts, b_parts, _, lz = code_data(config)
    xchecks = list(range(72))
    left, right, zchecks = list(range(72, 144)), list(range(144, 216)), list(range(216, 288))
    data = left + right
    nx = [a + b for a, b in zip(neighbors(a_parts, 72), neighbors(b_parts, 144))]
    nz = [a + b for a, b in zip(neighbors(b_parts, 72, True), neighbors(a_parts, 144, True))]
    rng = np.random.default_rng(seed)
    x = np.zeros((shots, 288), dtype=np.bool_)
    z = np.zeros_like(x)
    z_check_history = []

    def pair(table, direction, checks, reverse=False):
        flat = [q for i, check in enumerate(checks)
                for q in ((table[i][direction], check) if reverse
                          else (check, table[i][direction]))]
        return flat[::2], flat[1::2]

    def depolarize1(qubits, probability):
        if not probability:
            return
        error = rng.random((shots, len(qubits))) < probability
        pauli = rng.integers(0, 3, error.shape)
        x[:, qubits] ^= error & (pauli != 2)
        z[:, qubits] ^= error & (pauli != 0)

    def cnot(controls, targets, probability):
        x[:, targets] ^= x[:, controls]
        z[:, controls] ^= z[:, targets]
        if not probability:
            return
        error = rng.random((shots, len(controls))) < probability
        pauli = rng.integers(1, 16, error.shape)
        x[:, controls] ^= error & ((pauli & 1) != 0)
        z[:, controls] ^= error & ((pauli & 2) != 0)
        x[:, targets] ^= error & ((pauli & 4) != 0)
        z[:, targets] ^= error & ((pauli & 8) != 0)

    for round_index in range(config["num_cycles"] + 2):
        probability = p if round_index < config["num_cycles"] else 0.0
        x[:, xchecks] = False
        z[:, xchecks] = rng.random((shots, 72)) < probability
        controls, targets = pair(nz, config["sZ"][0], zchecks, True)
        cnot(controls, targets, probability)
        depolarize1(sorted(set(data) - set(controls)), probability)
        for stage in range(1, 6):
            cnot(*pair(nx, config["sX"][stage], xchecks), probability)
            cnot(*pair(nz, config["sZ"][stage], zchecks, True), probability)
        measured = x[:, zchecks].copy()
        if probability:
            measured ^= rng.random(measured.shape) < probability
        z_check_history.append(measured)
        controls, targets = pair(nx, config["sX"][6], xchecks)
        cnot(controls, targets, probability)
        depolarize1(sorted(set(data) - set(targets)), probability)
        depolarize1(data, probability)
        if probability:
            # Preserve the full-circuit RNG schedule; this readout is outside the selected sector.
            _ = rng.random((shots, len(xchecks)))
        x[:, zchecks] = rng.random((shots, 72)) < probability
        z[:, zchecks] = False

    def differences(history):
        values = np.stack(history, axis=1)
        return np.concatenate((values[:, :1], values[:, 1:] ^ values[:, :-1]), axis=1)

    detectors = differences(z_check_history).reshape(shots, -1)
    data_x = x[:, data].astype(np.uint8)
    observables = (data_x @ lz.T) & 1
    return detectors.astype(np.uint8), observables.astype(np.uint8)


def quantize(probabilities):
    if any(not 0 < p < 0.5 for p in probabilities):
        raise ValueError("all DEM probabilities must lie in (0, 0.5)")
    return [min((1 << PRIOR_BITS) - 1,
                math.floor(PRIOR_SCALE * math.log((1 - p) / p) + 0.5))
            for p in probabilities]


def reduce_degree_one(keys, detector_count: int, logical_count: int):
    """Solve singleton parity checks exactly; the CNU datapath starts at degree two."""
    raw_rows = [[] for _ in range(detector_count)]
    raw_logicals = [[] for _ in range(logical_count)]
    for column, (detectors, logicals) in enumerate(keys):
        for detector in detectors:
            raw_rows[detector].append(column)
        for logical in logicals:
            raw_logicals[logical].append(column)
    fixed = {row[0]: check for check, row in enumerate(raw_rows) if len(row) == 1}
    if len(fixed) != sum(len(row) == 1 for row in raw_rows):
        raise ValueError("singleton checks do not fix distinct variables")
    kept_variables = [column for column in range(len(keys)) if column not in fixed]
    remap = {column: i for i, column in enumerate(kept_variables)}
    kept_checks = [check for check, row in enumerate(raw_rows) if len(row) != 1]
    rows = [[remap[column] for column in raw_rows[check] if column not in fixed]
            for check in kept_checks]
    logicals = [[remap[column] for column in row if column not in fixed]
                for row in raw_logicals]
    if any(len(row) < 2 for row in rows):
        raise ValueError("singleton elimination exposed another low-degree check")
    return raw_rows, raw_logicals, fixed, kept_checks, kept_variables, rows, logicals


def reduce_sample(syndrome, observables, raw_rows, raw_logicals, fixed, kept_checks):
    fixed_value = {column: int(syndrome[check]) for column, check in fixed.items()}
    reduced_syndrome = [int(syndrome[check]) ^
                        (sum(fixed_value.get(column, 0) for column in raw_rows[check]) & 1)
                        for check in kept_checks]
    reduced_observables = [int(value) ^
                           (sum(fixed_value.get(column, 0) for column in row) & 1)
                           for value, row in zip(observables, raw_logicals)]
    return reduced_syndrome, reduced_observables


def prepare(output: Path, p_values, shots: int, iterations: int, seed: int) -> None:
    if shots < 1 or iterations < 1 or any(not 0 < p < 0.02 for p in p_values):
        raise ValueError("shots and iterations must be positive; require 0 < p < 0.02")
    config = upstream_config()
    output.mkdir(parents=True, exist_ok=True)
    canonical_keys, priors, dems, samples = None, [], [], []
    for index, p in enumerate(p_values):
        built, dem, keys, probabilities = z_check_model(config, p)
        if canonical_keys is None:
            canonical_keys = keys
            (output / "z_checks.stim").write_text(str(built) + "\n")
        elif keys != canonical_keys:
            raise ValueError("DEM topology changed across the p sweep")
        priors.append(quantize(probabilities))
        dems.append(dem)
        tag = f"p{p:.4f}".replace(".", "_")
        (output / f"{tag}.dem").write_text(str(dem) + "\n")
        samples.append(sample_physical(config, p, shots, seed + index))

    if any(dem.num_detectors != dems[0].num_detectors for dem in dems):
        raise ValueError("DEM detector count changed across the p sweep")
    reduced = reduce_degree_one(canonical_keys, dems[0].num_detectors, LOGICAL_COUNT)
    raw_rows, raw_logicals, fixed, kept_checks, kept_variables, rows, logicals = reduced
    if any(not row for row in rows) or any(not detectors for detectors, _ in canonical_keys):
        raise ValueError("the static decoder requires nonempty detector rows and columns")
    priors = [[prior[column] for column in kept_variables] for prior in priors]
    samples = [[reduce_sample(syndrome, observable, raw_rows, raw_logicals,
                              fixed, kept_checks)
                for syndrome, observable in zip(detectors, observables)]
               for detectors, observables in samples]
    observed = len(rows), len(kept_variables), sum(map(len, rows)), len(logicals)
    if observed != (936, 8784, 30672, LOGICAL_COUNT):
        raise ValueError(f"unexpected Z-check problem dimensions {observed}")

    sweep = {
        "schema": "chipsldpc.bb144.v2",
        "tools": {"stim": stim.__version__},
        "upstream": {"url": UPSTREAM_URL,
                     "commit": config["commit"]},
        "code": {"n": 144, "k": 12, "d": 12, "cycles": config["num_cycles"],
                 "ell": config["ell"], "m": config["m"],
                 "a": [config["a1"], config["a2"], config["a3"]],
                 "b": [config["b1"], config["b2"], config["b3"]]},
        "decoder": {"iterations": iterations, "quantization_bits": PRIOR_BITS,
                    "prior_scale": PRIOR_SCALE},
        "sampling": {"p_values": list(p_values), "shots_per_p": shots, "seed": seed,
                     "model": "Z-check sector of one circuit-level Pauli process"},
        "dem": {"m": len(rows), "n": len(kept_variables), "e": sum(map(len, rows)),
                "row_ones": rows, "logical_ones": logicals, "priors": priors,
                "sector": "Z-check detectors (X-error component)",
                "exact_preprocessing": {
                    "raw_m": dems[0].num_detectors, "raw_n": len(canonical_keys),
                    "fixed_variable_detector": [[column, check]
                                                for column, check in fixed.items()]},
                },
    }
    save(output / "sweep.json", sweep)

    with (output / "benchmark.txt").open("w") as stream:
        stream.write(f"{len(rows)} {len(kept_variables)} {LOGICAL_COUNT} {iterations} 12 "
                     f"{len(p_values)} {PRIOR_BITS} {CONTROL_MAX}\n")
        for row in logicals:
            stream.write(" ".join(map(str, (len(row), *row))) + "\n")
        for p, prior, sample in zip(p_values, priors, samples):
            stream.write(f"{p:.12g} {shots}\n")
            stream.write(" ".join(map(str, prior)) + "\n")
            for syndrome, actual in sample:
                stream.write(" ".join(map(str, syndrome + actual)) + "\n")

    verify = output / "verify"
    for p, prior, sample in zip(p_values, priors, samples):
        tag = f"p{p:.4f}".replace(".", "_")
        syndrome, observables = sample[0]
        save(verify / tag / "problem.json", {
            "schema": 1, "n": len(kept_variables), "row_ones": rows,
            "prior": prior, "syndrome": syndrome, "iterations": iterations,
        })
        save(verify / tag / "actual.json", {"p": p, "observables": observables})
    print(f"m={len(rows)} n={len(kept_variables)} logicals={LOGICAL_COUNT} "
          f"shots={shots * len(p_values)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("prepare")
    build.add_argument("output", type=Path)
    build.add_argument("--p", type=float, nargs="+", default=DEFAULT_P)
    build.add_argument("--shots", type=int, default=1000)
    build.add_argument("--iterations", type=int, default=30)
    build.add_argument("--seed", type=int, default=14412)
    args = parser.parse_args()
    prepare(args.output, args.p, args.shots, args.iterations, args.seed)


if __name__ == "__main__":
    main()
