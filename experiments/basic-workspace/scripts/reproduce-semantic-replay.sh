#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"
./scripts/build-mir-worker.sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/semantic_replay_campaign.py
python3 scripts/render-semantic-replay.py
echo "Open: $HERE/results/semantic-replay/replay.html"
echo "Static overview: $HERE/results/semantic-replay/overview.svg"
