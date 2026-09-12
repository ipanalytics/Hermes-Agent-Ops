#!/usr/bin/env bash
# Install module 15 artifacts into a Hermes home and register the command gate.
#
#   bash install.sh                 # copy hooks into $HERMES_HOME, print the config commands
#   bash install.sh --register      # also register the pre_tool_call hook (hermes config set)
#
# Nothing here touches the Hermes source tree: hooks live in $HERMES_HOME/agent-hooks and
# survive `hermes update`.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PYTHON="${PYTHON:-/usr/bin/python3}"
REGISTER=false
[[ "${1:-}" == "--register" ]] && REGISTER=true

info() { printf '\033[1;34m[guardrails]\033[0m %s\n' "$*"; }

mkdir -p "$HERMES_HOME/agent-hooks" "$HERMES_HOME/logs" "$HERMES_HOME/pylibs"
cp -f "$HERE/hooks/bash_guard.py" "$HERE/hooks/skill_scan.py" "$HERE/hooks/policy.json" \
      "$HERMES_HOME/agent-hooks/"
chmod +x "$HERMES_HOME/agent-hooks/bash_guard.py" "$HERMES_HOME/agent-hooks/skill_scan.py"
info "hooks installed in $HERMES_HOME/agent-hooks"

# bashlex is a pure-python wheel; vendor it instead of touching the agent's virtualenv.
if ! PYTHONPATH="$HERMES_HOME/pylibs" "$PYTHON" -c "import bashlex" 2>/dev/null; then
  info "vendoring bashlex into $HERMES_HOME/pylibs"
  tmp="$(mktemp -d)"
  url="$(curl -s https://pypi.org/pypi/bashlex/json \
        | "$PYTHON" -c 'import sys,json;d=json.load(sys.stdin);print([u["url"] for u in d["urls"] if u["url"].endswith(".whl")][0])')"
  curl -sL "$url" -o "$tmp/bashlex.whl"
  "$PYTHON" -c "import zipfile,sys;zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" \
      "$tmp/bashlex.whl" "$HERMES_HOME/pylibs"
  rm -rf "$tmp"
fi
PYTHONPATH="$HERMES_HOME/pylibs" "$PYTHON" -c "import bashlex; print('bashlex ready')"

HOOK_CMD="$PYTHON $HERMES_HOME/agent-hooks/bash_guard.py"
HOOKS_JSON='{"pre_tool_call":[{"matcher":"terminal","command":"'"$HOOK_CMD"'","timeout":10,"fail_closed":true}]}'

if $REGISTER; then
  hermes config set hooks_auto_accept true
  hermes config set hooks "$HOOKS_JSON"
  info "registered pre_tool_call guard; restart the gateway to bind it in running processes"
else
  info "register the gate with:"
  printf '  hermes config set hooks_auto_accept true\n  hermes config set hooks %s\n' "'$HOOKS_JSON'"
fi

info "self-test:"
"$PYTHON" "$HERE/tests/test_bash_guard.py" | tail -2
"$PYTHON" "$HERE/tests/test_lanes.py" | tail -2
