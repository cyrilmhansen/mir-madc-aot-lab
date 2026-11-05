#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT/madc"
JOBS=${JOBS:-4}
make -j"$JOBS" -C src cross-aarch64-linux OPTIONAL_LIBS=-lpcre2-8
