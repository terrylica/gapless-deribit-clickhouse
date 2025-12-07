"""
Schema CLI - command line interface for schema validation.

Usage:
    python -m gapless_deribit_clickhouse.schema.cli validate
    python -m gapless_deribit_clickhouse.schema.cli diff

ADR: 2025-12-07-schema-first-e2e-validation
"""

from __future__ import annotations

import sys

from gapless_deribit_clickhouse.clickhouse.config import get_credentials
from gapless_deribit_clickhouse.exceptions import CredentialError
from gapless_deribit_clickhouse.schema.introspector import (
    format_diff_report,
    validate_schema,
)
from gapless_deribit_clickhouse.schema.loader import load_schema


def cmd_validate() -> int:
    """Validate YAML schema against live ClickHouse. Exit 0 if valid, 1 if drift."""
    try:
        get_credentials()
    except CredentialError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Configure credentials in .env (see .env.example)", file=sys.stderr)
        return 1

    schema = load_schema("deribit_trades")
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

    schema = load_schema("deribit_trades")
    _, diffs = validate_schema(schema)

    print(format_diff_report(diffs))
    return 0


def main() -> int:
    """CLI entrypoint."""
    if len(sys.argv) < 2:
        print("Usage: python -m gapless_deribit_clickhouse.schema.cli <command>")
        print("Commands: validate, diff")
        return 1

    cmd = sys.argv[1]
    if cmd == "validate":
        return cmd_validate()
    elif cmd == "diff":
        return cmd_diff()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print("Commands: validate, diff", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
