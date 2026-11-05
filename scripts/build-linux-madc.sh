#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT/madc"
# Ubuntu's develop build does not discover optional PCRE2 through pkg-config
# in this checkout. Pass the installed library explicitly; do not patch MADC.
make -C src OPTIONAL_LIBS=-lpcre2-8
