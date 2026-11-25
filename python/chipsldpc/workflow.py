"""One resumable experiment, with immutable inputs and reusable RTL builds."""

from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import resource
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temp.replace(path)


def files_under(directory):
    return {str(p.relative_to(directory)): digest(p) for p in sorted(directory.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".tmp")}


def verify_files(directory, recorded, label):
    for name, expected in recorded.items():
        path = directory / name
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"{label} changed or is missing: {path}; use a new output directory")


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(f"another process is using {path.parent}; retry after it finishes") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def tool_version(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        text = (result.stdout + result.stderr).strip()
        return {"available": result.returncode == 0, "version": text.splitlines()[0] if text else "unknown"}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "version": str(error)}


def versions():
    packages = {}
    for name in ("stim", "numpy", "matplotlib", "bposd", "ldpc", "scipy"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"python": sys.version.split()[0], "platform": platform.platform(),
            "machine": platform.machine(), "packages": packages,
            "java": tool_version(["java", "-version"]),
            "verilator": tool_version(["verilator", "--version"]),
            "c++": tool_version([os.environ.get("CXX", "c++"), "--version"]),
            "make": tool_version(["make", "--version"])}


def preflight(spec, *, hardware=True):
    info = versions()
    required = ["stim", "numpy", "matplotlib"]
    if spec["circuit"].get("name", "").startswith("bb144"):
        required += ["bposd", "ldpc", "scipy"]
    missing = [name for name in required if info["packages"][name] is None]
    if missing:
        raise ValueError(f"missing Python packages: {', '.join(missing)}; run ./chipsldpc setup")
    if hardware and spec["run"]["backend"] == "verilator":
        missing = [name for name in ("java", "verilator", "c++", "make") if not info[name]["available"]]
        if missing:
            raise ValueError(f"missing tools: {', '.join(missing)}; run ./chipsldpc doctor for installation instructions")
        java = re.search(r'version "?(\d+)', info["java"]["version"])
        if java and int(java[1]) < 17:
            raise ValueError("Java 17 or newer is required; run ./chipsldpc doctor")
    return info


def producer_files():
    paths = [ROOT / "build.mill", ROOT / "mill", ROOT / ".mill-jvm-opts"]
    for directory, suffix in [("src/main/scala", ".scala"), ("src/test/scala", ".scala"),
                              ("python/chipsldpc", ".py"), ("benchmarks", ".py")]:
        paths += sorted((ROOT / directory).rglob(f"*{suffix}"))
    paths.append(ROOT / "benchmarks/bb144/sim_main.cpp")
    return {str(path.relative_to(ROOT)): digest(path) for path in paths if path.is_file()}


def scientific_spec(spec):
    result = copy.deepcopy(spec)
    # Concurrency changes scheduling, not the experiment or sample identities.
    result["run"].pop("workers", None)
    result["run"].pop("compile_jobs", None)
    return result


def _compiler_stack():
    # Large generated modules benefit from a larger compiler stack. Some macOS
    # sandboxes report a hard limit that setrlimit cannot actually select.
    try:
        _, hard = resource.getrlimit(resource.RLIMIT_STACK)
        resource.setrlimit(resource.RLIMIT_STACK, (hard, hard))
    except (OSError, ValueError):
        pass


def execute(command, log, *, environment=None, compiler=False):
    log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({"MPLBACKEND": "Agg", "MPLCONFIGDIR": str(ROOT / "build/matplotlib")})
    env.update(environment or {})
    started = time.monotonic()
    with log.open("w") as stream:
        stream.write("COMMAND " + json.dumps([str(v) for v in command]) + "\n")
        stream.flush()
        result = subprocess.run([str(v) for v in command], cwd=ROOT, env=env,
                                stdout=stream, stderr=subprocess.STDOUT,
                                preexec_fn=_compiler_stack if compiler else None)
    if result.returncode:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-18:])
        raise RuntimeError(f"command failed; log: {log}\n{tail}")
    return time.monotonic() - started


def mill(main, args, log):
    return execute([ROOT / "mill", "--no-server", "chipsLDPC.test.runMain", main, *args], log,
                   environment={"MILL_OUTPUT_DIR": str(ROOT / "out")})


