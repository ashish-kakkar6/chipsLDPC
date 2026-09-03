#!/usr/bin/env bash
# Execute all reproducible stages; each numbered script also runs independently.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
for stage in 01-prepare 02-emit-rtl 03-build-and-check-rtl 04-simulate-shards 05-analyze; do
  "$here/$stage.sh"
done
