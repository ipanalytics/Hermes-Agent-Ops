#!/usr/bin/env bash
# Minimal GEPA run over the shared shell-safety task set.
#   python3 -m venv --without-pip .venv && curl -sSL https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
#   .venv/bin/pip install -r ../../requirements.txt
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PY:-python3}"
"$PY" ../../tuner.py \
  --prompt-file "$HERE/seed_prompt.txt" \
  --dataset "$HERE/tasks.jsonl" \
  --max-metric-calls "${MAX_CALLS:-60}" \
  --out "$HERE/report.json" "${@:1}"
