"""
Schema introspector - validates YAML schema vs live ClickHouse.

Compares the YAML schema (Single Source of Truth) against the live
ClickHouse table to detect schema drift.

Usage:
    from gapless_deribit_clickhouse.schema.introspector import validate_schema
    from gapless_deribit_clickhouse.schema.loader import load_schema

    schema = load_schema("options_trades")
    is_valid, diffs = validate_schema(schema)

ADR: 2025-12-07-schema-first-e2e-validation
"""

from __future__ import annotations

from dataclasses import dataclass

from gapless_deribit_clickhouse.clickhouse.connection import get_client
from gapless_deribit_clickhouse.schema.loader import Schema


@dataclass
class ColumnInfo:
    """Live ClickHouse column information."""

    name: str
    type: str
    is_nullable: bool
    comment: str


@dataclass
class SchemaDiff:
    """A single difference between YAML and live schema."""

    category: str  # MISSING, EXTRA, TYPE_MISMATCH, NULLABILITY_MISMATCH
    column: str
    message: str
    yaml_value: str | None = None
    live_value: str | None = None


def _get_live_columns(database: str, table: str) -> dict[str, ColumnInfo]:
    """
    Fetch column information from live ClickHouse table.

    Args:
        database: Database name
        table: Table name

    Returns:
        Dict mapping column name to ColumnInfo
    """
    client = get_client()
    query = f"""
        SELECT
            name,
            type,
            comment
        FROM system.columns
        WHERE database = '{database}' AND table = '{table}'
    """
    result = client.query(query)
    columns = {}
    for row in result.result_rows:
        name, col_type, comment = row
        is_nullable = col_type.startswith("Nullable(")
        columns[name] = ColumnInfo(
            name=name,
            type=col_type,
            is_nullable=is_nullable,
            comment=comment or "",
        )
    return columns


def validate_schema(schema: Schema) -> tuple[bool, list[SchemaDiff]]:
    """
    Validate YAML schema matches live ClickHouse table.

    Compares:
    - Column existence
    - Column types
    - Nullability

    Args:
        schema: Parsed Schema object from loader

    Returns:
        Tuple of (is_valid, list of SchemaDiff)
    """
    live_columns = _get_live_columns(schema.database, schema.table)
    diffs: list[SchemaDiff] = []

    # Check YAML columns against live
    for col in schema.columns:
        if col.name not in live_columns:
            diffs.append(
                SchemaDiff(
                    category="MISSING",
                    column=col.name,
                    message=f"Column {col.name} exists in YAML but not in ClickHouse",
                    yaml_value=col.clickhouse_type,
                )
            )
            continue

        live_col = live_columns[col.name]

        # Type comparison (normalize for comparison)
        yaml_type = col.clickhouse_type
        live_type = live_col.type
        if yaml_type != live_type:
            diffs.append(
                SchemaDiff(
                    category="TYPE_MISMATCH",
                    column=col.name,
                    message=f"Type mismatch for {col.name}",
                    yaml_value=yaml_type,
                    live_value=live_type,
                )
            )

        # Nullability comparison
        yaml_nullable = not col.clickhouse_not_null
        if yaml_nullable != live_col.is_nullable:
            diffs.append(
                SchemaDiff(
                    category="NULLABILITY_MISMATCH",
                    column=col.name,
                    message=f"Nullability mismatch for {col.name}",
                    yaml_value="nullable" if yaml_nullable else "not null",
                    live_value="nullable" if live_col.is_nullable else "not null",
                )
            )

    # Check for extra columns in live that aren't in YAML
    yaml_column_names = {col.name for col in schema.columns}
    for live_name in live_columns:
        if live_name not in yaml_column_names:
            diffs.append(
                SchemaDiff(
                    category="EXTRA",
                    column=live_name,
                    message=f"Column {live_name} exists in ClickHouse but not in YAML",
                    live_value=live_columns[live_name].type,
                )
            )

    return len(diffs) == 0, diffs


def format_diff_report(diffs: list[SchemaDiff]) -> str:
    """
    Format schema diffs as human-readable report.

    Args:
        diffs: List of SchemaDiff objects

    Returns:
        Formatted string report
    """
    if not diffs:
        return "Schema is in sync - no differences found."

    lines = [f"Schema drift detected ({len(diffs)} issues):"]
    lines.append("")

    for diff in diffs:
        if diff.category == "MISSING":
            lines.append(f"  [MISSING] {diff.column}: {diff.yaml_value}")
        elif diff.category == "EXTRA":
            lines.append(f"  [EXTRA] {diff.column}: {diff.live_value}")
        elif diff.category == "TYPE_MISMATCH":
            lines.append(f"  [TYPE] {diff.column}: YAML={diff.yaml_value}, Live={diff.live_value}")
        elif diff.category == "NULLABILITY_MISMATCH":
            lines.append(
                f"  [NULL] {diff.column}: YAML={diff.yaml_value}, Live={diff.live_value}"
            )

    return "\n".join(lines)
