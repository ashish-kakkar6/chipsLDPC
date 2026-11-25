"""Run floating-point decoder experiments on a saved detector sample corpus."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np


def minsum_decode(row_ones, priors, syndrome, max_iterations, *, scale=0.75):
    """Normalized min-sum with flooding updates and a parity stopping test.

    ``priors`` are log likelihood ratios log((1-p)/p). This prototype uses
    floating-point arithmetic; it is not a bit-exact hardware model.
    """
    if not 0 < scale <= 1 or max_iterations < 1:
        raise ValueError("scale must lie in (0, 1] and max_iterations must be positive")
    priors = np.asarray(priors, dtype=float)
    syndrome = np.asarray(syndrome, dtype=np.uint8)
    if not len(priors) or not np.all(np.isfinite(priors)):
        raise ValueError("priors must be a nonempty finite LLR vector")
    if len(syndrome) != len(row_ones) or np.any(syndrome > 1):
        raise ValueError("syndrome must contain one bit per check")
    if not row_ones or any(len(row) < 2 for row in row_ones):
        raise ValueError("min-sum requires checks of degree at least two")
    if any(len(set(row)) != len(row) or any(v < 0 or v >= len(priors) for v in row)
           for row in row_ones):
        raise ValueError("check rows contain repeated or out-of-range variables")
    variables = np.asarray([v for row in row_ones for v in row], dtype=np.int64)
    checks = np.repeat(np.arange(len(row_ones)), [len(row) for row in row_ones])
    messages = priors[variables].copy()
    correction = np.zeros(len(priors), dtype=np.uint8)
    for iteration in range(1, max_iterations + 1):
        magnitude = np.abs(messages)
        first = np.full(len(row_ones), np.inf)
        np.minimum.at(first, checks, magnitude)
        minimum = magnitude == first[checks]
        ties = np.bincount(checks, weights=minimum, minlength=len(row_ones))
        second = np.full(len(row_ones), np.inf)
        np.minimum.at(second, checks, np.where(minimum, np.inf, magnitude))
        outgoing_magnitude = np.where(minimum & (ties[checks] == 1),
                                      second[checks], first[checks])
        signs = (messages < 0).astype(np.uint8)
        parity = syndrome.copy()
        np.bitwise_xor.at(parity, checks, signs)
        outgoing = scale * outgoing_magnitude * (1 - 2 * (parity[checks] ^ signs).astype(float))
        marginal = priors + np.bincount(variables, weights=outgoing, minlength=len(priors))
        correction = (marginal < 0).astype(np.uint8)
        residual = syndrome.copy()
        np.bitwise_xor.at(residual, checks, correction[variables])
        if not np.any(residual):
            break
        messages = marginal[variables] - outgoing
    return {"correction": correction.tolist(), "iterations": iteration}


def _decoder(spec):
    config = spec.get("decoder", {})
    path = config.get("path")
    if not path:
        scale = float(config.get("scale", 0.75))
        if not math.isfinite(scale) or not 0 < scale <= 1:
            raise ValueError("decoder.scale must lie in (0, 1]")
        return (lambda rows, priors, syndrome, budget:
                minsum_decode(rows, priors, syndrome, budget, scale=scale)), {
                    "name": "normalized min-sum", "scale": scale}
    path = Path(path)
    if not path.is_absolute():
        path = Path(spec.get("_config_dir", ".")) / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"decoder module does not exist: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    module_spec = importlib.util.spec_from_file_location(f"chipsldpc_user_decoder_{digest[:16]}", path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f"cannot load decoder module: {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    function = config.get("function", "decode")
    decode = getattr(module, function, None)
    if not callable(decode):
        raise ValueError(f"{path} does not define callable {function}")
    return decode, {"name": f"{path.name}:{function}", "path": str(path), "sha256": digest}


def _integers(stream, count, label):
    line = stream.readline()
    try:
        values = [int(value) for value in line.split()]
    except ValueError as error:
        raise ValueError(f"invalid {label}") from error
    if len(values) != count:
        raise ValueError(f"{label}: expected {count} integers, found {len(values)}")
    return values


def _result(value, n, budget):
    iterations = None
    if isinstance(value, dict):
        iterations = value.get("iterations")
        if iterations is not None and (isinstance(iterations, bool) or
                not isinstance(iterations, (int, np.integer)) or not 0 <= iterations <= budget):
            raise ValueError("decoder iterations must be an integer between zero and its budget")
        value = value.get("correction")
    if value is None:
        raise ValueError("decoder result must include a correction")
    try:
        correction = list(value)
    except TypeError as error:
        raise ValueError("decoder correction must be a bit vector") from error
    if len(correction) != n or any(bit not in (0, 1) for bit in correction):
        raise ValueError(f"decoder correction must contain exactly {n} binary entries")
    return [int(bit) for bit in correction], iterations


def _pack(bits):
    return hex(sum(int(bit) << index for index, bit in enumerate(bits)))


def run_prototype(spec: dict, source: Path, output: Path) -> Path:
    """Decode a saved corpus; the callable receives no observed logical bits.

    A callable returns a correction vector, or a dict with ``correction`` and
    ``iterations``. Its parity convergence is checked independently. No RTL
    timing or exact agreement with the quantized hardware is implied.
    """
    source, output = Path(source), Path(output)
    metadata = json.loads((source / "sweep.json").read_text())
    rows = metadata["dem"]["row_ones"]
    decode, decoder_metadata = _decoder(spec)
    config, run = spec.get("decoder", {}), spec.get("run", {})
    budgets = config.get("budgets", run.get("budgets", run.get("iteration_budgets")))
    default_iterations = config.get("iterations", config.get("max_iterations"))
    probability_points = metadata["dem"].get("probabilities")
    prior_scale = metadata.get("decoder", {}).get("prior_scale", 2)
    fields = ["p", "shot", "max_bp_iterations", "status", "converged", "iterations",
              "correction_weight", "predicted_observables", "actual_observables", "logical_failure"]
    destination = output / "raw" / "shots.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".csv.tmp")
    unknown_iterations = False
    try:
        with (source / "benchmark.txt").open() as stream, temporary.open("w", newline="") as sink:
            m, n, logical_count, file_iterations, _, points, _, _ = _integers(stream, 8, "benchmark header")
            if m != len(rows) or n < 1 or logical_count < 1 or points < 1:
                raise ValueError("benchmark dimensions do not match a nonempty problem")
            if any(not row or any(v < 0 or v >= n for v in row) for row in rows):
                raise ValueError("problem graph contains empty or invalid rows")
            if probability_points is not None and len(probability_points) != points:
                raise ValueError("DEM probability point count does not match the corpus")
            budgets = budgets or [default_iterations or file_iterations]
            if not isinstance(budgets, (list, tuple)) or not budgets or any(
                    isinstance(budget, bool) or not isinstance(budget, int) or budget < 1 for budget in budgets):
                raise ValueError("decoder budgets must be positive integers")
            if len(set(budgets)) != len(budgets):
                raise ValueError("decoder budgets must be distinct")
            logicals = []
            for _ in range(logical_count):
                values = [int(value) for value in stream.readline().split()]
                if not values or values[0] != len(values) - 1 or any(v < 0 or v >= n for v in values[1:]):
                    raise ValueError("invalid logical observable row")
                logicals.append(values[1:])
            writer = csv.DictWriter(sink, fieldnames=fields)
            writer.writeheader()
            for point in range(points):
                point_header = stream.readline().split()
                if len(point_header) != 2:
                    raise ValueError("expected probability and shot count")
                p, shots = float(point_header[0]), int(point_header[1])
                if not math.isfinite(p) or p < 0 or shots < 1:
                    raise ValueError("invalid probability or shot count")
                quantized = _integers(stream, n, "prior")
                if probability_points is not None:
                    probabilities = probability_points[point]
                    if len(probabilities) != n or any(not 0 < value < 1 for value in probabilities):
                        raise ValueError("DEM probabilities must contain one value in (0, 1) per variable")
                    priors = [math.log1p(-value) - math.log(value) for value in probabilities]
                else:
                    if prior_scale <= 0:
                        raise ValueError("prior_scale must be positive")
                    priors = [value / prior_scale for value in quantized]
                for shot in range(shots):
                    sample = _integers(stream, m + logical_count, "detector sample")
                    if any(bit not in (0, 1) for bit in sample):
                        raise ValueError("detector samples and observables must be binary")
                    syndrome, observed = sample[:m], sample[m:]
                    for budget in budgets:
                        # Separate copies prevent one plugin invocation from changing later shots.
                        result = decode([row.copy() for row in rows], priors.copy(), syndrome.copy(), budget)
                        correction, iterations = _result(result, n, budget)
                        unknown_iterations |= iterations is None
                        converged = all(sum(correction[v] for v in row) % 2 == bit
                                        for row, bit in zip(rows, syndrome))
                        predicted = [sum(correction[v] for v in row) % 2 for row in logicals]
                        writer.writerow({"p": f"{p:.12g}", "shot": shot, "max_bp_iterations": budget,
                                         "status": "bp_converged" if converged else "bp_nonconverged",
                                         "converged": int(converged), "iterations": iterations,
                                         "correction_weight": sum(correction),
                                         "predicted_observables": _pack(predicted),
                                         "actual_observables": _pack(observed),
                                         "logical_failure": int(not converged or predicted != observed)})
            if stream.read().strip():
                raise ValueError("unexpected records after the benchmark corpus")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    artifact = output / "artifact"
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact / "config.json").write_text(json.dumps({
        "schema": "chipsldpc.python-prototype.v1", "backend": "python",
        "arithmetic": "floating-point prototype; not a bit-exact RTL model",
        "prior_source": "DEM log likelihood ratios" if probability_points is not None else
                        "quantized priors divided by prior_scale (approximate LLRs)",
        "decoder": decoder_metadata, "budgets": list(budgets),
        "iterations_complete": not unknown_iterations,
        "observable_count": logical_count,
    }, indent=2) + "\n")
    return destination
