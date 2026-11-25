"""Public command line for scientist-facing experiments."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from .config import load_recipe
from .workflow import ROOT, versions


def doctor():
    info = versions()
    print(f"Python {info['python']} ({sys.executable})")
    okay = sys.version_info >= (3, 12)
    for name in ("java", "verilator", "c++", "make"):
        value = info[name]
        print(f"{'OK' if value['available'] else 'MISSING'} {name}: {value['version']}")
        okay &= value["available"]
    java = re.search(r'version "?(\d+)', info["java"]["version"])
    if java and int(java[1]) < 17:
        print("Java 17 or newer is required.")
        okay = False
    for name, version in info["packages"].items():
        print(f"{'OK' if version else 'MISSING'} {name}: {version or 'run ./chipsldpc setup'}")
        okay &= version is not None
    if not okay:
        print("\nInstall Python 3.12+, Java 17+, Verilator, make and a C++ compiler.\n"
              "macOS: xcode-select --install; brew install python@3.12 openjdk@17 verilator\n"
              "Ubuntu 24.04: sudo apt install python3-venv openjdk-17-jdk verilator build-essential\n"
              "Then run ./chipsldpc setup. Mill is included in the repository.\n"
              "See docs/source/getting-started.md for PATH and platform notes.")
    return 0 if okay else 1


def setup():
    if sys.version_info < (3, 12):
        raise ValueError("install Python 3.12 or newer, then run CHIPSLDPC_PYTHON=/path/to/python3.12 ./chipsldpc setup")
    python = ROOT / ".venv/bin/python"
    if not python.is_file():
        subprocess.run([sys.executable, "-m", "venv", ROOT / ".venv"], check=True)
    # A prepared checkout should not need network access just to check setup.
    required = dict(line.split("==", 1) for line in
                    (ROOT / "benchmarks/bb144/requirements.txt").read_text().splitlines()
                    if "==" in line)
    check = subprocess.run([python, "-c", "import importlib.metadata,json; "
                            "print(json.dumps({d.metadata['Name'].lower():d.version "
                            "for d in importlib.metadata.distributions()}))"],
                           capture_output=True, text=True, check=True)
    installed = json.loads(check.stdout)
    if any(installed.get(name.lower()) != version for name, version in required.items()):
        subprocess.run([python, "-m", "pip", "install", "-r", ROOT / "benchmarks/bb144/requirements.txt"], check=True)
    else:
        print("Python environment is ready; pinned packages already installed.")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "python")
    return subprocess.run([python, "-m", "chipsldpc", "doctor"], env=environment).returncode


def archive_results(action, output):
    publisher = ROOT / "docs/figures/publish_bb144.py"
    source = ROOT / "docs/source/_static/bb144-results/legacy-v1"
    if action == "check":
        subprocess.run([sys.executable, publisher, "--check"], check=True)
        return
    output = output.resolve()
    if output == source or source in output.parents:
        raise ValueError("choose an output outside the frozen documentation bundle")
    if output.exists() and any(output.iterdir()):
        raise ValueError("archived-figure output must be empty; choose another --out directory")
    shutil.copytree(source, output, dirs_exist_ok=True)
    environment = os.environ.copy()
    environment.update({"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(ROOT / "build/matplotlib")})
    environment.setdefault("XDG_CACHE_HOME", str(ROOT / "build/cache"))
    subprocess.run([sys.executable, publisher, "--render", "--bundle", output], env=environment, check=True)
    print(f"Redrawn archived figures: {output}")


def parser():
    p = argparse.ArgumentParser(prog="chipsldpc", description="Run circuit-level decoding experiments and generate RTL results.")
    commands = p.add_subparsers(dest="command", required=True, metavar="{setup,doctor,run,plot,results}")
    commands.add_parser("setup", help="prepare the Python environment and check the toolchain")
    commands.add_parser("doctor", help="show installed tools and missing dependencies")
    r = commands.add_parser("run", help="prepare, emit, verify, simulate and plot an experiment")
    r.add_argument("recipe", type=Path, help="TOML experiment recipe")
    r.add_argument("--out", type=Path, help="run directory; matching runs resume automatically")
    r.add_argument("--shots", type=int, help="override shots per physical probability")
    r.add_argument("--workers", type=int, help="simulation worker count")
    r.add_argument("--backend", choices=("verilator", "python"))
    r.add_argument("--samples", type=Path, help="reuse a saved source directory for a paired comparison")
    stages = r.add_mutually_exclusive_group()
    stages.add_argument("--prepare-only", action="store_true", help="save circuits, DEM and samples without building RTL")
    stages.add_argument("--emit-only", action="store_true", help="stop after generating SystemVerilog")
    plot = commands.add_parser("plot", help="regenerate a run's statistics and figures without a simulator")
    plot.add_argument("directory", type=Path)
    results = commands.add_parser("results", help="check or redraw the archived main results")
    results.add_argument("action", choices=("check", "plot"))
    results.add_argument("--out", type=Path, default=Path("runs/archived-figures"))
    legacy = commands.add_parser("legacy", help=argparse.SUPPRESS)
    legacy.add_argument("variant", choices=("vanilla", "relay", "budget"))
    legacy.add_argument("out", type=Path, nargs="?")
    legacy.add_argument("shots", type=int, nargs="?")
    commands._choices_actions = [action for action in commands._choices_actions if action.dest != "legacy"]
    return p


def legacy_run(args):
    """Compatibility for old shell commands; scientific settings stay explicit."""
    from .config import validate
    from .workflow import run
    variant = args.variant
    recipe = ROOT / "experiments" / {"vanilla": "bb144-vanilla.toml", "relay": "bb144-relay.toml",
                                     "budget": "bb144-p003.toml"}[variant]
    spec = load_recipe(recipe, shots=args.shots)
    env = os.environ
    if variant == "budget":
        spec["noise"] = {"p": float(env.get("P_VALUE", "0.003"))}
        name = env.get("DECODER", "relay")
        if name in {"bp", "vanilla"}:
            spec["decoder"] = {"kind": "vanilla", "budgets": [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024]}
        elif name != "relay":
            raise ValueError("DECODER must be vanilla or relay")
        if env.get("MAX_BP_ITERATIONS"):
            spec["decoder"]["budgets"] = list(map(int, env["MAX_BP_ITERATIONS"].split()))
            spec["decoder"].pop("iterations", None)
            spec["decoder"].pop("relay_legs", None)
    elif "P_VALUES" in env:
        spec["noise"] = {"probabilities": list(map(float, env["P_VALUES"].split()))}
    for name, key in [("SIM_WORKERS", "workers"), ("VERILATOR_JOBS", "compile_jobs"), ("SHARD_SIZE", "shard_size")]:
        if name in env:
            spec["run"][key] = int(env[name])
    if "SEED" in env:
        spec["sampling"]["seed"] = int(env["SEED"])
    if spec["decoder"]["kind"] == "relay":
        for name, key in [("RELAY_T0", "initial_iterations"), ("RELAY_TR", "relay_iterations"),
                          ("RELAY_R", "relay_legs"), ("RELAY_S", "solutions"), ("RELAY_SEED_OFFSET", "seed_offset")]:
            if name in env:
                spec["decoder"][key] = int(env[name])
        if variant != "budget":
            spec["decoder"].pop("budgets", None)
    spec = validate(spec)
    print("Using the public experiment runner. Existing matching output resumes; results are never cleared.")
    run(spec, recipe, out=args.out)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "setup":
            return setup()
        if args.command == "doctor":
            return doctor()
        if args.command == "results":
            archive_results(args.action, args.out)
        elif args.command == "plot":
            from .report import generate_report
            from .workflow import plotting_environment
            os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "build/matplotlib"))
            with plotting_environment():
                generate_report(args.directory.resolve())
            print(f"Results: {args.directory.resolve() / 'results'}")
        elif args.command == "legacy":
            legacy_run(args)
        else:
            from .workflow import run
            spec = load_recipe(args.recipe, shots=args.shots, workers=args.workers, backend=args.backend)
            run(spec, args.recipe.resolve(), out=args.out, samples=args.samples,
                prepare_only=args.prepare_only, emit_only=args.emit_only)
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. Repeat the same command to resume completed work.", file=sys.stderr)
        return 130
