"""Generate the `--mcp-config` JSON that points `claude -p` at the naaf MCP
server, scoped to one owner. The server reads naaf_db_url + naaf_mcp_owner_id
from its env (project/work-item ids are tool arguments)."""

import json
import os
import sys
import tempfile


def write_mcp_config(*, owner_id: str, db_url: str, out_dir: str | None = None) -> str:
    config = {
        "mcpServers": {
            "naaf": {
                "command": sys.executable,
                "args": ["-m", "interactors.mcp.server"],
                "env": {"naaf_db_url": db_url, "naaf_mcp_owner_id": owner_id},
            }
        }
    }
    fd, path = tempfile.mkstemp(suffix=".json", prefix="naaf-mcp-", dir=out_dir)
    with os.fdopen(fd, "w") as f:
        json.dump(config, f)
    return path
