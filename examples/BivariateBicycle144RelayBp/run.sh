#!/usr/bin/env bash
# Compatibility entry point; the public runner preserves and resumes results.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$root"
exec ./chipsldpc legacy relay "$@"