def relay_profile(decoder, budget=None):
    t0, tr = decoder["initial_iterations"], decoder["relay_iterations"]
    cap = budget if budget is not None else max(decoder["budgets"])
    return [t0, tr, (cap - t0) // tr, decoder["solutions"], decoder["seed_offset"]]


def corpus_copy(samples, output, spec):
    source = samples.resolve()
    if not (source / "benchmark.txt").is_file() and (source / "source/benchmark.txt").is_file():
        source /= "source"
    if not (source / "sweep.json").is_file() or not (source / "benchmark.txt").is_file():
        raise ValueError("--samples must name a prepared source directory or a run containing one")
    meta = json.loads((source / "sweep.json").read_text())
    requested_p = spec["noise"].get("probabilities", [spec["noise"].get("p", 0.003)])
    if (meta["sampling"]["p_values"] != requested_p or
            meta["sampling"]["shots_per_p"] != spec["sampling"]["shots"] or
            meta["sampling"]["seed"] != spec["sampling"]["seed"]):
        raise ValueError("saved samples have different probabilities, shot count or seed; match the recipe to the corpus")
    circuit_path = spec["circuit"].get("path")
    if circuit_path and meta.get("code", {}).get("input_sha256") != digest(circuit_path):
        raise ValueError("the circuit file/factory changed since these samples were generated; prepare a new corpus")
    receipt = source.parent / "run.json"
    if receipt.is_file():
        old = json.loads(receipt.read_text())
        if old.get("source_files"):
            verify_files(source, old["source_files"], "saved sample corpus")
    recipe = source / "prepare-spec.json"
    if recipe.is_file():
        old = json.loads(recipe.read_text())
        for section in ("circuit", "noise"):
            if old.get(section) != spec[section]:
                raise ValueError(f"saved samples have a different {section} specification; use their original circuit/noise settings")
        if old.get("sampling", {}).get("verification_shots", 8) != spec["sampling"]["verification_shots"]:
            raise ValueError("saved samples use a different verification_shots setting; retain that setting when reusing the corpus")
    if source == output.resolve():
        raise ValueError("--samples must refer to another run")
    shutil.copytree(source, output, dirs_exist_ok=True)
    return source


def prepare_run(spec, output, receipt, samples):
    source = output / "source"
    if receipt.get("source_files"):
        verify_files(source, receipt["source_files"], "prepared input")
        print("[prepare] reuse saved circuit and samples", flush=True)
        return
    print("[prepare] build detector model and sample circuit-level noise", flush=True)
    if samples:
        reused = corpus_copy(samples, source, spec)
        receipt["samples_from"] = str(reused)
    else:
        from .prepare import prepare
        prepare(spec, source)
    # Headers and reference fixtures describe decoder capacity, not sampling.
    cap = (spec["decoder"]["initial_iterations"] if spec["decoder"]["kind"] == "relay"
           else max(spec["decoder"]["budgets"]))
    benchmark = source / "benchmark.txt"
    with benchmark.open() as original, benchmark.with_suffix(".tmp").open("w") as rewritten:
        header = original.readline().split()
        header[3] = str(cap)
        rewritten.write(" ".join(header) + "\n")
        shutil.copyfileobj(original, rewritten)
    benchmark.with_suffix(".tmp").replace(benchmark)
    metadata = json.loads((source / "sweep.json").read_text())
    metadata["sampling"]["benchmark_sha256"] = digest(benchmark)
    metadata["decoder"]["iterations"] = cap
    save(source / "sweep.json", metadata)
    graph = metadata["dem"]
    print(f"Graph: {graph['m']} checks, {graph['n']} fault variables, {graph['e']} edges, "
          f"{len(graph['logical_ones'])} observables", flush=True)
    for path in source.glob("verify/**/problem.json"):
        value = json.loads(path.read_text())
        value["iterations"] = cap
        save(path, value)
    receipt["source_files"] = files_under(source)
    save(output / "run.json", receipt)


def hardware_build(spec, output, receipt, tool_info, *, emit_only=False):
    fixtures = sorted((output / "source/verify").glob("**/problem.json"))
    if not fixtures:
        raise ValueError("preparation produced no reference fixtures")
    problem = json.loads(fixtures[0].read_text())
    relay = spec["decoder"]["kind"] == "relay"
    if relay and problem["n"] > 65535:
        raise ValueError("Relay's coefficient generator supports at most 65,535 fault variables")
    generator_sources = {k: v for k, v in producer_files().items()
                         if k.startswith("src/") or k in {"build.mill", "mill", ".mill-jvm-opts", "benchmarks/bb144/sim_main.cpp"}}
    capacity = dict(spec["decoder"])
    capacity["budgets"] = [max(capacity["budgets"])]
    key = identity({"graph": {"n": problem["n"], "row_ones": problem["row_ones"]},
                    "decoder": capacity, "source": generator_sources,
                    "tools": {k: tool_info[k] for k in ("java", "verilator", "c++", "machine", "platform")}})
    cache = ROOT / "build/chipsldpc-cache" / key
    top = "RelayBpArtifact" if relay else "BpOnlyArtifact"
    emitter = "chipsldpc.RelayBpExperiment" if relay else "chipsldpc.BpOnlyExperiment"
    binary = cache / "obj_dir" / f"V{top}"
    with locked(cache / ".lock"):
        build_receipt = cache / "build.json"
        built = json.loads(build_receipt.read_text()) if build_receipt.is_file() else {}
        if built.get("rtl"):
            verify_files(cache / "artifact", built["rtl"], "cached RTL")
            print("[emit] reuse generated RTL", flush=True)
        else:
            print(f"[emit] generate {top} ({len(problem['row_ones'])} checks, {problem['n']} variables)", flush=True)
            args = [fixtures[0], cache] + (relay_profile(spec["decoder"]) if relay else [])
            built["emit_seconds"] = mill(emitter, args, output / "logs/emit.log")
            built["rtl"] = files_under(cache / "artifact")
            save(build_receipt, built)
        (output / "artifact").mkdir(exist_ok=True)
        shutil.copytree(cache / "artifact", output / "artifact", dirs_exist_ok=True)
        if not emit_only:
            if built.get("binary"):
                verify_files(cache, built["binary"], "cached simulator")
                print("[build] reuse Verilator simulator", flush=True)
            else:
                print("[build] compile Verilator simulator (see logs/build.log)", flush=True)
                args = ["verilator", "--cc", "--exe", "--build", "-j", spec["run"]["compile_jobs"],
                        "-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSEDSIGNAL", "-Wno-PINCONNECTEMPTY",
                        "--top-module", top, "--Mdir", cache / "obj_dir",
                        "-CFLAGS", f"-std=c++17 -D{'RELAY_BP_ARTIFACT' if relay else 'BP_ONLY_ARTIFACT'}",
                        *sorted((cache / "artifact/rtl").glob("*.sv")), ROOT / "benchmarks/bb144/sim_main.cpp"]
                built["build_seconds"] = execute(args, output / "logs/build.log", environment={"MAKEFLAGS": "-s"}, compiler=True)
                built["binary"] = {str(binary.relative_to(cache)): digest(binary)}
                save(build_receipt, built)
            shutil.copy2(binary, output / "artifact/simulator")
        receipt["hardware_key"] = key
        receipt["build"] = built
        receipt["artifact_files"] = files_under(output / "artifact")
        save(output / "run.json", receipt)
    return output / "artifact/simulator"


def verify_hardware(spec, output, receipt, simulator):
    if receipt.get("verified_files"):
        verify_files(output / "verification", receipt["verified_files"], "reference verification")
        print("[verify] reuse passed reference comparisons", flush=True)
        return
    decoder = spec["decoder"]
    relay = decoder["kind"] == "relay"
    fixtures = sorted((output / "source/verify").glob("**/problem.json"))
    print(f"[verify] compare {len(fixtures)} frames at {len(decoder['budgets'])} stopping budgets", flush=True)
    total = 0
    for budget in decoder["budgets"]:
        args = relay_profile(decoder, budget) if relay else []
        goldens = []
        for i, original in enumerate(fixtures):
            directory = output / "verification" / f"b{budget}" / f"frame{i:04d}"
            problem = json.loads(original.read_text())
            problem["iterations"] = decoder["initial_iterations"] if relay else budget
            path, golden = directory / "problem.json", directory / "golden.txt"
            save(path, problem)
            args += [path, golden]
            goldens.append(golden)
        main = "chipsldpc.RelayBpSweepGolden" if relay else "chipsldpc.BpOnlySweepGolden"
        mill(main, args, output / "logs" / f"golden-b{budget}.log")
        for golden in goldens:
            execute([simulator, golden, golden.parent / "result.json"], golden.parent / "verify.log")
            total += 1
    receipt["verification_frames"] = total
    receipt["verified_files"] = files_under(output / "verification")
    save(output / "run.json", receipt)


def simulate(spec, output, receipt, simulator):
    manifest = output / "parallel/jobs.json"
    if receipt.get("manifest_sha256") and (not manifest.is_file() or digest(manifest) != receipt["manifest_sha256"]):
        raise ValueError("the saved simulation manifest changed; use a new output directory")
    if receipt.get("raw_sha256") and (not (output / "raw/shots.csv").is_file() or
                                      digest(output / "raw/shots.csv") != receipt["raw_sha256"]):
        raise ValueError("the completed raw results changed; use a new output directory")
    if not manifest.is_file():
        print("[simulate] prepare independent sample batches", flush=True)
        execute([sys.executable, ROOT / "benchmarks/rtl_shards/adapters/chipsldpc.py",
                 output / "source/benchmark.txt", simulator, output / "parallel",
                 "--shard-size", spec["run"]["shard_size"], "--simulator-config", output / "artifact/config.txt",
                 "--budgets", *spec["decoder"]["budgets"]], output / "logs/plan.log")
    receipt["manifest_sha256"] = digest(manifest)
    save(output / "run.json", receipt)
    print(f"[simulate] run/resume with {spec['run']['workers']} workers (logs/simulate.log)", flush=True)
    report = output / "parallel/run.json"
    # The low-level executor pins worker count in its timing receipt. Keep each
    # scheduling choice's receipt, while reusing the same immutable job outputs.
    if report.exists():
        previous = json.loads(report.read_text())
        if previous["workers"] != spec["run"]["workers"]:
            report.replace(report.with_name(f"run-{time.time_ns()}.json"))
    receipt["simulation_seconds"] = execute(
        [sys.executable, ROOT / "benchmarks/rtl_shards/workflow.py", "run", manifest,
         "-j", spec["run"]["workers"], "--report", report], output / "logs/simulate.log")
    execute([sys.executable, ROOT / "benchmarks/rtl_shards/workflow.py", "merge", manifest,
             output / "raw/shots.csv"], output / "logs/merge.log")
    receipt["raw_sha256"] = digest(output / "raw/shots.csv")
    save(output / "run.json", receipt)


def run(spec, recipe, *, out=None, samples=None, prepare_only=False, emit_only=False):
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "build/matplotlib"))
    info = preflight(spec, hardware=not prepare_only)
    sources = producer_files()
    external = {str(Path(section["path"])): digest(section["path"])
                for section in (spec["circuit"], spec["decoder"]) if "path" in section}
    payload = {"spec": scientific_spec(spec), "source": sources, "external": external,
               "tools": info, "sample_corpus": None}
    if samples:
        source = samples / "source" if (samples / "source").is_dir() else samples
        payload["sample_corpus"] = digest(source / "benchmark.txt")
    run_id = identity(payload)
    output = (out or ROOT / "runs" / f"{Path(recipe).stem}-{run_id[:10]}").resolve()
    with locked(output / ".lock"):
        receipt_path = output / "run.json"
        receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
        if receipt and receipt.get("identity") != run_id:
            raise ValueError(f"{output} contains a different experiment or source revision; choose another --out directory")
        if not receipt and any(p.name != ".lock" for p in output.iterdir()):
            raise ValueError(f"{output} is not empty; choose an empty output directory")
        print(f"Run: {output}", flush=True)
        p = spec["noise"].get("probabilities", [spec["noise"].get("p", 0.003)])
        print(f"{spec['circuit'].get('name', spec['circuit'].get('path'))}; p={p}; "
              f"{spec['sampling']['shots']} shots/p; {spec['decoder']['kind']}; "
              f"budgets={spec['decoder']['budgets']}; backend={spec['run']['backend']}", flush=True)
        if not receipt:
            receipt = {"schema": "chipsldpc.run.v1", "identity": run_id, "status": "started"}
            save(receipt_path, receipt)
            git = subprocess.run(["git", "-c", "core.fsmonitor=false", "rev-parse", "HEAD"],
                                 cwd=ROOT, capture_output=True, text=True)
            status = subprocess.run(["git", "-c", "core.fsmonitor=false", "status", "--porcelain"],
                                    cwd=ROOT, capture_output=True, text=True)
            save(output / "provenance.json", {"git_revision": git.stdout.strip(),
                 "working_tree_status": status.stdout, "tools": info, "source_sha256": sources,
                 "external_sha256": external})
            shutil.copy2(recipe, output / "recipe.toml")
            for name in sources:
                destination = output / "producer" / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, destination)
            for i, path in enumerate(external):
                destination = output / "producer/external" / f"{i}-{Path(path).name}"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        save(output / "resolved.json", spec)
        try:
            prepare_run(spec, output, receipt, samples)
            if prepare_only:
                receipt["status"] = "prepared"
                save(receipt_path, receipt)
                print(f"Prepared circuit, graph and samples: {output / 'source'}")
                return output
            if spec["run"]["backend"] == "python":
                if emit_only:
                    raise ValueError("Python prototype decoders do not emit RTL")
                from .prototype import run_prototype
                raw = output / "raw/shots.csv"
                if receipt.get("raw_sha256"):
                    if not raw.is_file() or digest(raw) != receipt["raw_sha256"]:
                        raise ValueError("saved prototype output changed; use a new output directory")
                    print("[simulate] reuse Python prototype results", flush=True)
                else:
                    print("[simulate] run Python prototype (floating-point, not RTL)", flush=True)
                    run_prototype(spec, output / "source", output)
                    receipt["raw_sha256"] = digest(raw)
            else:
                if receipt.get("artifact_files"):
                    verify_files(output / "artifact", receipt["artifact_files"], "run artifact")
                simulator = hardware_build(spec, output, receipt, info, emit_only=emit_only)
                if emit_only:
                    receipt["status"] = "emitted"
                    save(receipt_path, receipt)
                    print(f"Generated SystemVerilog: {output / 'artifact/rtl'}")
                    return output
                verify_hardware(spec, output, receipt, simulator)
                simulate(spec, output, receipt, simulator)
            print("[report] count logical failures and plot confidence intervals", flush=True)
            from .report import generate_report
            os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "build/matplotlib"))
            with plotting_environment():
                generate_report(output)
            summary = json.loads((output / "results/summary.json").read_text())
            print("p         budget  failures/shots  word failure (95% interval)")
            for row in summary["results"]:
                print(f"{row['p']:<9g} {row['max_bp_iterations']:>6}  "
                      f"{row['failures']}/{row['shots']:<12} "
                      f"{row['word_failure_probability']:.6g} "
                      f"[{row['word_failure_ci95_low']:.6g}, {row['word_failure_ci95_high']:.6g}]")
            receipt["status"] = "complete"
            receipt["result_files"] = files_under(output / "results")
            save(receipt_path, receipt)
            print(f"Results: {output / 'results/summary.csv'}\nPlot: {output / 'results/logical_failure.png'}", flush=True)
            return output
        except BaseException:
            receipt["status"] = "interrupted"
            save(receipt_path, receipt)
            raise


@contextmanager
def plotting_environment():
    # Fontconfig needs a writable cache in restricted environments. Scope this
    # to plotting: Mill also uses XDG_CACHE_HOME for its downloaded launcher.
    previous = os.environ.get("XDG_CACHE_HOME")
    os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "build/cache"))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("XDG_CACHE_HOME", None)
        else:
            os.environ["XDG_CACHE_HOME"] = previous
