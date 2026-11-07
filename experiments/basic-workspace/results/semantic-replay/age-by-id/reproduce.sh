#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$HERE/../../.." && pwd)
cd "$ROOT"
python3 -m unittest tests.test_semantic_replay_age -v
python3 scripts/age-by-id-campaign.py --deterministic-only --output-dir "$HERE/reproduced-scripted"
printf '\nHTML: %s\n' "$HERE/reproduced-scripted/replay.html"
printf 'ANSI: python3 %s/scripts/kitty-replay.py %s/reproduced-scripted/history.jsonl --step\n' "$ROOT" "$HERE"
