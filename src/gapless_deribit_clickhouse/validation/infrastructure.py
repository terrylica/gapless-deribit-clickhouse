# ADR: 2025-12-11-e2e-validation-pipeline
"""
Infrastructure validation with auto-creation for ClickHouse data pipeline.

Provides:
- Dictionary existence check and auto-creation
- Schema version validation (v3.0.0 optimizations)
- Mode indicator for CLI output (local/cloud)
- Connection info for current mode

Usage:
    from gapless_deribit_clickhouse.validation.infrastructure import (
        ensure_spot_dictionary,
        get_mode_indicator,
    )

    client = get_client(...)
    ensure_spot_dictionary(client)  # Creates if missing
    print(get_mode_indicator())  # "[LOCAL] localhost"
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clickhouse_connect.driver import Client

logger = logging.getLogger(__name__)

# ADR: 2025-12-11-e2e-validation-pipeline - Schema version constant
EXPECTED_SCHEMA_VERSION = "3.0.0"

# ADR: 2025-12-10-schema-optimization - Dictionary DDL
# Reused from spot_provider.py concept, but defined here for auto-creation
SPOT_DICT_DDL = """
CREATE DICTIONARY IF NOT EXISTS spot_prices_dict (
    symbol LowCardinality(String),
    ts DateTime,
    close Float64
)
PRIMARY KEY symbol, ts
SOURCE(CLICKHOUSE(
    TABLE 'ohlcv'
    QUERY "SELECT symbol, toStartOfFifteenMinutes(timestamp) AS ts, close
           FROM ohlcv WHERE timeframe = '15m' AND instrument_type = 'spot'"
))
LAYOUT(COMPLEX_KEY_HASHED())
LIFETIME(MIN 3600 MAX 7200)
"""


def check_spot_dictionary_exists(client: Client) -> bool:
    """Check if the spot_prices_dict dictionary exists in ClickHouse.

    Args:
        client: ClickHouse client instance

    Returns:
        True if dictionary exists, False otherwise
    """
    query = """
    SELECT count() > 0
    FROM system.dictionaries
    WHERE name = 'spot_prices_dict'
    """
    result = client.query(query)
    return bool(result.result_rows[0][0])


def ensure_spot_dictionary(client: Client, auto_create: bool = True) -> bool:
    """Check and optionally create spot_prices_dict.

    ADR: 2025-12-11-e2e-validation-pipeline - Auto-creation reduces friction

    Args:
        client: ClickHouse client instance
        auto_create: If True, create dictionary if missing. Default True.

    Returns:
        True if dictionary exists or was created successfully.

    Raises:
        RuntimeError: If auto_create=False and dictionary doesn't exist.
    """
    exists = check_spot_dictionary_exists(client)
    if exists:
        logger.debug("spot_prices_dict already exists")
        return True

    if not auto_create:
        raise RuntimeError(
            "spot_prices_dict not found. "
            "Run: clickhouse-client < schema/clickhouse/spot_prices_dict.sql"
        )

    logger.info("Creating spot_prices_dict dictionary...")
    client.command(SPOT_DICT_DDL)
    logger.info("spot_prices_dict created successfully")
    return True


def validate_schema_version(
    client: Client,
    database: str = "deribit",
    table: str = "options_trades",
) -> dict:
    """Validate schema matches expected v3.0.0 optimizations.

    ADR: 2025-12-10-schema-optimization - Validates:
    - ORDER BY includes timestamp
    - LowCardinality types for direction, underlying, option_type
    - Table exists

    Args:
        client: ClickHouse client instance
        database: Database name (default: deribit)
        table: Table name (default: options_trades)

    Returns:
        Dict with validation results:
        - valid: bool - Overall validation result
        - table_exists: bool
        - order_by_columns: list[str]
        - low_cardinality_columns: list[str]
        - errors: list[str] - Any validation errors

    Raises:
        RuntimeError: If table doesn't exist.
    """
    result = {
        "valid": False,
        "table_exists": False,
        "order_by_columns": [],
        "low_cardinality_columns": [],
        "errors": [],
    }

    # Check table exists
    table_check = client.query(
        f"""
        SELECT count() > 0
        FROM system.tables
        WHERE database = '{database}' AND name = '{table}'
        """
    )
    if not table_check.result_rows[0][0]:
        raise RuntimeError(f"Table {database}.{table} does not exist")

    result["table_exists"] = True

    # Get ORDER BY columns
    order_by_query = client.query(
        f"""
        SELECT sorting_key
        FROM system.tables
        WHERE database = '{database}' AND name = '{table}'
        """
    )
    sorting_key = order_by_query.result_rows[0][0] if order_by_query.result_rows else ""
    result["order_by_columns"] = [c.strip() for c in sorting_key.split(",") if c.strip()]

    # Get LowCardinality columns
    low_card_query = client.query(
        f"""
        SELECT name
        FROM system.columns
        WHERE database = '{database}'
          AND table = '{table}'
          AND type LIKE 'LowCardinality%'
        """
    )
    result["low_cardinality_columns"] = [row[0] for row in low_card_query.result_rows]

    # Validate v3.0.0 requirements
    expected_low_card = {"direction", "underlying", "option_type"}
    actual_low_card = set(result["low_cardinality_columns"])

    if not expected_low_card.issubset(actual_low_card):
        missing = expected_low_card - actual_low_card
        result["errors"].append(f"Missing LowCardinality columns: {missing}")

    # Check timestamp in ORDER BY (v3.0.0 requirement)
    if "timestamp" not in result["order_by_columns"]:
        result["errors"].append("timestamp not in ORDER BY (v3.0.0 requirement)")

    result["valid"] = len(result["errors"]) == 0
    return result


def get_mode_indicator() -> str:
    """Return current ClickHouse mode for CLI output.

    ADR: 2025-12-11-e2e-validation-pipeline - Mode visibility

    Reads CLICKHOUSE_MODE env var (default: "local") and constructs
    indicator string with host.

    Returns:
        String like "[LOCAL] localhost" or "[CLOUD] ebmf8f35lu.aws.clickhouse.cloud"
    """
    mode = os.environ.get("CLICKHOUSE_MODE", "local").upper()

    # Get host based on mode
    if mode == "CLOUD":
        host = os.environ.get(
            "CLICKHOUSE_HOST_CLOUD",
            os.environ.get("CLICKHOUSE_HOST_READONLY", "unknown"),
        )
    else:
        host = os.environ.get("CLICKHOUSE_HOST_LOCAL", "localhost")

    return f"[{mode}] {host}"


def get_connection_info() -> dict:
    """Return connection details for current mode.

    Returns:
        Dict with connection parameters:
        - mode: str - "local" or "cloud"
        - host: str
        - port: int
        - database: str
        - secure: bool
    """
    mode = os.environ.get("CLICKHOUSE_MODE", "local").lower()

    if mode == "cloud":
        return {
            "mode": "cloud",
            "host": os.environ.get(
                "CLICKHOUSE_HOST_CLOUD",
                os.environ.get("CLICKHOUSE_HOST_READONLY", ""),
            ),
            "port": int(os.environ.get("CLICKHOUSE_PORT_CLOUD", "443")),
            "database": os.environ.get("CLICKHOUSE_DATABASE", "deribit"),
            "secure": True,
        }
    else:
        return {
            "mode": "local",
            "host": os.environ.get("CLICKHOUSE_HOST_LOCAL", "localhost"),
            "port": int(os.environ.get("CLICKHOUSE_PORT_LOCAL", "8123")),
            "database": os.environ.get("CLICKHOUSE_DATABASE", "deribit"),
            "secure": False,
        }


if __name__ == "__main__":
    # CLI entry point for mise task
    import sys

    from dotenv import load_dotenv

    load_dotenv()

    from clickhouse_connect import get_client

    conn_info = get_connection_info()
    print(f"Mode: {get_mode_indicator()}")
    print(f"Connection: {conn_info}")

    try:
        client = get_client(
            host=conn_info["host"],
            port=conn_info["port"],
            database=conn_info["database"],
            secure=conn_info["secure"],
            username=os.environ.get("CLICKHOUSE_USER_READONLY", "default"),
            password=os.environ.get("CLICKHOUSE_PASSWORD_READONLY", ""),
        )

        # Validate infrastructure
        print("\nValidating infrastructure...")

        # Check/create dictionary
        dict_exists = ensure_spot_dictionary(client, auto_create=True)
        print(f"  spot_prices_dict: {'✓ exists' if dict_exists else '✗ missing'}")

        # Validate schema
        schema_result = validate_schema_version(client)
        if schema_result["valid"]:
            print("  Schema v3.0.0: ✓ validated")
        else:
            print("  Schema v3.0.0: ✗ errors")
            for error in schema_result["errors"]:
                print(f"    - {error}")
            sys.exit(1)

        print("\n✓ Infrastructure validation passed")

    except Exception as e:
        print(f"\n✗ Infrastructure validation failed: {e}")
        sys.exit(1)
