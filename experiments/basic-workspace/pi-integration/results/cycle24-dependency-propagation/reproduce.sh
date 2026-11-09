#!/bin/sh
set -eu
cd "$(dirname "$0")/../../../../.."
tmpdir=$(mktemp -d /var/tmp/cycle24-preflight.XXXXXX)
trap 'rm -rf "$tmpdir"' EXIT
python3 -m unittest discover -s experiments/basic-workspace/tests -v
python3 experiments/basic-workspace/pi-integration/cycle24_preflight.py --output "$tmpdir/preflight"
python3 experiments/basic-workspace/pi-integration/results/cycle24-dependency-propagation/build_combined_replay.py
