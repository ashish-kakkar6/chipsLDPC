#!/usr/bin/env python3
"""Run one deterministic fixture through the pinned trmue/relay oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys


EXPECTED_COMMIT = "d185194ba0cb4101ced4340d82b2ee6d42f225f0"
SCHEMA = "trmue-relay-oracle.v1"


class OracleError(RuntimeError):
    """A fixture or reference-environment error safe to show to the caller."""


def _git(ref_dir: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(ref_dir), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise OracleError(f"cannot inspect RELAY_REF_DIR: {detail.strip()}") from exc
    return completed.stdout.strip()


def verify_reference() -> Path:
    value = os.environ.get("RELAY_REF_DIR")
    if not value:
        raise OracleError("RELAY_REF_DIR must name the pinned trmue/relay checkout")
    ref_dir = Path(value).expanduser().resolve()
    if not ref_dir.is_dir():
        raise OracleError(f"RELAY_REF_DIR is not a directory: {ref_dir}")
    top = Path(_git(ref_dir, "rev-parse", "--show-toplevel")).resolve()
    if top != ref_dir:
        raise OracleError(f"RELAY_REF_DIR must be the checkout root ({top})")
    commit = _git(ref_dir, "rev-parse", "HEAD")
    if commit != EXPECTED_COMMIT:
        raise OracleError(
            f"trmue/relay HEAD is {commit}; expected exact commit {EXPECTED_COMMIT}"
        )
    dirty = _git(ref_dir, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise OracleError("trmue/relay has tracked local changes; oracle must be pristine")
    return ref_dir


def import_reference(ref_dir: Path):
    source_dir = ref_dir / "src"
    sys.path.insert(0, str(source_dir))
    try:
        import numpy as np  # pylint: disable=import-outside-toplevel
        import relay_bp  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise OracleError(
            "cannot import the reference package; run this adapter with a Python "
            f"environment where RELAY_REF_DIR is installed editable ({exc})"
        ) from exc

    module_file = Path(relay_bp.__file__).resolve()
    try:
        module_file.relative_to(source_dir.resolve())
    except ValueError as exc:
        raise OracleError(
            f"imported relay_bp from {module_file}, not RELAY_REF_DIR/src"
        ) from exc
    return np, relay_bp, module_file


def _object(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise OracleError(f"{label} must be a JSON object")
    return value


def _reject_unknown(value: dict, allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise OracleError(f"unknown {label} field(s): {', '.join(unknown)}")


def _integer(value, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise OracleError(f"{label} must be an integer >= {minimum}")
    return value


def _finite(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OracleError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise OracleError(f"{label} must be finite")
    return result


def _bits(value, label: str) -> list[int]:
    if not isinstance(value, list):
        raise OracleError(f"{label} must be a JSON array")
    result = []
    for index, bit in enumerate(value):
        if bit not in (0, 1, False, True):
            raise OracleError(f"{label}[{index}] must be 0 or 1")
        result.append(int(bit))
    return result


def _priors(fixture: dict) -> tuple[list[float], list[float], str]:
    values = fixture.get("priors")
    if not isinstance(values, list) or not values:
        raise OracleError("priors must be a non-empty JSON array")
    kind = fixture.get("prior_kind", "error_probability")
    parsed = [_finite(value, f"priors[{i}]") for i, value in enumerate(values)]
    if kind == "error_probability":
        for i, value in enumerate(parsed):
            if not 0.0 < value < 1.0:
                raise OracleError(f"priors[{i}] must be strictly between 0 and 1")
        probabilities = parsed
        llrs = [math.log1p(-value) - math.log(value) for value in parsed]
    elif kind == "llr":
        llrs = parsed
        probabilities = [
            math.exp(-value) / (1.0 + math.exp(-value))
            if value >= 0.0
            else 1.0 / (1.0 + math.exp(value))
            for value in parsed
        ]
        if any(not 0.0 < value < 1.0 for value in probabilities):
            raise OracleError(
                "an llr prior is outside the range representable by the reference "
                "error-probability API"
            )
    else:
        raise OracleError("prior_kind must be 'error_probability' or 'llr'")
    return probabilities, llrs, kind


def _check_matrix(fixture: dict, n: int) -> list[list[int]]:
    dense = fixture.get("check_matrix")
    sparse = fixture.get("check_rows")
    if (dense is None) == (sparse is None):
        raise OracleError("provide exactly one of check_matrix or check_rows")
    declared_n = fixture.get("num_variables", n)
    if _integer(declared_n, "num_variables", 1) != n:
        raise OracleError("num_variables must equal len(priors)")
    if dense is not None:
        if not isinstance(dense, list) or not dense:
            raise OracleError("check_matrix must be a non-empty array of rows")
        rows = [_bits(row, f"check_matrix[{i}]") for i, row in enumerate(dense)]
        if any(len(row) != n for row in rows):
            raise OracleError("every check_matrix row must have len(priors) entries")
        return rows
    if not isinstance(sparse, list) or not sparse:
        raise OracleError("check_rows must be a non-empty array of index arrays")
    rows = []
    for row_index, indices in enumerate(sparse):
        if not isinstance(indices, list):
            raise OracleError(f"check_rows[{row_index}] must be an array")
        row = [0] * n
        seen = set()
        for entry_index, index in enumerate(indices):
            index = _integer(index, f"check_rows[{row_index}][{entry_index}]")
            if index >= n:
                raise OracleError(f"check_rows[{row_index}] index {index} is out of range")
            if index in seen:
                raise OracleError(f"check_rows[{row_index}] contains duplicate index {index}")
            seen.add(index)
            row[index] = 1
        rows.append(row)
    return rows


def _coefficient(value, label: str, n: int) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, list):
        if len(value) != n:
            raise OracleError(f"{label} must contain {n} values")
        return [_finite(item, f"{label}[{i}]") for i, item in enumerate(value)]
    scalar = _finite(value, label)
    return [scalar] * n


def _beta_int(value, label: str, n: int) -> list[float]:
    values = value if isinstance(value, list) else [value] * n
    if len(values) != n:
        raise OracleError(f"{label} must contain {n} values")
    scaled = [_integer(item, f"{label}[{i}]") for i, item in enumerate(values)]
    if any(item > 15 for item in scaled):
        raise OracleError(f"{label} entries must fit the chipsLDPC 4-bit beta field")
    return [1.0 - item / 8.0 for item in scaled]


def _legs(fixture: dict, n: int) -> tuple[list[dict], float | None, list[list[float]]]:
    legs = fixture.get("legs")
    if not isinstance(legs, list) or not legs:
        raise OracleError("legs must be a non-empty array")
    normalized = []
    for index, raw in enumerate(legs):
        leg = _object(raw, f"legs[{index}]")
        _reject_unknown(
            leg, {"gamma", "beta", "beta_int", "max_iterations"}, f"legs[{index}]"
        )
        keys = [key for key in ("gamma", "beta", "beta_int") if key in leg]
        if len(keys) != 1:
            raise OracleError(
                f"legs[{index}] must contain exactly one of gamma, beta, or beta_int"
            )
        key = keys[0]
        if key == "beta_int":
            gamma = _beta_int(leg[key], f"legs[{index}].{key}", n)
        else:
            coefficient = _coefficient(leg[key], f"legs[{index}].{key}", n)
            if coefficient is None:
                if index != 0 or key != "gamma":
                    raise OracleError("only legs[0].gamma may be null (vanilla initial BP)")
                gamma = None
            else:
                gamma = coefficient if key == "gamma" else [1.0 - item for item in coefficient]
        if gamma is None:
            if index != 0:
                raise OracleError("only legs[0].gamma may be null (vanilla initial BP)")
        limit = _integer(leg.get("max_iterations"), f"legs[{index}].max_iterations")
        normalized.append({"gamma": gamma, "max_iterations": limit})

    initial = normalized[0]["gamma"]
    if initial is not None and any(value != initial[0] for value in initial[1:]):
        raise OracleError("trmue/relay supports only a scalar gamma/beta on legs[0]")
    relay_limits = {leg["max_iterations"] for leg in normalized[1:]}
    if len(relay_limits) > 1:
        raise OracleError(
            "trmue/relay exposes one shared set_max_iter; relay-leg limits must match"
        )
    initial_gamma = None if initial is None else initial[0]
    relay_gammas = [leg["gamma"] for leg in normalized[1:]]
    return normalized, initial_gamma, relay_gammas


def normalize_fixture(raw: object) -> dict:
    fixture = _object(raw, "fixture")
    _reject_unknown(
        fixture,
        {
            "schema", "check_matrix", "check_rows", "num_variables", "syndrome",
            "priors", "prior_kind", "legs", "decoder", "stopping", "metadata",
            "expected",
        },
        "fixture",
    )
    if fixture.get("schema", SCHEMA) != SCHEMA:
        raise OracleError(f"schema must be {SCHEMA!r}")
    probabilities, llrs, prior_kind = _priors(fixture)
    matrix = _check_matrix(fixture, len(probabilities))
    syndrome = _bits(fixture.get("syndrome"), "syndrome")
    if len(syndrome) != len(matrix):
        raise OracleError("syndrome length must equal the number of check rows")
    legs, initial_gamma, relay_gammas = _legs(fixture, len(probabilities))

    decoder = _object(fixture.get("decoder", {}), "decoder")
    _reject_unknown(
        decoder,
        {"dtype", "alpha", "alpha_iteration_scaling_factor", "data_scale_value", "max_data_value"},
        "decoder",
    )
    dtype = decoder.get("dtype", "f64")
    if dtype not in ("f32", "f64", "i32", "i64"):
        raise OracleError("decoder.dtype must be f32, f64, i32, or i64")
    alpha = decoder.get("alpha")
    if alpha is not None:
        alpha = _finite(alpha, "decoder.alpha")
    alpha_scale = _finite(
        decoder.get("alpha_iteration_scaling_factor", 1.0),
        "decoder.alpha_iteration_scaling_factor",
    )
    if alpha_scale <= 0.0:
        raise OracleError("decoder.alpha_iteration_scaling_factor must be > 0")
    data_scale = decoder.get("data_scale_value")
    if data_scale is not None:
        data_scale = _finite(data_scale, "decoder.data_scale_value")
        if data_scale <= 0.0:
            raise OracleError("decoder.data_scale_value must be > 0")
    max_data = decoder.get("max_data_value")
    if max_data is not None:
        max_data = _finite(max_data, "decoder.max_data_value")
        if max_data <= 0.0:
            raise OracleError("decoder.max_data_value must be > 0")

    stopping = _object(fixture.get("stopping", {}), "stopping")
    _reject_unknown(stopping, {"criterion", "nconv"}, "stopping")
    criterion = stopping.get("criterion", "all")
    if criterion not in ("all", "nconv", "pre_iter"):
        raise OracleError("stopping.criterion must be all, nconv, or pre_iter")
    nconv = _integer(stopping.get("nconv", 1), "stopping.nconv", 1)

    expected = fixture.get("expected")
    if expected is not None:
        expected = _object(expected, "expected")
        _reject_unknown(expected, {"success", "correction"}, "expected")
        if not isinstance(expected.get("success"), bool):
            raise OracleError("expected.success must be boolean")
        correction = _bits(expected.get("correction"), "expected.correction")
        if len(correction) != len(probabilities):
            raise OracleError("expected.correction must have len(priors) entries")
        expected = {"success": expected["success"], "correction": correction}

    return {
        "matrix": matrix,
        "syndrome": syndrome,
        "probabilities": probabilities,
        "llrs": llrs,
        "prior_kind": prior_kind,
        "legs": legs,
        "initial_gamma": initial_gamma,
        "relay_gammas": relay_gammas,
        "dtype": dtype,
        "alpha": alpha,
        "alpha_scale": alpha_scale,
        "data_scale": data_scale,
        "max_data": max_data,
        "criterion": criterion,
        "nconv": nconv,
        "metadata": fixture.get("metadata"),
        "expected": expected,
    }


def _schedule_digest(fixture: dict) -> str:
    schedule = {
        "legs": fixture["legs"],
        "stopping": {"criterion": fixture["criterion"], "nconv": fixture["nconv"]},
    }
    encoded = json.dumps(schedule, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def run_oracle(fixture: dict, np, relay_bp, ref_dir: Path, module_file: Path) -> dict:
    n = len(fixture["probabilities"])
    relay_gammas = fixture["relay_gammas"]
    # Upstream indexes explicit_gammas with set=1..num_sets.  A never-read
    # dummy row zero prevents the final leg from wrapping around to row zero.
    explicit_gammas = None
    if relay_gammas:
        explicit_gammas = np.asarray([[0.0] * n] + relay_gammas, dtype=np.float64)

    classes = {
        "f32": "RelayDecoderF32",
        "f64": "RelayDecoderF64",
        "i32": "RelayDecoderI32",
        "i64": "RelayDecoderI64",
    }
    decoder_class = getattr(relay_bp, classes[fixture["dtype"]])
    relay_limit = fixture["legs"][1]["max_iterations"] if relay_gammas else 0
    decoder = decoder_class(
        np.asarray(fixture["matrix"], dtype=np.uint8),
        np.asarray(fixture["probabilities"], dtype=np.float64),
        alpha=fixture["alpha"],
        alpha_iteration_scaling_factor=fixture["alpha_scale"],
        gamma0=fixture["initial_gamma"],
        data_scale_value=fixture["data_scale"],
        max_data_value=fixture["max_data"],
        pre_iter=fixture["legs"][0]["max_iterations"],
        num_sets=len(relay_gammas),
        set_max_iter=relay_limit,
        gamma_dist_interval=(0.0, 1.0),
        explicit_gammas=explicit_gammas,
        stop_nconv=fixture["nconv"],
        stopping_criterion=fixture["criterion"],
        logging=False,
        seed=0,
    )
    result = decoder.decode_detailed(np.asarray(fixture["syndrome"], dtype=np.uint8))
    correction = [int(value) for value in result.decoding.tolist()]
    expected = fixture["expected"]
    if expected and (
        bool(result.success) != expected["success"] or
        correction != expected["correction"]
    ):
        raise OracleError("reference result disagrees with fixture.expected")
    decoded = [int(value) for value in result.decoded_detectors.tolist()]
    independently_decoded = [
        sum(bit * correction[column] for column, bit in enumerate(row)) & 1
        for row in fixture["matrix"]
    ]
    if decoded != independently_decoded:
        raise OracleError("reference decoded_detectors disagrees with H * correction mod 2")
    cost = math.fsum(llr for llr, bit in zip(fixture["llrs"], correction) if bit)
    configured_limit = sum(leg["max_iterations"] for leg in fixture["legs"])
    return {
        "schema": SCHEMA,
        "ok": True,
        "oracle": {
            "name": "trmue/relay",
            "commit": EXPECTED_COMMIT,
            "ref_dir": str(ref_dir),
            "python_module": str(module_file),
            "decoder": classes[fixture["dtype"]],
        },
        "configuration": {
            "num_checks": len(fixture["matrix"]),
            "num_variables": n,
            "num_relay_legs": len(relay_gammas),
            "leg_iteration_limits": [leg["max_iterations"] for leg in fixture["legs"]],
            "stopping_criterion": fixture["criterion"],
            "stop_nconv": fixture["nconv"],
            "prior_kind": fixture["prior_kind"],
            "schedule_sha256": _schedule_digest(fixture),
            "explicit_gamma_dummy_row0": bool(relay_gammas),
            "metadata": fixture["metadata"],
            "expected_checked": expected is not None,
        },
        "result": {
            "success": bool(result.success),
            "correction": correction,
            "correction_weight": sum(correction),
            "decoded_syndrome": decoded,
            "syndrome_matches": decoded == fixture["syndrome"],
            "posterior_log_likelihood_ratios": [
                float(value) for value in result.posterior_ratios.tolist()
            ],
            "candidate_weighted_cost": cost,
            "iterations": int(result.iterations),
            "configured_iteration_limit": configured_limit,
            "selected_candidate_iteration_limit": int(result.max_iter),
        },
        "api_limitations": [
            "the Python API does not expose per-leg traces or the selected leg index",
            "all relay legs must share set_max_iter",
            "the initial leg supports only one uniform gamma0",
        ],
    }


def self_test(np, relay_bp, ref_dir: Path, module_file: Path) -> dict:
    raw = {
        "check_rows": [[0, 1], [1, 2]],
        "syndrome": [1, 1],
        "priors": [0.1, 0.1, 0.1],
        "legs": [
            {"gamma": 0.1, "max_iterations": 10},
            {"gamma": [0.2, 0.3, 0.4], "max_iterations": 5},
        ],
    }
    output = run_oracle(normalize_fixture(raw), np, relay_bp, ref_dir, module_file)
    if not output["result"]["success"] or output["result"]["correction"] != [0, 1, 0]:
        raise OracleError("self-test repetition-code decode did not match [0, 1, 0]")
    output["self_test"] = True
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", nargs="?", help="JSON fixture path (default: stdin)")
    parser.add_argument("--pretty", action="store_true", help="indent output JSON")
    parser.add_argument("--self-test", action="store_true", help="run a tiny repetition-code fixture")
    args = parser.parse_args()
    try:
        ref_dir = verify_reference()
        np, relay_bp, module_file = import_reference(ref_dir)
        if args.self_test:
            if args.fixture:
                raise OracleError("do not pass a fixture with --self-test")
            output = self_test(np, relay_bp, ref_dir, module_file)
        else:
            if args.fixture:
                with Path(args.fixture).open(encoding="utf-8") as stream:
                    raw = json.load(stream)
            else:
                raw = json.load(sys.stdin)
            output = run_oracle(
                normalize_fixture(raw), np, relay_bp, ref_dir, module_file
            )
    except (OracleError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": SCHEMA, "ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(output, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
