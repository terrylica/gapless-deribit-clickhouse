"""
ClickHouse connection factory for gapless-deribit-clickhouse.

Provides authenticated client for ClickHouse queries with dual-mode support:
- "cloud": ClickHouse Cloud (production) - requires credentials from .env
- "local": Local ClickHouse (development/backtesting) - no auth required

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
ADR: 2025-12-08-clickhouse-data-pipeline-architecture (dual-mode)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from gapless_deribit_clickhouse.clickhouse.config import (
    DEFAULT_PORT,
    DEFAULT_SECURE,
    get_credentials,
)
from gapless_deribit_clickhouse.exceptions import ConnectionError

if TYPE_CHECKING:
    import clickhouse_connect

# Environment variable names for local mode
ENV_MODE = "CLICKHOUSE_MODE"
ENV_LOCAL_HOST = "CLICKHOUSE_LOCAL_HOST"
ENV_LOCAL_PORT = "CLICKHOUSE_LOCAL_PORT"

# Local ClickHouse defaults
# Note: clickhouse-connect uses HTTP interface, so port 8123 (not 9000)
LOCAL_DEFAULT_HOST = "localhost"
LOCAL_DEFAULT_PORT = 8123


def get_client(mode: str | None = None) -> clickhouse_connect.driver.Client:
    """
    Get ClickHouse client based on mode (local or cloud).

    Args:
        mode: Connection mode - "local" or "cloud". Defaults to CLICKHOUSE_MODE
              env var, falling back to "cloud".

    Returns:
        Configured ClickHouse client

    Raises:
        CredentialError: If credentials cannot be resolved (cloud mode only)
        ConnectionError: If connection fails
    """
    # Resolve mode from parameter or environment
    resolved_mode = mode or os.environ.get(ENV_MODE, "cloud")

    if resolved_mode == "local":
        return _get_local_client()
    return _get_cloud_client()


def _get_local_client() -> clickhouse_connect.driver.Client:
    """Get client for local ClickHouse (development/backtesting)."""
    import clickhouse_connect

    host = os.environ.get(ENV_LOCAL_HOST, LOCAL_DEFAULT_HOST)
    port = int(os.environ.get(ENV_LOCAL_PORT, LOCAL_DEFAULT_PORT))

    try:
        return clickhouse_connect.get_client(
            host=host,
            port=port,
            username="default",
            password="",
        )
    except Exception as e:
        raise ConnectionError(
            f"Failed to connect to local ClickHouse at {host}:{port}. "
            f"Is ClickHouse running? Start with: clickhouse server"
        ) from e


def _get_cloud_client() -> clickhouse_connect.driver.Client:
    """Get client for ClickHouse Cloud (production)."""
    import clickhouse_connect

    host, user, password = get_credentials()

    try:
        return clickhouse_connect.get_client(
            host=host,
            port=DEFAULT_PORT,
            username=user,
            password=password,
            secure=DEFAULT_SECURE,
        )
    except Exception as e:
        raise ConnectionError(
            f"Failed to connect to ClickHouse Cloud at {host}:{DEFAULT_PORT}. "
            f"Error: {e}"
        ) from e


def test_connection(mode: str | None = None) -> bool:
    """
    Test ClickHouse connection.

    Args:
        mode: Connection mode - "local" or "cloud". Defaults to CLICKHOUSE_MODE
              env var, falling back to "cloud".

    Returns:
        True if connection successful

    Raises:
        CredentialError: If credentials cannot be resolved (cloud mode only)
        ConnectionError: If connection fails
    """
    client = get_client(mode=mode)
    result = client.query("SELECT 1")
    return result.result_rows[0][0] == 1
