#!/usr/bin/env bash
# Install Mwenza into a DeerFlow checkout: the skill, the constitution middleware and the MCP server entry.
#
#   integrations/deerflow/install.sh /path/to/deer-flow
#
#   MWENZA_AGENT_MODEL=mwenza-glm integrations/deerflow/install.sh /path/to/deer-flow     (pin the agent's model)
#
# Idempotent; run it again after changing the skill, the middleware or mwenza_engine/constitution.py.
# Start the MCP server separately (docker-compose.deerflow.yml). The Gateway reloads extensions_config.json
# and picks up the skill; restart it after changing the middleware.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
deerflow="${1:?usage: install.sh /path/to/deer-flow}"
deerflow="$(cd "$deerflow" && pwd)"
[ -f "$deerflow/backend/packages/harness/deerflow/__init__.py" ] || { echo "not a DeerFlow checkout: $deerflow" >&2; exit 1; }

# Skill: a public skill, like NDIM's, so every user sees it (skills/custom is DeerFlow's legacy location). Never
# copy __pycache__: DeerFlow projects skills into a read-only view and stray bytecode breaks it.
skill="$deerflow/skills/public/mwenza"
rm -rf "$skill"
mkdir -p "$skill"
cp -r "$here/skills/mwenza/." "$skill/"
find "$skill" -name __pycache__ -prune -exec rm -rf {} +
echo "skill       -> $skill"

# Middleware: importable from the Gateway, which runs with PYTHONPATH=. in backend/. constitution.py is vendored
# from the engine so the Gateway needs none of Mwenza's dependencies.
package="$deerflow/backend/mwenza_deerflow"
rm -rf "$package"
mkdir -p "$package"
cp "$here/mwenza_deerflow/__init__.py" "$here/mwenza_deerflow/middleware.py" "$package/"
cp "$repo/backend/src/mwenza_engine/constitution.py" "$package/constitution.py"
echo "middleware  -> $package"

python3 - "$deerflow/extensions_config.json" "$here/agent" "$deerflow/backend/.deer-flow/agents/mwenza" "${MWENZA_AGENT_MODEL:-}" <<'EOF'
import json, shutil, sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

path = Path(sys.argv[1])
config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
servers = config.setdefault("mcpServers", {})
servers["mwenza"] = {
    "enabled": True,
    "type": "http",
    "url": "http://mwenza-mcp:8766/mcp",
    "tool_name_prefix": False,
    "session_init_timeout": 60,
    "description": "Mwenza research tools: open literature discovery, golden-thread and paradigm-method checks, methodology navigator, citation audit. Use with the mwenza skill. Served by the mwenza-mcp container on the DeerFlow network (mwenza/integrations/deerflow/docker-compose.deerflow.yml).",
}
entry = {"class": "mwenza_deerflow.middleware:MwenzaConstitutionMiddleware", "kwargs": {"agents": ["mwenza"]}}
middlewares = [item for item in config.setdefault("middlewares", []) if (item if isinstance(item, str) else item.get("class", "")).split(":")[0] != "mwenza_deerflow.middleware"]
config["middlewares"] = [*middlewares, entry]
# Write in place: Docker bind-mounts this file, and rename() over a mount point fails.
path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"config      -> {path} (mcpServers.mwenza, constitution middleware)")

# The Mwenza lead agent, in DeerFlow's shared agents directory so every user sees it. It gets only the mwenza
# skill and the mwenza MCP server (DeerFlow's installation id for a server is uuid5 of its name), read-only file
# tools (to read the skill and uploads) but no web, write or shell tools, no sub-agents, and no memory until per-student memory exists (phase H2).
source, target = Path(sys.argv[2]), Path(sys.argv[3])
target.mkdir(parents=True, exist_ok=True)
shutil.copy(source / "SOUL.md", target / "SOUL.md")
mcp_id = str(uuid5(NAMESPACE_URL, "deerflow:mcp:mwenza"))
# A model named in DeerFlow's config.yaml; empty uses DeerFlow's default model.
model = f"model: {sys.argv[4]}\n" if sys.argv[4] else ""
(target / "config.yaml").write_text(f"""name: mwenza
display_name: Mwenza
{model}description: Research companion for postgraduate students. Supervises with evidence-first checks and open literature; never ghost-writes.
skills: [mwenza]
tool_groups: [file:read]
mcp_plugins: [{mcp_id}]
allowed_subagents: []
memory_enabled: false
""", encoding="utf-8")
print(f"agent       -> {target}")
EOF
