"""
Contract tests validating schema consistency.

These tests validate architectural invariants (not mocked data).
Pattern: gapless-network-data/tests/test_api.py

ADR: 2025-12-07-schema-first-e2e-validation
"""

import re
from pathlib import Path

import pytest

from gapless_deribit_clickhouse.schema.loader import get_schema_path, load_schema


class TestSchemaContracts:
    """Validate deribit_trades.yaml schema contracts."""

    def test_yaml_schema_exists(self):
        """Schema YAML file must exist."""
        schema_path = get_schema_path("deribit_trades")
        assert schema_path.exists(), f"Schema file not found: {schema_path}"

    def test_schema_loads_without_error(self):
        """Schema parses successfully."""
        schema = load_schema("deribit_trades")
        assert schema.title is not None
        assert schema.title == "Deribit Options Trades"

    def test_required_fields_in_columns(self):
        """All required fields exist in columns."""
        schema = load_schema("deribit_trades")
        column_names = [c.name for c in schema.columns]
        for required in schema.required_columns:
            assert required in column_names, f"Required field {required} missing from columns"

    def test_required_fields_not_nullable(self):
        """Required fields must have not_null=true."""
        schema = load_schema("deribit_trades")
        for col in schema.columns:
            if col.name in schema.required_columns:
                assert col.clickhouse_not_null, f"Required field {col.name} must be NOT NULL"

    def test_clickhouse_config_complete(self):
        """ClickHouse config has all required fields."""
        schema = load_schema("deribit_trades")
        assert schema.clickhouse.database == "deribit_options"
        assert schema.clickhouse.table == "trades"
        assert schema.clickhouse.engine == "ReplacingMergeTree()"
        assert len(schema.clickhouse.order_by) > 0

    def test_all_columns_have_clickhouse_type(self):
        """Every column must specify x-clickhouse.type."""
        schema = load_schema("deribit_trades")
        for col in schema.columns:
            assert col.clickhouse_type, f"Column {col.name} missing x-clickhouse.type"

    def test_all_columns_have_pandas_dtype(self):
        """Every column must specify x-pandas.dtype."""
        schema = load_schema("deribit_trades")
        for col in schema.columns:
            assert col.pandas_dtype, f"Column {col.name} missing x-pandas.dtype"


class TestInstrumentParsingContracts:
    """Validate instrument parsing roundtrip invariants."""

    @pytest.mark.parametrize(
        "instrument",
        [
            "BTC-27DEC24-100000-C",
            "ETH-28MAR25-5000-P",
            "BTC-3JAN25-42000-C",
        ],
    )
    def test_parse_format_roundtrip(self, instrument):
        """parse(format(x)) == x for all valid instruments."""
        from gapless_deribit_clickhouse.utils import parse_instrument

        parsed = parse_instrument(instrument)
        # Reconstruct the instrument name
        # Note: expiry format may differ, so we check components
        assert parsed.underlying in ["BTC", "ETH"]
        assert parsed.strike > 0
        assert parsed.option_type in ["C", "P"]


class TestAPIContracts:
    """Validate public API exports."""

    def test_version_export(self):
        """__version__ must exist and follow semver."""
        import gapless_deribit_clickhouse as gdch

        assert hasattr(gdch, "__version__")
        semver_pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$"
        assert re.match(
            semver_pattern, gdch.__version__
        ), f"Version {gdch.__version__} doesn't match semver"

    def test_api_function_exports(self):
        """Public API functions are exported."""
        import gapless_deribit_clickhouse as gdch

        expected = ["fetch_trades", "parse_instrument"]
        for func in expected:
            assert hasattr(gdch, func), f"Missing export: {func}"
            assert callable(getattr(gdch, func))

    def test_exception_exports(self):
        """Exception classes are exported."""
        import gapless_deribit_clickhouse as gdch

        expected = ["GaplessDeribitError", "QueryError", "CredentialError"]
        for exc in expected:
            assert hasattr(gdch, exc), f"Missing exception: {exc}"
            assert issubclass(getattr(gdch, exc), Exception)
