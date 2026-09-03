# Parallel RTL shots

This folder runs independent simulation batches against one immutable RTL
simulator. It is deliberately independent of Chisel, CIRCT, MLIR, and the RTL
generator: an experiment-specific adapter writes inputs plus `jobs.json`; the
standard-library-only workflow executes jobs, validates them, and merges CSV.

The simulator contract is small: each job command receives `{input}` and an
atomic `{output}` path, exits nonzero on failure, and writes one CSV row for
each local shot numbered `0..count-1`. All other columns are owned by the
experiment. A manifest pins every input and simulator artifact by SHA-256.

## chipsLDPC example

After producing the BB144 benchmark and Verilated artifact once, split it into
500-shot jobs:

```sh
python3 benchmarks/rtl_shards/adapters/chipsldpc.py \
  build/generated/bb144-progressive-osd0/source/benchmark.txt \
  build/generated/bb144-progressive-osd0/verification/obj_dir-k64-k128-k256/VBpFilteredOsd0Artifact \
  build/generated/bb144-progressive-osd0/parallel --shard-size 100 \
  --simulator-config build/generated/bb144-progressive-osd0/artifact/config.txt
```

`bb144.py prepare --shots 10000` means 10,000 shots **per** probability point;
use 1,250 for 10,000 total shots over an eight-point sweep.

Run, resume, validate, and merge without rebuilding RTL:

```sh
python3 benchmarks/rtl_shards/workflow.py run \
  build/generated/bb144-progressive-osd0/parallel/jobs.json -j 4
python3 benchmarks/rtl_shards/workflow.py check \
  build/generated/bb144-progressive-osd0/parallel/jobs.json
python3 benchmarks/rtl_shards/workflow.py merge \
  build/generated/bb144-progressive-osd0/parallel/jobs.json \
  build/generated/bb144-progressive-osd0/raw/shots.csv
```

Completed shards are checked and skipped. Failed runs cannot replace valid
CSV because each simulator writes a temporary file that is validated before
an atomic rename. Merge converts each local shot number to its global number,
rejects missing or duplicate samples, and preserves every simulator-defined
result column.

Start at four workers, then measure four, six, and eight on the target machine;
stop increasing concurrency when aggregate shots/s stops improving or the host
swaps. Generate the complete deterministic input set before planning so worker
count and restart order cannot alter the samples.

For another RTL project, emit the same compact `rtl-shards.v1` manifest from a
format-specific adapter. `command` is an argument array, never a shell string,
and may use `{input}`, `{output}`, `{id}`, `{start}`, `{count}`, or a configured
group field. Paths may be relative to `jobs.json`, making the benchmark folder
portable with its simulator artifact.

```json
{
  "schema": "rtl-shards.v1",
  "artifacts": [{"path": "sim", "sha256": "..."}],
  "command": ["./sim", "{input}", "{output}"],
  "csv": {"index": "shot", "groups": ["p"]},
  "jobs": [{
    "id": "p000-s000000", "input": "inputs/000.txt",
    "input_sha256": "...", "output": "raw/000.csv",
    "start": 0, "count": 500, "groups": {"p": "0.001"}
  }]
}
```

Run the dependency-free regression test with:

```sh
python3 -m unittest benchmarks/rtl_shards/test_workflow.py
```
