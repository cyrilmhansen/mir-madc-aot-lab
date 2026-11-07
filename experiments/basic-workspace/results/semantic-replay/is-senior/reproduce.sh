#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../../.."

(cd experiments/basic-workspace && python3 -m unittest discover -s tests -v)
python3 experiments/basic-workspace/scripts/is-senior-campaign.py \
  --no-model \
  --output-dir experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics

if [[ -n "${BASIC_WS_CHAT_COMPLETIONS_URL:-}" && -n "${BASIC_WS_MODEL:-}" ]]; then
  python3 experiments/basic-workspace/scripts/is-senior-campaign.py
else
  echo "Real model trial not run: configure BASIC_WS_CHAT_COMPLETIONS_URL and BASIC_WS_MODEL explicitly."
fi

python3 experiments/basic-workspace/scripts/render-semantic-replay.py \
  --trace experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics/history.jsonl \
  --output-dir experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics
