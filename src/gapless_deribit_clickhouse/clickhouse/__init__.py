"""
ClickHouse integration for gapless-deribit-clickhouse.

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
"""

from gapless_deribit_clickhouse.clickhouse.config import get_credentials
from gapless_deribit_clickhouse.clickhouse.connection import get_client, test_connection

__all__ = [
    "get_client",
    "get_credentials",
    "test_connection",
]
