#!/usr/bin/env python3
"""Split a chipsLDPC benchmark stream into reusable simulator jobs."""

import argparse
import hashlib
import json
import os
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def line(stream, label):
    value = stream.readline()
    if not value:
        raise ValueError(f"missing {label}")
    return value


def plan(source, simulator, output, shard_size, limit, max_p, clock_cycles,
         simulator_config):
    if shard_size < 1 or (limit is not None and limit < 1):
        raise ValueError("shard size and shot limit must be positive")
    source, simulator, output = source.resolve(), simulator.resolve(), output.resolve()
    simulator_config = simulator_config.resolve() if simulator_config else None
    if not source.is_file() or not simulator.is_file():
        raise ValueError("benchmark source and simulator must be files")
    if simulator_config and not simulator_config.is_file():
        raise ValueError("simulator configuration must be a file")
    inputs = output / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    (output / "raw").mkdir(parents=True, exist_ok=True)
    jobs = []
    with source.open() as stream:
        header = line(stream, "header").split()
        if len(header) != 8:
            raise ValueError("expected the chipsLDPC eight-field benchmark header")
        logical_count, iterations, qec_cycles, point_count = map(
            int, (header[2], header[3], header[4], header[5]))
        logicals = [line(stream, "logical row") for _ in range(logical_count)]
        header[5] = "1"
        prefix = " ".join(header) + "\n" + "".join(logicals)
        for point in range(point_count):
            point_header = line(stream, "probability header").split()
            if len(point_header) != 2:
                raise ValueError("expected probability and shot count")
            probability, available = float(point_header[0]), int(point_header[1])
            p = f"{probability:.12g}"
            prior = line(stream, "prior")
            selected = min(available, limit) if limit is not None else available
            if max_p is not None and probability > max_p:
                selected = 0
            for start in range(0, selected, shard_size):
                count = min(shard_size, selected - start)
                name = f"p{point:03d}-s{start:06d}-n{count:06d}"
                path = inputs / f"{name}.txt"
                temporary = path.with_suffix(".tmp")
                with temporary.open("w") as shard:
                    shard.write(prefix)
                    shard.write(f"{p} {count}\n{prior}")
                    for _ in range(count):
                        shard.write(line(stream, "sample"))
                os.replace(temporary, path)
                jobs.append({"id": name, "input": str(path.relative_to(output)),
                             "input_sha256": digest(path),
                             "output": f"raw/{name}.csv", "start": start,
                             "count": count, "groups": {"p": p}})
            for _ in range(available - selected):
                line(stream, "discarded sample")
        if stream.read().strip():
            raise ValueError("extra data after final benchmark record")
    artifacts = [simulator] + ([simulator_config] if simulator_config else [])
    command = [str(simulator), "--benchmark", "{input}", "{output}"]
    if simulator_config:
        command.append(str(simulator_config))
    manifest = {
        "schema": "rtl-shards.v1",
        "source": {"path": str(source), "sha256": digest(source)},
        "artifacts": [{"path": str(path), "sha256": digest(path)} for path in artifacts],
        "command": command,
        "csv": {"index": "shot", "groups": ["p"]},
        "metrics": {"qec_cycles_per_shot": qec_cycles,
                    "decoder_clock_cycles_per_shot": clock_cycles or 2 + 2 * iterations},
        "jobs": jobs,
    }
    path = output / "jobs.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    os.replace(temporary, path)
    print(f"PASS planned {sum(job['count'] for job in jobs)} shots in {len(jobs)} shards: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("simulator", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--shard-size", type=int, default=500)
    parser.add_argument("--limit-per-point", type=int)
    parser.add_argument("--max-p", type=float)
    parser.add_argument("--clock-cycles-per-shot", type=int)
    parser.add_argument("--simulator-config", type=Path)
    args = parser.parse_args()
    if args.clock_cycles_per_shot is not None and args.clock_cycles_per_shot < 1:
        parser.error("clock cycles per shot must be positive")
    plan(args.source, args.simulator, args.output, args.shard_size,
         args.limit_per_point, args.max_p, args.clock_cycles_per_shot,
         args.simulator_config)


if __name__ == "__main__":
    main()
