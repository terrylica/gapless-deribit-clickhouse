# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2.0",
#     "python-dotenv>=1.0",
# ]
# ///
# ADR: 2025-12-09-pydantic-dbeaver-config
"""
Generate DBeaver configuration from Pydantic models.

This script reads connection definitions from the Pydantic SSoT models
and generates:
1. .dbeaver/data-sources.json - DBeaver connection configuration
2. .dbeaver/data-sources.schema.json - JSON Schema for IDE IntelliSense

Usage:
    uv run scripts/generate_dbeaver_config.py
    # or via mise:
    mise run dbeaver-generate
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import TypeAdapter

# Import directly from config module (avoids heavy package deps like pandas)
# We import the module file directly to bypass package __init__.py
import importlib.util

_config_path = Path(__file__).parent.parent / "src/gapless_deribit_clickhouse/config/connections.py"
_spec = importlib.util.spec_from_file_location("connections", _config_path)
_connections = importlib.util.module_from_spec(_spec)
sys.modules["connections"] = _connections
_spec.loader.exec_module(_connections)
ClickHouseConnection = _connections.ClickHouseConnection


def generate_dbeaver_config() -> dict[str, Any]:
    """
    Generate DBeaver data-sources.json content.

    Creates both local and cloud connections.
    Local: No credentials needed (default user, empty password)
    Cloud: Pre-populated from .env (CLICKHOUSE_*_READONLY vars)
    """
    # Load .env for cloud credentials
    load_dotenv()

    # Create connections
    local_conn = ClickHouseConnection.local()
    cloud_conn = ClickHouseConnection.cloud_from_env()

    # Merge connection configs
    connections: dict[str, Any] = {}
    connections.update(local_conn.to_dbeaver_config())
    connections.update(cloud_conn.to_dbeaver_config())

    # DBeaver data-sources.json structure
    return {
        "folders": {},
        "connections": connections,
        "connection-types": {
            "dev": {
                "name": "Development",
                "color": "255,255,255",
                "description": "Development connections",
                "auto-commit": True,
                "confirm-execute": False,
                "confirm-data-change": False,
                "auto-close-transactions": False,
            }
        },
    }


def generate_json_schema() -> dict[str, Any]:
    """
    Generate JSON Schema for ClickHouseConnection.

    This schema provides IDE IntelliSense when editing data-sources.json.
    """
    adapter = TypeAdapter(ClickHouseConnection)
    return adapter.json_schema()


def main() -> None:
    """Generate DBeaver configuration files."""
    # Ensure .dbeaver directory exists
    dbeaver_dir = Path(__file__).parent.parent / ".dbeaver"
    dbeaver_dir.mkdir(exist_ok=True)

    # Generate data-sources.json
    config = generate_dbeaver_config()
    config_path = dbeaver_dir / "data-sources.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Generated: {config_path}")

    # Generate JSON Schema
    schema = generate_json_schema()
    schema_path = dbeaver_dir / "data-sources.schema.json"
    schema_path.write_text(json.dumps(schema, indent=2) + "\n")
    print(f"Generated: {schema_path}")

    # Summary
    print("\nConnections created:")
    for conn_id in config["connections"]:
        conn = config["connections"][conn_id]
        print(f"  - {conn['name']} ({conn_id})")


if __name__ == "__main__":
    main()
