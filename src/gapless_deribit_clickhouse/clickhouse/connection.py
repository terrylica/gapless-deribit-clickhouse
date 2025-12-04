"""
ClickHouse connection factory for gapless-deribit-clickhouse.

Provides authenticated client for ClickHouse queries.

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gapless_deribit_clickhouse.clickhouse.config import (
    DEFAULT_PORT,
    DEFAULT_SECURE,
    get_credentials,
)
from gapless_deribit_clickhouse.exceptions import ConnectionError

if TYPE_CHECKING:
    import clickhouse_connect


def get_client() -> clickhouse_connect.driver.Client:
    """
    Get authenticated ClickHouse client.

    Returns:
        Configured ClickHouse client

    Raises:
        CredentialError: If credentials cannot be resolved
        ConnectionError: If connection fails
    """
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
            f"Failed to connect to ClickHouse at {host}:{DEFAULT_PORT}. "
            f"Error: {e}"
        ) from e


def test_connection() -> bool:
    """
    Test ClickHouse connection.

    Returns:
        True if connection successful

    Raises:
        CredentialError: If credentials cannot be resolved
        ConnectionError: If connection fails
    """
    client = get_client()
    result = client.query("SELECT 1")
    return result.result_rows[0][0] == 1
