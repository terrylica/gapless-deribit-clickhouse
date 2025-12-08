"""
Schema loader for gapless-deribit-clickhouse.

Loads and parses YAML schema files that serve as the single source of truth
for all generated types, DDL, and documentation.

Usage:
    from gapless_deribit_clickhouse.schema.loader import load_schema

    schema = load_schema("options_trades")
    print(schema.title)
    print(schema.columns)

ADR: 2025-12-08-clickhouse-naming-convention
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from gapless_deribit_clickhouse.exceptions import SchemaError


def _find_schema_dir() -> Path:
    """
    Find the schema directory relative to package or project root.

    Searches in order:
    1. Relative to this file (when installed as package)
    2. Project root (when running from source)
    3. Environment variable override
    """
    # Option 1: Installed package - schema is at package_root/../../../schema
    package_dir = Path(__file__).parent.parent.parent.parent
    schema_dir = package_dir / "schema" / "clickhouse"
    if schema_dir.exists():
        return schema_dir

    # Option 2: Project root from CWD
    cwd = Path.cwd()
    schema_dir = cwd / "schema" / "clickhouse"
    if schema_dir.exists():
        return schema_dir

    # Option 3: Environment variable override
    env_path = os.environ.get("GAPLESS_DERIBIT_SCHEMA_DIR")
    if env_path:
        schema_dir = Path(env_path)
        if schema_dir.exists():
            return schema_dir

    raise SchemaError(
        "Could not find schema directory. "
        "Ensure schema/clickhouse/ exists in project root or set GAPLESS_DERIBIT_SCHEMA_DIR."
    )


@dataclass
class ClickHouseConfig:
    """ClickHouse-specific configuration from x-clickhouse extension."""

    database: str
    table: str
    engine: str
    order_by: list[str]
    partition_by: str
    settings: dict[str, Any]


@dataclass
class ColumnConfig:
    """Configuration for a single column."""

    name: str
    json_type: str | list[str]
    description: str
    clickhouse_type: str
    clickhouse_not_null: bool
    pandas_dtype: str
    is_derived: bool
    is_critical: bool
    minimum: float | None
    enum_values: list[str] | None


@dataclass
class Schema:
    """
    Parsed schema representing a ClickHouse table.

    Attributes:
        title: Human-readable title
        description: Detailed description for documentation
        clickhouse: ClickHouse-specific configuration
        columns: List of column configurations
        required_columns: List of required column names
        raw: Original parsed YAML dict for custom access
    """

    title: str
    description: str
    clickhouse: ClickHouseConfig
    columns: list[ColumnConfig]
    required_columns: list[str]
    raw: dict[str, Any]

    @property
    def database(self) -> str:
        """Get the database name."""
        return self.clickhouse.database

    @property
    def table(self) -> str:
        """Get the table name."""
        return self.clickhouse.table

    @property
    def full_table_name(self) -> str:
        """Get fully qualified table name (database.table)."""
        return f"{self.database}.{self.table}"

    @property
    def derived_columns(self) -> list[ColumnConfig]:
        """Get columns that are derived from other fields."""
        return [col for col in self.columns if col.is_derived]

    @property
    def source_columns(self) -> list[ColumnConfig]:
        """Get columns that come directly from API."""
        return [col for col in self.columns if not col.is_derived]


def _parse_column(name: str, props: dict[str, Any]) -> ColumnConfig:
    """Parse a single column definition from YAML."""
    x_ch = props.get("x-clickhouse", {})
    x_pandas = props.get("x-pandas", {})

    return ColumnConfig(
        name=name,
        json_type=props.get("type", "string"),
        description=props.get("description", ""),
        clickhouse_type=x_ch.get("type", "String"),
        clickhouse_not_null=x_ch.get("not_null", False),
        pandas_dtype=x_pandas.get("dtype", "object"),
        is_derived=props.get("x-derived", False),
        is_critical=props.get("x-critical") is not None,
        minimum=props.get("minimum"),
        enum_values=props.get("enum"),
    )


def _parse_clickhouse_config(x_clickhouse: dict[str, Any]) -> ClickHouseConfig:
    """Parse ClickHouse configuration from x-clickhouse extension."""
    return ClickHouseConfig(
        database=x_clickhouse.get("database", "default"),
        table=x_clickhouse.get("table", "unknown"),
        engine=x_clickhouse.get("engine", "MergeTree()"),
        order_by=x_clickhouse.get("order_by", []),
        partition_by=x_clickhouse.get("partition_by", ""),
        settings=x_clickhouse.get("settings", {}),
    )


def load_schema(name: str) -> Schema:
    """
    Load a schema from YAML file.

    Args:
        name: Schema name (without .yaml extension).
              Options: "options_trades"

    Returns:
        Parsed Schema object with typed access to all fields

    Raises:
        SchemaError: If schema file doesn't exist or is invalid
    """
    schema_dir = _find_schema_dir()
    schema_path = schema_dir / f"{name}.yaml"

    if not schema_path.exists():
        raise SchemaError(f"Schema file not found: {schema_path}")

    with open(schema_path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise SchemaError(f"Empty schema file: {schema_path}")

    # Parse columns from properties
    properties = raw.get("properties", {})
    columns = [_parse_column(col_name, props) for col_name, props in properties.items()]

    return Schema(
        title=raw.get("title", ""),
        description=raw.get("description", ""),
        clickhouse=_parse_clickhouse_config(raw.get("x-clickhouse", {})),
        columns=columns,
        required_columns=raw.get("required", []),
        raw=raw,
    )


def get_schema_path(name: str) -> Path:
    """
    Get the path to a schema file.

    Args:
        name: Schema name (without .yaml extension)

    Returns:
        Path to the schema file
    """
    schema_dir = _find_schema_dir()
    return schema_dir / f"{name}.yaml"


def list_schemas() -> list[str]:
    """
    List available schema names.

    Returns:
        List of schema names (without .yaml extension)
    """
    schema_dir = _find_schema_dir()
    return [p.stem for p in schema_dir.glob("*.yaml") if not p.stem.startswith("_")]
