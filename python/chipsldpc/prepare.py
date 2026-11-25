"""Prepare a saved circuit-noise corpus for the fixed-point RTL decoders."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
import platform
import sys

import numpy as np
import stim


ROOT = Path(__file__).resolve().parents[2]
PRIOR_BITS = 4
PRIOR_SCALE = 2
SAMPLE_BLOCK = 256


def _save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_module(path: Path, name: str):
    module_spec = importlib.util.spec_from_file_location(name, path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f"cannot load Python circuit factory: {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    module_spec.loader.exec_module(module)
    return module


def _integer(value, label, minimum=1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _settings(spec):
    noise, sampling, decoder = (spec.get(name, {}) for name in ("noise", "sampling", "decoder"))
    values = noise.get("probabilities", [noise.get("p", 0.003)])
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("noise.probabilities must be a nonempty list")
    probabilities = [float(value) for value in values]
    if any(not math.isfinite(p) or not 0 < p < 0.5 for p in probabilities):
        raise ValueError("noise probabilities must lie in (0, 0.5)")
    if len(set(probabilities)) != len(probabilities):
        raise ValueError("noise.probabilities contains duplicate values")
    if len({format(p, '.12g') for p in probabilities}) != len(probabilities):
        raise ValueError("noise probabilities are too close for the simulator's 12-digit input format")
    shots = _integer(sampling.get("shots", 100), "sampling.shots")
    seed = _integer(sampling.get("seed", 14412), "sampling.seed", 0)
    if decoder.get("kind", "vanilla") == "relay":
        iterations = _integer(decoder.get("initial_iterations", 60), "decoder.initial_iterations")
    else:
        iterations = _integer(decoder.get("iterations", 30), "decoder.iterations")
        if decoder.get("budgets"):
            iterations = max(_integer(value, "decoder.budgets entry") for value in decoder["budgets"])
    return probabilities, shots, seed, iterations


def quantize(probabilities):
    """Positive 4-bit LLR magnitudes, matching the existing RTL prior ABI."""
    if any(not math.isfinite(p) or not 0 < p < 0.5 for p in probabilities):
        raise ValueError("RTL prior probabilities must lie in (0, 0.5); deterministic or >= 0.5 faults are unsupported")
    return [min((1 << PRIOR_BITS) - 1,
                math.floor(PRIOR_SCALE * math.log((1 - p) / p) + 0.5))
            for p in probabilities]


def extract_dem(dem: stim.DetectorErrorModel):
    """Return canonically ordered detector/logical signatures and probabilities.

    Equal signatures combine by odd-parity probability. Hyperedges stay intact;
    splitting them would change the decoder's latent fault variables.
    """
    merged = {}
    for instruction in dem.flattened():
        if instruction.type in {"detector", "logical_observable"}:
            continue
        if instruction.type != "error":
            raise ValueError(f"unsupported DEM instruction: {instruction.type}")
        probability = float(instruction.args_copy()[0])
        if probability == 0:
            continue
        quantize([probability])
        detectors, logicals = set(), set()
        for target in instruction.targets_copy():
            if target.is_relative_detector_id():
                detectors.symmetric_difference_update({target.val})
            elif target.is_logical_observable_id():
                logicals.symmetric_difference_update({target.val})
            elif target.is_separator():
                raise ValueError("decomposed DEM errors are unsupported; use circuit.detector_error_model(decompose_errors=False)")
            else:
                raise ValueError(f"unsupported DEM target: {target}")
        if not detectors:
            if logicals:
                raise ValueError(
                    "the DEM contains a detector-free logical fault; this RTL workflow currently requires "
                    "every fault variable to touch a detector. The fault cannot be silently discarded")
            continue  # No detector or logical action.
        key = tuple(sorted(detectors)), tuple(sorted(logicals))
        previous = merged.get(key, 0.0)
        merged[key] = previous * (1 - probability) + probability * (1 - previous)
    keys = sorted(merged)
    probabilities = [merged[key] for key in keys]
    quantize(probabilities)
    if not keys:
        raise ValueError("the circuit has no detectable faults; add a nonzero circuit-noise model")
    return keys, probabilities


@dataclass
class Reduction:
    rows: list[list[int]]
    logicals: list[list[int]]
    kept_variables: list[int]
    kept_checks: list[int]
    syndrome_expressions: list[list[int]]
    logical_offsets: list[list[int]]
    empty_constraints: list[tuple[int, list[int]]]
    fixed_expressions: dict[int, list[int]]
    raw_checks: int
    raw_variables: int

    def metadata(self):
        return {
            "method": "iterative singleton elimination over GF(2)",
            "raw_m": self.raw_checks,
            "raw_n": self.raw_variables,
            "kept_variables": self.kept_variables,
            "kept_checks": self.kept_checks,
            "fixed_variable_syndrome_xor": [
                [variable, expression] for variable, expression in sorted(self.fixed_expressions.items())
            ],
            "syndrome_xor": self.syndrome_expressions,
            "logical_offset_xor": self.logical_offsets,
            "zero_constraints": [[check, expression] for check, expression in self.empty_constraints],
        }


def preprocess(keys, detector_count: int, logical_count: int) -> Reduction:
    """Eliminate all singleton variables while preserving syndrome and logical action.

    Expressions contain original detector indices. Duplicate singleton checks
    become consistency constraints instead of assigning a variable twice.
    """
    rows = [set() for _ in range(detector_count)]
    logicals = [set() for _ in range(logical_count)]
    variable_checks = [set() for _ in keys]
    for variable, (detectors, observables) in enumerate(keys):
        if not detectors:
            raise ValueError("detector-free fault columns are not supported")
        for check in detectors:
            rows[check].add(variable)
            variable_checks[variable].add(check)
        for observable in observables:
            logicals[observable].add(variable)
    expressions = [{check} for check in range(detector_count)]
    queue = deque(check for check, row in enumerate(rows) if len(row) == 1)
    fixed = {}
    while queue:
        check = queue.popleft()
        if len(rows[check]) != 1:
            continue
        variable = next(iter(rows[check]))
        expression = expressions[check].copy()
        fixed[variable] = expression
        for affected in sorted(variable_checks[variable]):
            rows[affected].remove(variable)
            expressions[affected].symmetric_difference_update(expression)
            if len(rows[affected]) == 1:
                queue.append(affected)
        variable_checks[variable].clear()
    kept_variables = [variable for variable in range(len(keys)) if variable not in fixed]
    remap = {variable: index for index, variable in enumerate(kept_variables)}
    kept_checks = [check for check, row in enumerate(rows) if row]
    offsets = []
    for row in logicals:
        offset = set()
        for variable in row.intersection(fixed):
            offset.symmetric_difference_update(fixed[variable])
        offsets.append(sorted(offset))
    return Reduction(
        rows=[[remap[variable] for variable in sorted(rows[check])] for check in kept_checks],
        logicals=[[remap[variable] for variable in sorted(row) if variable in remap] for row in logicals],
        kept_variables=kept_variables,
        kept_checks=kept_checks,
        syndrome_expressions=[sorted(expressions[check]) for check in kept_checks],
        logical_offsets=offsets,
        empty_constraints=[(check, sorted(expressions[check])) for check, row in enumerate(rows) if not row],
        fixed_expressions={variable: sorted(expression) for variable, expression in fixed.items()},
        raw_checks=detector_count,
        raw_variables=len(keys),
    )


def apply_reduction(reduction: Reduction, detectors, observables):
    detectors = np.asarray(detectors, dtype=np.bool_)
    observables = np.asarray(observables, dtype=np.bool_)
    if detectors.ndim != 2 or detectors.shape[1] != reduction.raw_checks:
        raise ValueError("detector samples do not match the DEM detector count")
    if observables.shape != (len(detectors), len(reduction.logicals)):
        raise ValueError("observable samples do not match the circuit observable count")

    def parity(expression):
        return np.logical_xor.reduce(detectors[:, expression], axis=1)

    for check, expression in reduction.empty_constraints:
        inconsistent = np.flatnonzero(parity(expression))
        if inconsistent.size:
            raise ValueError(f"sample {int(inconsistent[0])}: detector check {check} is inconsistent after singleton elimination")
    syndrome = np.empty((len(detectors), len(reduction.rows)), dtype=np.bool_)
    for index, expression in enumerate(reduction.syndrome_expressions):
        syndrome[:, index] = parity(expression)
    actual = observables.copy()
    for logical, expression in enumerate(reduction.logical_offsets):
        actual[:, logical] ^= parity(expression)
    return syndrome, actual


def _block_seed(seed: int, probability: float, block: int) -> int:
    identity = f"chipsldpc.stim.samples.v1\n{seed}\n{probability.hex()}\n{block}".encode()
    return int.from_bytes(hashlib.sha256(identity).digest()[:8], "little")


def sample_circuit(circuit: stim.Circuit, probability: float, shots: int, seed: int):
    """Stable sample prefixes on the same machine with the same Stim version."""
    detectors, observables = [], []
    for block, start in enumerate(range(0, shots, SAMPLE_BLOCK)):
        sampler = circuit.compile_detector_sampler(seed=_block_seed(seed, probability, block))
        det, obs = sampler.sample(SAMPLE_BLOCK, separate_observables=True)
        count = min(SAMPLE_BLOCK, shots - start)
        detectors.append(det[:count])
        observables.append(obs[:count])
    return np.concatenate(detectors), np.concatenate(observables)


def _circuits(spec, probabilities):
    config = spec.get("circuit", {})
    kind = config.get("kind", "builtin")
    name = config.get("name", "repetition")
    if kind == "builtin":
        if name not in {"repetition", "surface"}:
            raise ValueError(f"unknown builtin circuit {name!r}; choose repetition, surface, or bb144-legacy")
        distance = _integer(config.get("distance", 3), "circuit.distance", 3)
        rounds = _integer(config.get("rounds", 3), "circuit.rounds")
        task = "repetition_code:memory" if name == "repetition" else "surface_code:rotated_memory_z"
        circuits = [stim.Circuit.generated(
            task, distance=distance, rounds=rounds,
            after_clifford_depolarization=p, before_round_data_depolarization=p,
            after_reset_flip_probability=p, before_measure_flip_probability=p,
        ) for p in probabilities]
        metadata = {"name": name, "distance": distance, "cycles": rounds, "cycles_explicit": True,
                    "sector": "Z-memory", "stim_generator": task,
                    "noise_model": "p at Clifford depolarization, round data depolarization, reset flip, and measurement flip"}
    elif kind == "stim":
        if len(probabilities) != 1:
            raise ValueError("a .stim file already contains its noise probabilities; use one p label or a Python factory for a noise sweep")
        path = Path(config["path"])
        circuits = [stim.Circuit.from_file(str(path))]
        metadata = {"name": path.stem, "input_path": str(path), "input_sha256": _digest(path),
                    "noise_model": "noise embedded in the supplied Stim circuit", "probability_role": "label_only"}
    elif kind == "factory":
        path = Path(config["path"])
        module = _load_module(path, "chipsldpc_circuit_factory")
        function_name = config.get("function", "make_circuit")
        factory = getattr(module, function_name, None)
        if not callable(factory):
            raise ValueError(f"{path} must define {function_name}(p) returning stim.Circuit")
        kwargs = ({"rounds": _integer(config["rounds"], "circuit.rounds")}
                  if "rounds" in config else {})
        try:
            inspect.signature(factory).bind(probabilities[0], **kwargs)
        except TypeError as error:
            expected = "(p, rounds=...)" if kwargs else "(p)"
            raise ValueError(f"{function_name} must accept {expected}; circuit.rounds is passed to the factory") from error
        circuits = [factory(p, **kwargs) for p in probabilities]
        if any(not isinstance(circuit, stim.Circuit) for circuit in circuits):
            raise ValueError(f"{function_name}(p) must return stim.Circuit")
        metadata = {"name": path.stem, "input_path": str(path), "input_sha256": _digest(path),
                    "factory_function": function_name, "noise_model": "specified by the circuit factory"}
    else:
        raise ValueError(f"unknown circuit.kind {kind!r}; choose builtin, stim, or factory")
    if kind != "builtin":
        metadata.update({"cycles": _integer(config.get("rounds", 1), "circuit.rounds"),
                         "cycles_explicit": "rounds" in config, "sector": config.get("sector", "supplied circuit observables")})
    return circuits, metadata


def _tag(probability):
    return "p" + format(probability, ".12g").replace(".", "_").replace("-", "m").replace("+", "")


def _fixtures(output, tag, p, prior, rows, logicals, syndrome, actual, iterations, limit):
    # Exercise distinct physical inputs, including a nonzero syndrome when present.
    indices, seen = [], set()
    for shot, (det, obs) in enumerate(zip(syndrome, actual)):
        identity = det.tobytes(), obs.tobytes()
        if identity not in seen:
            indices.append(shot)
            seen.add(identity)
        if len(indices) == limit:
            break
    for position, shot in enumerate(indices):
        folder = output / "verify" / tag
        if position:
            folder /= f"sample{shot:06d}"
        _save(folder / "problem.json", {
            "schema": 1, "n": len(prior), "row_ones": rows, "prior": prior,
            "syndrome": syndrome[shot].astype(int).tolist(), "iterations": iterations,
        })
        _save(folder / "actual.json", {"p": p, "shot": shot, "source": "sampled",
                                      "observables": actual[shot].astype(int).tolist()})
    # Low-p smoke runs can contain only the zero syndrome. Exercise nonzero
    # inputs too, without inserting invented shots into the statistical corpus.
    if len(indices) < limit:
        columns = [[] for _ in prior]
        logical_columns = [[] for _ in prior]
        for check, row in enumerate(rows):
            for variable in row:
                columns[variable].append(check)
        for observable, row in enumerate(logicals):
            for variable in row:
                logical_columns[variable].append(observable)
        count = len(indices)
        for variable, checks in enumerate(columns):
            det, obs = np.zeros(len(rows), dtype=np.bool_), np.zeros(len(logicals), dtype=np.bool_)
            det[checks] = True
            obs[logical_columns[variable]] = True
            identity = det.tobytes(), obs.tobytes()
            if identity in seen:
                continue
            seen.add(identity)
            folder = output / "verify" / tag / f"fault{variable:06d}"
            _save(folder / "problem.json", {
                "schema": 1, "n": len(prior), "row_ones": rows, "prior": prior,
                "syndrome": det.astype(int).tolist(), "iterations": iterations,
            })
            _save(folder / "actual.json", {
                "p": p, "source": "synthetic single DEM fault; verification only",
                "fault_variable": variable, "observables": obs.astype(int).tolist(),
            })
            count += 1
            if count == limit:
                break


def _legacy(spec, output, probabilities, shots, seed, iterations):
    config = spec.get("circuit", {})
    if any(key in config for key in ("distance", "rounds")):
        if config.get("rounds", 12) != 12 or config.get("distance", 12) != 12:
            raise ValueError("bb144-legacy fixes [[144,12,12]], 12 noisy rounds and two noiseless closure rounds")
    if len({_tag(p) for p in probabilities}) != len({f"p{p:.4f}" for p in probabilities}):
        raise ValueError("bb144-legacy probability points must be distinct at four decimal places")
    legacy = _load_module(ROOT / "benchmarks/bb144/bb144.py", "chipsldpc_bb144_legacy")
    legacy.prepare(output, probabilities, shots, iterations, seed)
    sweep = json.loads((output / "sweep.json").read_text())
    sweep["code"].update({"name": "bb144-legacy", "cycles_explicit": True,
                          "sector": "Z-check detectors (X-error component)"})
    sweep["tools"].update({"numpy": np.__version__, "python": platform.python_version(), "machine": platform.machine()})
    sweep["sampling"].update({
        "sampler": "bb144.numpy-pauli.legacy-v1",
        "seed_scheme": "root seed + probability index; samples depend on shot count and probability order",
        "corpus_policy": "preserves the existing BB144 sampler; this is not a replay of an archived corpus",
    })
    sweep["dem"]["probabilities"] = []
    for p in probabilities:
        built, _, keys, values = legacy.z_check_model(legacy.upstream_config(), p)
        fixed = {item[0] for item in sweep["dem"]["exact_preprocessing"]["fixed_variable_detector"]}
        sweep["dem"]["probabilities"].append([value for index, value in enumerate(values) if index not in fixed])
        tag = f"p{p:.4f}".replace(".", "_")
        (output / f"{tag}.stim").write_text(str(built) + "\n")
    # Extend the original first-shot fixture set from the already-saved corpus.
    with (output / "benchmark.txt").open() as stream:
        header = list(map(int, stream.readline().split()))
        m, _, logical_count = header[:3]
        for _ in range(logical_count):
            stream.readline()
        for p in probabilities:
            _, count = stream.readline().split()
            prior = list(map(int, stream.readline().split()))
            data = np.array([list(map(int, stream.readline().split())) for _ in range(int(count))], dtype=np.bool_)
            _fixtures(output, f"p{p:.4f}".replace(".", "_"), p, prior, sweep["dem"]["row_ones"],
                      sweep["dem"]["logical_ones"], data[:, :m], data[:, m:], iterations,
                      _integer(spec.get("sampling", {}).get("verification_shots", 8), "sampling.verification_shots"))
    return sweep


def prepare(spec: dict, output: Path) -> dict:
    """Write a corpus, metadata, and verification fixtures to a source directory."""
    output = Path(output)
    probabilities, shots, seed, iterations = _settings(spec)
    verification_shots = _integer(spec.get("sampling", {}).get("verification_shots", 8), "sampling.verification_shots")
    circuit_config = spec.get("circuit", {})
    legacy = (circuit_config.get("kind", "builtin") == "builtin"
              and circuit_config.get("name") in {"bb144", "bb144-legacy"})
    if legacy:
        output.mkdir(parents=True, exist_ok=True)
        sweep = _legacy(spec, output, probabilities, shots, seed, iterations)
    else:
        circuits, code = _circuits(spec, probabilities)
        keys_by_p, probabilities_by_p, dems = [], [], []
        for circuit in circuits:
            if circuit.num_observables < 1:
                raise ValueError("the circuit must define at least one OBSERVABLE_INCLUDE to measure logical failure")
            try:
                dem = circuit.detector_error_model(decompose_errors=False)
            except ValueError as error:
                raise ValueError("Stim could not derive an undecomposed DEM; check deterministic detectors/observables and supported circuit noise. " + str(error)) from error
            keys, fault_probabilities = extract_dem(dem)
            keys_by_p.append(keys)
            probabilities_by_p.append(fault_probabilities)
            dems.append(dem)
        if any(keys != keys_by_p[0] or circuit.num_detectors != circuits[0].num_detectors
               or circuit.num_observables != circuits[0].num_observables
               for keys, circuit in zip(keys_by_p, circuits)):
            raise ValueError("the detector/fault/logical topology changes across probabilities; run these circuits separately")
        reduction = preprocess(keys_by_p[0], circuits[0].num_detectors, circuits[0].num_observables)
        if not reduction.rows or not reduction.kept_variables:
            raise ValueError("singleton preprocessing solved the entire graph; no BP graph remains for RTL generation")
        float_priors = [[values[index] for index in reduction.kept_variables] for values in probabilities_by_p]
        priors = [quantize(values) for values in float_priors]
        code["observables"] = circuits[0].num_observables
        sweep = {
            "schema": "chipsldpc.circuit.v1",
            "tools": {"stim": stim.__version__, "numpy": np.__version__, "python": platform.python_version(), "machine": platform.machine()},
            "code": code,
            "decoder": {"iterations": iterations, "quantization_bits": PRIOR_BITS, "prior_scale": PRIOR_SCALE},
            "sampling": {"p_values": probabilities, "shots_per_p": shots, "seed": seed,
                         "model": "native Stim circuit detector and observable sampling",
                         "sampler": "stim.detector-sampler.block-v1", "block_size": SAMPLE_BLOCK,
                         "seed_scheme": "SHA256 of root seed, probability float.hex(), and block index; first 8 bytes little-endian",
                         "prefix_stability": "fixed 256-shot blocks; same Stim version and machine/SIMD implementation required"},
            "dem": {"m": len(reduction.rows), "n": len(reduction.kept_variables),
                    "e": sum(map(len, reduction.rows)), "row_ones": reduction.rows,
                    "logical_ones": reduction.logicals, "priors": priors, "probabilities": float_priors,
                    "sector": code["sector"], "exact_preprocessing": reduction.metadata()},
        }
        output.mkdir(parents=True, exist_ok=True)
        with (output / "benchmark.txt").open("w") as stream:
            stream.write(f"{len(reduction.rows)} {len(reduction.kept_variables)} {len(reduction.logicals)} "
                         f"{iterations} {code['cycles']} {len(probabilities)} {PRIOR_BITS} 7\n")
            for row in reduction.logicals:
                stream.write(" ".join(map(str, (len(row), *row))) + "\n")
            sample_files = []
            for p, circuit, dem, prior in zip(probabilities, circuits, dems, priors):
                tag = _tag(p)
                (output / f"{tag}.stim").write_text(str(circuit) + "\n")
                (output / f"{tag}.dem").write_text(str(dem) + "\n")
                detectors, observables = sample_circuit(circuit, p, shots, seed)
                syndrome, actual = apply_reduction(reduction, detectors, observables)
                samples_path = output / f"{tag}.samples.npz"
                np.savez_compressed(samples_path, detectors=detectors, observables=observables,
                                    syndrome=syndrome, actual=actual)
                sample_files.append({"p": p, "path": samples_path.name, "sha256": _digest(samples_path)})
                stream.write(f"{p:.12g} {shots}\n")
                stream.write(" ".join(map(str, prior)) + "\n")
                for det, obs in zip(syndrome, actual):
                    stream.write(" ".join(map(str, np.concatenate((det, obs)).astype(int))) + "\n")
                _fixtures(output, tag, p, prior, reduction.rows, reduction.logicals,
                          syndrome, actual, iterations, verification_shots)
            sweep["sampling"]["sample_files"] = sample_files
    sweep["sampling"]["benchmark_sha256"] = _digest(output / "benchmark.txt")
    # The existing transport header includes a decoder iteration cap. Exclude
    # only that field from the physical-corpus identity, so another decoder can
    # consume the same saved faults without changing its identity.
    benchmark_hash = hashlib.sha256()
    with (output / "benchmark.txt").open("rb") as stream:
        header = stream.readline().split()
        header[3] = b"0"
        benchmark_hash.update(b" ".join(header) + b"\n")
        for block in iter(lambda: stream.read(1 << 20), b""):
            benchmark_hash.update(block)
    graph = json.dumps(sweep["dem"]["row_ones"], separators=(",", ":")).encode()
    benchmark_hash.update(graph)
    sweep["sampling"]["corpus_sha256"] = benchmark_hash.hexdigest()
    _save(output / "sweep.json", sweep)
    _save(output / "prepare-spec.json", {
        "schema": "chipsldpc.prepare-spec.v1",
        **{key: spec.get(key, {}) for key in ("circuit", "noise", "sampling")},
    })
    return sweep
