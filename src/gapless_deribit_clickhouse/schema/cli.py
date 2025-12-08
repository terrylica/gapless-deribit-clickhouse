"""
Schema CLI - command line interface for schema validation and database management.

Usage:
    python -m gapless_deribit_clickhouse.schema.cli validate
    python -m gapless_deribit_clickhouse.schema.cli diff
    python -m gapless_deribit_clickhouse.schema.cli init
    python -m gapless_deribit_clickhouse.schema.cli drop-legacy

ADR: 2025-12-08-clickhouse-naming-convention
"""

from __future__ import annotations

import sys

from gapless_deribit_clickhouse.clickhouse.config import get_credentials
from gapless_deribit_clickhouse.clickhouse.connection import get_client
from gapless_deribit_clickhouse.exceptions import CredentialError
from gapless_deribit_clickhouse.schema.introspector import (
    format_diff_report,
    validate_schema,
)
from gapless_deribit_clickhouse.schema.loader import load_schema

# Legacy database/table to drop during migration
LEGACY_DATABASE = "deribit_options"
LEGACY_TABLE = "trades"


def cmd_validate() -> int:
    """Validate YAML schema against live ClickHouse. Exit 0 if valid, 1 if drift."""
    try:
        get_credentials()
    except CredentialError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Configure credentials in .env (see .env.example)", file=sys.stderr)
        return 1

    schema = load_schema("options_trades")
    is_valid, diffs = validate_schema(schema)

    if is_valid:
        print("Schema validation passed - YAML matches live ClickHouse")
        return 0

    print(format_diff_report(diffs), file=sys.stderr)
    return 1


def cmd_diff() -> int:
    """Show schema differences between YAML and live ClickHouse."""
    try:
        get_credentials()
    except CredentialError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Configure credentials in .env (see .env.example)", file=sys.stderr)
        return 1

    schema = load_schema("options_trades")
    _, diffs = validate_schema(schema)

    print(format_diff_report(diffs))
    return 0


def cmd_init() -> int:
    """Create ClickHouse database and table from YAML schema."""
    try:
        get_credentials()
    except CredentialError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Configure credentials in .env (see .env.example)", file=sys.stderr)
        return 1

    schema = load_schema("options_trades")
    client = get_client()

    # Create database
    create_db_sql = f"CREATE DATABASE IF NOT EXISTS {schema.database}"
    print(f"Creating database: {schema.database}")
    client.command(create_db_sql)

    # Build CREATE TABLE statement from schema
    columns_sql = []
    for col in schema.columns:
        col_type = col.clickhouse_type
        if col.clickhouse_not_null and not col_type.startswith("Nullable"):
            col_def = f"    {col.name} {col_type}"
        else:
            col_def = f"    {col.name} {col_type}"
        columns_sql.append(col_def)

    order_by_clause = ", ".join(schema.clickhouse.order_by)
    partition_clause = schema.clickhouse.partition_by

    create_table_sql = f"""
CREATE TABLE IF NOT EXISTS {schema.full_table_name}
(
{chr(10).join(columns_sql)}
)
ENGINE = {schema.clickhouse.engine}
PARTITION BY {partition_clause}
ORDER BY ({order_by_clause})
"""

    print(f"Creating table: {schema.full_table_name}")
    client.command(create_table_sql)

    print(f"✓ Database and table created: {schema.full_table_name}")
    return 0


def cmd_drop_legacy() -> int:
    """Drop legacy deribit_options.trades database and table."""
    try:
        get_credentials()
    except CredentialError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Configure credentials in .env (see .env.example)", file=sys.stderr)
        return 1

    client = get_client()

    # Drop legacy table
    drop_table_sql = f"DROP TABLE IF EXISTS {LEGACY_DATABASE}.{LEGACY_TABLE}"
    print(f"Dropping legacy table: {LEGACY_DATABASE}.{LEGACY_TABLE}")
    client.command(drop_table_sql)

    # Drop legacy database
    drop_db_sql = f"DROP DATABASE IF EXISTS {LEGACY_DATABASE}"
    print(f"Dropping legacy database: {LEGACY_DATABASE}")
    client.command(drop_db_sql)

    print(f"✓ Legacy database dropped: {LEGACY_DATABASE}")
    return 0


def main() -> int:
    """CLI entrypoint."""
    if len(sys.argv) < 2:
        print("Usage: python -m gapless_deribit_clickhouse.schema.cli <command>")
        print("Commands: validate, diff, init, drop-legacy")
        return 1

    cmd = sys.argv[1]
    if cmd == "validate":
        return cmd_validate()
    elif cmd == "diff":
        return cmd_diff()
    elif cmd == "init":
        return cmd_init()
    elif cmd == "drop-legacy":
        return cmd_drop_legacy()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print("Commands: validate, diff, init, drop-legacy", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
