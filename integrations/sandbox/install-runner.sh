#!/usr/bin/env bash
# Install the research sandbox runner as a systemd user service.
#
#   integrations/sandbox/install-runner.sh /path/to/deer-flow
#
# Builds the research image if it is missing, then writes ~/.config/systemd/user/mwenza-runner.service with this
# checkout's runner.py and the DeerFlow data folder the runner reads uploads from and writes outputs to.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
deerflow="$(cd "${1:?usage: install-runner.sh /path/to/deer-flow}" && pwd)"
home_dir="$deerflow/backend/.deer-flow"
[ -d "$home_dir/users" ] || { echo "no DeerFlow data folder at $home_dir" >&2; exit 1; }
docker image inspect mwenza-research:1 >/dev/null 2>&1 || docker build -f "$here/Dockerfile.research" -t mwenza-research:1 "$here"
unit="$HOME/.config/systemd/user/mwenza-runner.service"
mkdir -p "$(dirname "$unit")"
cat > "$unit" <<UNIT
# Written by mwenza/integrations/sandbox/install-runner.sh. Runs student analyses in locked-down containers; listens on
# ~/.local/share/mwenza-runner/socket/runner.sock, which only the mwenza-mcp container mounts.
[Unit]
Description=Mwenza research sandbox runner
After=docker.service

[Service]
Environment=DEERFLOW_HOME=$home_dir
Environment=RUNNER_IMAGE=mwenza-research:1
ExecStart=/usr/bin/python3 -I $here/runner.py
Restart=on-failure

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now mwenza-runner
systemctl --user restart mwenza-runner
echo "runner -> $unit (DEERFLOW_HOME=$home_dir)"
