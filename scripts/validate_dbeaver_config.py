# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2.0",
# ]
# ///
"""Validate DBeaver data-sources.json against Pydantic schema.

ADR: 2025-12-09-pydantic-dbeaver-config
Skill: clickhouse-pydantic-config (cc-skills)

This script validates generated DBeaver configurations to ensure they
conform to the expected structure. It provides:

1. JSON syntax validation
2. Pydantic schema validation
3. JDBC URL consistency checks
4. Port/protocol alignment validation

Usage:
    uv run scripts/validate_dbeaver_config.py
    uv run scripts/validate_dbeaver_config.py --config .dbeaver/data-sources.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator


class DBeaverConnectionConfig(BaseModel):
    """DBeaver connection configuration block.

    Validates the 'configuration' section of each connection entry.
    """

    host: str
    port: str  # DBeaver stores as string
    database: str
    url: str
    type: Literal["dev", "test", "prod"] = "dev"
    user: str = "default"
    password: str = ""

    @model_validator(mode="after")
    def validate_url_protocol_consistency(self) -> DBeaverConnectionConfig:
        """Ensure JDBC URL protocol matches port expectations."""
        # TODO: Implement validation logic
        # Consider: port 443/8443 should use https, port 8123/9000 should use http
        # This is where YOUR implementation goes
        return self


class DBeaverConnection(BaseModel):
    """Single DBeaver connection entry."""

    provider: str = Field(pattern=r"^clickhouse$")
    driver: str  # Allow both "com_clickhouse" and "clickhouse_com"
    name: str
    configuration: DBeaverConnectionConfig
    save_password: bool = Field(default=True, alias="save-password")


class DBeaverDataSources(BaseModel):
    """Complete DBeaver data-sources.json structure."""

    folders: dict[str, Any] = Field(default_factory=dict)
    connections: dict[str, DBeaverConnection]
    connection_types: dict[str, Any] = Field(
        default_factory=dict, alias="connection-types"
    )


def validate_config(config_path: Path) -> tuple[bool, list[str]]:
    """Validate DBeaver config file.

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors: list[str] = []

    # Check file exists
    if not config_path.exists():
        return False, [f"Config file not found: {config_path}"]

    # Parse JSON
    try:
        config_data = json.loads(config_path.read_text())
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]

    # Validate with Pydantic
    try:
        datasources = DBeaverDataSources.model_validate(config_data)
    except ValidationError as e:
        for error in e.errors():
            loc = ".".join(str(x) for x in error["loc"])
            errors.append(f"{loc}: {error['msg']}")
        return False, errors

    # Additional validations
    if not datasources.connections:
        errors.append("No connections defined")
        return False, errors

    for conn_id, conn in datasources.connections.items():
        # Validate JDBC URL consistency
        url = conn.configuration.url
        port = conn.configuration.port

        is_https = "https" in url
        is_secure_port = port in ("443", "8443")

        if is_https and not is_secure_port:
            errors.append(
                f"{conn_id}: HTTPS URL but non-secure port {port} (expected 443 or 8443)"
            )
        if is_secure_port and not is_https:
            errors.append(
                f"{conn_id}: Secure port {port} but HTTP URL (expected HTTPS)"
            )

    return len(errors) == 0, errors


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate DBeaver config against Pydantic schema"
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path(".dbeaver/data-sources.json"),
        help="Path to data-sources.json",
    )

    args = parser.parse_args()

    is_valid, errors = validate_config(args.config)

    if is_valid:
        print(f"✓ Valid: {args.config}")
        return 0

    print(f"✗ Invalid: {args.config}")
    for error in errors:
        print(f"  - {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
