#!/usr/bin/env python3
"""Run independent RTL simulation shards and merge their CSV records."""

import argparse
import csv
import hashlib
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCHEMA = "rtl-shards.v1"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def load(path):
    data = json.loads(path.read_text())
    if data.get("schema") != SCHEMA or not data.get("jobs"):
        raise ValueError(f"expected a nonempty {SCHEMA} manifest")
    jobs, groups = data["jobs"], set(data.get("csv", {}).get("groups", []))
    if not isinstance(data.get("command"), list) or not any(
            "{output}" in token for token in data["command"]):
        raise ValueError("command must be an argument array containing {output}")
    if len({job["id"] for job in jobs}) != len(jobs) or len(
            {job["output"] for job in jobs}) != len(jobs):
        raise ValueError("job identifiers and outputs must be unique")
    if any(job["start"] < 0 or job["count"] < 1
           or set(job.get("groups", {})) != groups for job in jobs):
        raise ValueError("invalid job range or group fields")
    return data


def resolved(base, path):
    path = Path(path)
    return path if path.is_absolute() else base / path


def verify_file(base, record, label):
    path = resolved(base, record["path"])
    if not path.is_file() or digest(path) != record["sha256"]:
        raise ValueError(f"{label} changed or is missing: {path}")


def read_rows(path, job, csv_config):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        index = csv_config["index"]
        required = [index, *csv_config.get("groups", [])]
        if not reader.fieldnames or any(name not in reader.fieldnames for name in required):
            raise ValueError(f"{path}: missing CSV columns {required}")
        rows = list(reader)
    expected = set(range(job["count"]))
    try:
        actual = {int(row[index]) for row in rows}
    except ValueError as error:
        raise ValueError(f"{path}: non-integer {index}") from error
    if len(rows) != job["count"] or actual != expected:
        raise ValueError(f"{path}: expected local {index} values 0..{job['count'] - 1}")
    for name, value in job.get("groups", {}).items():
        if any(row.get(name) != value for row in rows):
            raise ValueError(f"{path}: unexpected {name}")
    return reader.fieldnames, rows


def verify_job(base, job, csv_config):
    verify_file(base, {"path": job["input"], "sha256": job["input_sha256"]}, "input")
    return read_rows(resolved(base, job["output"]), job, csv_config)


def run_one(base, manifest, job):
    output = resolved(base, job["output"])
    try:
        verify_job(base, job, manifest["csv"])
        return f"SKIP {job['id']}", False
    except (FileNotFoundError, ValueError):
        pass
    verify_file(base, {"path": job["input"], "sha256": job["input_sha256"]}, "input")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    log = output.with_suffix(output.suffix + ".log")
    values = {"id": job["id"], "input": str(resolved(base, job["input"])),
              "output": str(temporary), "start": job["start"], "count": job["count"],
              **job.get("groups", {})}
    command = [token.format_map(values) for token in manifest["command"]]
    with log.open("w") as stream:
        result = subprocess.run(command, cwd=base, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"{job['id']} failed ({result.returncode}); see {log}")
    read_rows(temporary, job, manifest["csv"])
    os.replace(temporary, output)
    return f"DONE {job['id']}", True


def verify_artifacts(base, manifest):
    for artifact in manifest.get("artifacts", []):
        verify_file(base, artifact, "artifact")


def run(manifest_path, workers, report):
    manifest = load(manifest_path)
    base = manifest_path.parent
    verify_artifacts(base, manifest)
    manifest_hash, previous = digest(manifest_path), {}
    if report and report.exists():
        previous = json.loads(report.read_text())
        if (previous.get("manifest_sha256") != manifest_hash
                or previous.get("workers") != workers):
            raise ValueError("existing run report belongs to another manifest or worker count")
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda job: run_one(base, manifest, job), manifest["jobs"]))
        for status, _ in results:
            print(status)
    elapsed = time.monotonic() - started
    executed = [job for job, result in zip(manifest["jobs"], results) if result[1]]
    shots = sum(job["count"] for job in executed)
    if report:
        shots += previous.get("executed_shots", 0)
        elapsed += previous.get("wall_seconds", 0.0)
        value = {"schema": "rtl-shards.run.v1", "manifest_sha256": manifest_hash,
                 "workers": workers, "total_shards": len(manifest["jobs"]),
                 "executed_shards": previous.get("executed_shards", 0) + len(executed),
                 "executed_shots": shots,
                 "wall_seconds": elapsed,
                 "shots_per_second": shots / elapsed if shots else 0.0}
        report.parent.mkdir(parents=True, exist_ok=True)
        temporary = report.with_suffix(report.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n")
        os.replace(temporary, report)
    print(f"PASS {len(manifest['jobs'])} shards in {elapsed:.1f}s")


def check(manifest_path):
    manifest = load(manifest_path)
    base = manifest_path.parent
    verify_artifacts(base, manifest)
    for job in manifest["jobs"]:
        verify_job(base, job, manifest["csv"])
    print(f"PASS {len(manifest['jobs'])} complete, immutable shards")


def merge(manifest_path, output):
    manifest = load(manifest_path)
    base, config = manifest_path.parent, manifest["csv"]
    verify_artifacts(base, manifest)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = None
    seen = set()
    with temporary.open("w", newline="") as stream:
        writer = None
        for job in manifest["jobs"]:
            job_fields, rows = verify_job(base, job, config)
            if fields is None:
                fields, writer = job_fields, csv.DictWriter(stream, fieldnames=job_fields)
                writer.writeheader()
            elif job_fields != fields:
                raise ValueError("shard CSV headers differ")
            for row in rows:
                row[config["index"]] = str(job["start"] + int(row[config["index"]]))
                key = tuple(row[name] for name in config.get("groups", [])) + (
                    row[config["index"]],)
                if key in seen:
                    raise ValueError(f"duplicate merged sample {key}")
                seen.add(key)
                writer.writerow(row)
    os.replace(temporary, output)
    print(f"PASS merged {len(seen)} unique records into {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    execute = commands.add_parser("run")
    execute.add_argument("manifest", type=Path)
    execute.add_argument("--workers", "-j", type=int, default=1)
    execute.add_argument("--report", type=Path)
    inspect = commands.add_parser("check")
    inspect.add_argument("manifest", type=Path)
    combine = commands.add_parser("merge")
    combine.add_argument("manifest", type=Path)
    combine.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.action == "run":
        if args.workers < 1:
            parser.error("workers must be positive")
        run(args.manifest.resolve(), args.workers,
            args.report.resolve() if args.report else None)
    elif args.action == "check":
        check(args.manifest.resolve())
    else:
        merge(args.manifest.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
