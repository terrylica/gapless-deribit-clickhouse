# ADR: 2025-12-09-pydantic-dbeaver-config
"""
ClickHouse connection configuration models.

Single Source of Truth (SSoT) for database connections.
Used by generator script to produce DBeaver configuration.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ConnectionMode(str, Enum):
    """Connection mode determines SSL and default credentials."""

    LOCAL = "local"
    CLOUD = "cloud"


class ClickHouseConnection(BaseModel):
    """
    ClickHouse connection configuration.

    This model serves as the Single Source of Truth for connection settings.
    The generator script reads these models and produces DBeaver-compatible JSON.
    """

    mode: ConnectionMode = Field(..., description="Connection mode (local/cloud)")
    name: str = Field(..., description="Display name in DBeaver")
    host: str = Field(..., description="ClickHouse server hostname")
    port: int = Field(..., description="ClickHouse server port")
    database: str = Field(default="deribit", description="Database name")
    user: str = Field(default="default", description="Username")
    password: str = Field(default="", description="Password (empty for local)")
    ssl: bool = Field(default=False, description="Use SSL/TLS connection")

    @model_validator(mode="after")
    def set_defaults_by_mode(self) -> ClickHouseConnection:
        """Set SSL based on connection mode."""
        if self.mode == ConnectionMode.LOCAL:
            # Local: HTTP, no auth required
            object.__setattr__(self, "ssl", False)
        elif self.mode == ConnectionMode.CLOUD:
            # Cloud: HTTPS required
            object.__setattr__(self, "ssl", True)
        return self

    @classmethod
    def local(cls) -> ClickHouseConnection:
        """
        Create local ClickHouse connection.

        Local mode uses HTTP (port 8123) with default user and no password.
        No security concern for local development.
        """
        return cls(
            mode=ConnectionMode.LOCAL,
            name="ClickHouse Local",
            host="localhost",
            port=8123,
            database="deribit",
            user="default",
            password="",
        )

    @classmethod
    def cloud_from_env(cls) -> ClickHouseConnection:
        """
        Create cloud ClickHouse connection from environment variables.

        Reads from:
        - CLICKHOUSE_HOST_READONLY
        - CLICKHOUSE_USER_READONLY
        - CLICKHOUSE_PASSWORD_READONLY

        Cloud mode uses HTTPS (port 443) with credentials from .env.
        """
        return cls(
            mode=ConnectionMode.CLOUD,
            name="ClickHouse Cloud",
            host=os.environ.get("CLICKHOUSE_HOST_READONLY", ""),
            port=443,
            database="deribit",
            user=os.environ.get("CLICKHOUSE_USER_READONLY", "default"),
            password=os.environ.get("CLICKHOUSE_PASSWORD_READONLY", ""),
        )

    def to_dbeaver_config(self) -> dict[str, Any]:
        """
        Convert to DBeaver data-sources.json format.

        Returns a dict matching DBeaver's expected connection structure.
        """
        # DBeaver connection ID format
        conn_id = f"clickhouse-{self.mode.value}-{self.database}"

        return {
            conn_id: {
                "provider": "clickhouse",
                "driver": "clickhouse_com",
                "name": self.name,
                "save-password": True,
                "configuration": {
                    "host": self.host,
                    "port": str(self.port),
                    "database": self.database,
                    "url": self._build_jdbc_url(),
                    "configurationType": "URL",
                    "type": "dev",
                    "auth-model": "native",
                    "user": self.user,
                    "password": self.password,
                },
            }
        }

    def _build_jdbc_url(self) -> str:
        """Build JDBC URL for ClickHouse connection."""
        protocol = "https" if self.ssl else "http"
        return f"jdbc:clickhouse:{protocol}://{self.host}:{self.port}/{self.database}"
