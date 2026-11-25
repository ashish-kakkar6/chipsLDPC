"""Read small, explicit experiment recipes; reject misspelled settings."""

from __future__ import annotations

import copy
import math
from pathlib import Path
import tomllib


FIELDS = {
    "circuit": {"kind", "name", "path", "function", "rounds", "distance", "sampler"},
    "noise": {"p", "probabilities"},
    "sampling": {"shots", "seed", "verification_shots"},
    "decoder": {"kind", "iterations", "initial_iterations", "relay_iterations", "relay_legs",
                "solutions", "seed_offset", "budgets", "path", "function", "scale", "arithmetic"},
    "run": {"backend", "workers", "compile_jobs", "shard_size"},
}


def positive(value, label, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def validate(spec):
    spec = copy.deepcopy(spec)
    if set(spec) - FIELDS.keys():
        raise ValueError(f"unknown recipe sections: {', '.join(sorted(set(spec) - FIELDS.keys()))}")
    for section, allowed in FIELDS.items():
        value = spec.setdefault(section, {})
        if not isinstance(value, dict):
            raise ValueError(f"{section} must be a TOML table")
        extra = value.keys() - allowed
        if extra:
            raise ValueError(f"unknown {section} setting: {', '.join(sorted(extra))}")
    circuit, noise, sample, decoder, run = (spec[k] for k in FIELDS)
    kind = circuit.setdefault("kind", "builtin")
    if kind not in {"builtin", "stim", "factory"}:
        raise ValueError("circuit.kind must be builtin, stim, or factory")
    applicable = {
        "builtin": {"kind", "name", "rounds", "distance", "sampler"},
        "stim": {"kind", "path", "rounds"},
        "factory": {"kind", "path", "function", "rounds"},
    }[kind]
    if circuit.keys() - applicable:
        raise ValueError(f"settings not applicable to circuit.kind={kind}: {sorted(circuit.keys() - applicable)}")
    if kind == "builtin":
        if circuit.get("name") not in {"repetition", "surface", "bb144", "bb144-legacy"}:
            raise ValueError("choose circuit.name = repetition, surface, or bb144")
        circuit.setdefault("rounds", 12 if circuit["name"].startswith("bb144") else 3)
        if circuit["name"].startswith("bb144") and circuit["rounds"] != 12:
            raise ValueError("the historical BB144 circuit has 12 noisy rounds; use a factory for another circuit")
        if not circuit["name"].startswith("bb144"):
            positive(circuit.setdefault("distance", 3), "circuit.distance", 3)
    else:
        if not isinstance(circuit.get("path"), str) or not Path(circuit["path"]).is_file():
            raise ValueError("circuit.path must name an existing file")
        if kind == "factory":
            circuit.setdefault("function", "make_circuit")
    if "rounds" in circuit:
        positive(circuit["rounds"], "circuit.rounds")
    if "sampler" in circuit and not (
        kind == "builtin" and circuit.get("name", "").startswith("bb144") and circuit["sampler"] == "legacy"
    ):
        raise ValueError("circuit.sampler is only supported as 'legacy' for BB144; other circuits use Stim")
    if "p" in noise and "probabilities" in noise:
        raise ValueError("use noise.p or noise.probabilities, not both")
    values = noise.get("probabilities", [noise.get("p", 0.003)])
    if not isinstance(values, list) or not values or any(
        isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 < p < 0.5
        for p in values
    ) or len(set(values)) != len(values):
        raise ValueError("noise probabilities must be distinct numbers between 0 and 0.5")
    if kind == "stim" and len(values) != 1:
        raise ValueError("a .stim file already contains its noise; use a circuit factory for a p sweep")
    if not noise:
        noise["p"] = 0.003
    positive(sample.setdefault("shots", 100), "sampling.shots")
    positive(sample.setdefault("seed", 14412), "sampling.seed", 0)
    if sample["seed"] >= 2**64:
        raise ValueError("sampling.seed must fit in 64 bits")
    positive(sample.setdefault("verification_shots", 8), "sampling.verification_shots")
    decoder.setdefault("kind", "vanilla")
    explicit_iterations = decoder.get("iterations")
    explicit_legs = decoder.get("relay_legs")
    if decoder["kind"] not in {"vanilla", "relay", "python", "minsum"}:
        raise ValueError("decoder.kind must be vanilla, relay, or python")
    common = {"kind", "budgets", "arithmetic"}
    applicable = common | {
        "vanilla": {"iterations"},
        "relay": {"initial_iterations", "relay_iterations", "relay_legs", "solutions", "seed_offset"},
        "python": {"iterations", "path", "function", "scale"},
        "minsum": {"iterations", "scale"},
    }[decoder["kind"]]
    if decoder.keys() - applicable:
        raise ValueError(f"settings not applicable to decoder.kind={decoder['kind']}: {sorted(decoder.keys() - applicable)}")
    if "function" in decoder and "path" not in decoder:
        raise ValueError("decoder.function requires decoder.path")
    if "path" in decoder and "scale" in decoder:
        raise ValueError("set a custom decoder's scale in its Python function; decoder.scale configures the built-in prototype")
    default_backend = "python" if decoder["kind"] in {"python", "minsum"} else "verilator"
    run.setdefault("backend", default_backend)
    if run["backend"] not in {"verilator", "python"}:
        raise ValueError("run.backend must be verilator or python")
    if run["backend"] == "verilator" and decoder["kind"] in {"python", "minsum"}:
        raise ValueError("this Python decoder has no RTL implementation; use backend = 'python'")
    if run["backend"] == "python" and decoder["kind"] == "relay":
        raise ValueError("the Python prototype is min-sum; Relay's integer reference is verified with backend = 'verilator'")
    if "path" in decoder and not Path(decoder["path"]).is_file():
        raise ValueError("decoder.path must name an existing Python module")
    if "path" in decoder and decoder["kind"] != "python":
        raise ValueError("a custom decoder.path requires decoder.kind = 'python'")
    if "scale" in decoder:
        if run["backend"] != "python":
            raise ValueError("decoder.scale selects the Python prototype; RTL uses its recorded integer ramp profile")
        if not isinstance(decoder["scale"], (float, int)) or not 0 < decoder["scale"] <= 1:
            raise ValueError("decoder.scale must lie in (0, 1]")
    if decoder["kind"] == "relay":
        for name, default in [("initial_iterations", 60), ("relay_iterations", 60), ("solutions", 5)]:
            positive(decoder.setdefault(name, default), f"decoder.{name}")
        positive(decoder.setdefault("relay_legs", 67), "decoder.relay_legs", 0)
        positive(decoder.setdefault("seed_offset", 0), "decoder.seed_offset", 0)
        if decoder["seed_offset"] >= 65535:
            raise ValueError("decoder.seed_offset must be < 65535")
        default_cap = decoder["initial_iterations"] + decoder["relay_legs"] * decoder["relay_iterations"]
        arithmetic = "relay-int4-5"
    else:
        positive(decoder.setdefault("iterations", 30), "decoder.iterations")
        default_cap = decoder["iterations"]
        arithmetic = "vanilla-int4-7" if run["backend"] == "verilator" else "float-minsum"
    if decoder.setdefault("arithmetic", arithmetic) != arithmetic:
        raise ValueError(f"this decoder/backend uses arithmetic = '{arithmetic}'")
    budgets = decoder.setdefault("budgets", [default_cap])
    if not isinstance(budgets, list) or not budgets or len(set(budgets)) != len(budgets):
        raise ValueError("decoder.budgets must be a nonempty list of distinct iteration caps")
    for budget in budgets:
        positive(budget, "decoder.budgets entry")
        if budget > 1000000000:
            raise ValueError("iteration cap exceeds the supported hardware counter")
        if decoder["kind"] == "relay" and (
            budget < decoder["initial_iterations"] or
            (budget - decoder["initial_iterations"]) % decoder["relay_iterations"]
        ):
            raise ValueError("each Relay budget must equal initial_iterations + R * relay_iterations")
    decoder["budgets"] = sorted(budgets)
    if decoder["kind"] == "relay":
        inferred_legs = (max(budgets) - decoder["initial_iterations"]) // decoder["relay_iterations"]
        if explicit_legs is not None and explicit_legs != inferred_legs:
            raise ValueError("decoder.relay_legs conflicts with decoder.budgets; specify one capacity")
        decoder["relay_legs"] = inferred_legs
    else:
        if explicit_iterations is not None and explicit_iterations != max(budgets):
            raise ValueError("decoder.iterations conflicts with decoder.budgets; specify one capacity")
        decoder["iterations"] = max(budgets)
    for name, default in [("workers", 2), ("compile_jobs", 2), ("shard_size", 100)]:
        positive(run.setdefault(name, default), f"run.{name}")
    return spec


def load_recipe(path, *, shots=None, workers=None, backend=None):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        spec = tomllib.load(stream)
    for section in ("circuit", "decoder"):
        if "path" in spec.get(section, {}):
            spec[section]["path"] = str((path.parent / spec[section]["path"]).resolve())
    if shots is not None:
        spec.setdefault("sampling", {})["shots"] = shots
    if workers is not None:
        spec.setdefault("run", {})["workers"] = workers
    if backend is not None:
        spec.setdefault("run", {})["backend"] = backend
    return validate(spec)
