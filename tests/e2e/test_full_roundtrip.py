"""
Full roundtrip E2E tests.

Tests the complete data flow:
Deribit API -> collect_trades() -> ClickHouse -> fetch_trades() -> DataFrame

ADR: 2025-12-08-clickhouse-naming-convention
"""

import pytest


@pytest.mark.e2e
@pytest.mark.slow
class TestFullRoundtrip:
    """End-to-end validation with real data."""

    def test_fetch_trades_returns_real_data(self, skip_without_credentials):
        """fetch_trades() returns real trade data from ClickHouse."""
        from gapless_deribit_clickhouse import fetch_trades

        # Fetch a small sample of trades
        df = fetch_trades(underlying="BTC", limit=10)

        assert df is not None
        assert len(df) > 0
        assert "trade_id" in df.columns
        assert "instrument_name" in df.columns

    def test_instrument_parsing_on_real_trades(self, skip_without_credentials):
        """All real trades have valid instrument names."""
        from gapless_deribit_clickhouse import fetch_trades, parse_instrument

        df = fetch_trades(underlying="BTC", limit=100)

        for instrument in df["instrument_name"].unique():
            # Should not raise
            parsed = parse_instrument(instrument)
            assert parsed.underlying == "BTC"
            assert parsed.option_type in ["C", "P"]

    def test_required_fields_not_null(self, skip_without_credentials):
        """Required fields are never null in real data."""
        from gapless_deribit_clickhouse import fetch_trades
        from gapless_deribit_clickhouse.schema.loader import load_schema

        schema = load_schema("options_trades")
        df = fetch_trades(underlying="BTC", limit=100)

        for required_field in schema.required_columns:
            if required_field in df.columns:
                null_count = df[required_field].isnull().sum()
                assert null_count == 0, f"Required field {required_field} has {null_count} nulls"

    def test_timestamp_ordering(self, skip_without_credentials):
        """Trades are ordered by timestamp DESC."""
        from gapless_deribit_clickhouse import fetch_trades

        df = fetch_trades(underlying="BTC", limit=100)

        if len(df) > 1:
            # Assuming default order is DESC
            timestamps = df["timestamp"].tolist()
            assert timestamps == sorted(timestamps, reverse=True), (
                "Trades not ordered by timestamp DESC"
            )


@pytest.mark.e2e
@pytest.mark.slow
class TestDeribitAPIIntegration:
    """Direct Deribit API validation."""

    def test_api_reachable(self, skip_without_deribit):
        """Deribit API is reachable and returns valid response."""
        import httpx

        with httpx.Client(timeout=10) as client:
            response = client.get(
                "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time",
                params={
                    "currency": "BTC",
                    "kind": "option",
                    "count": 1,
                    "start_timestamp": 0,
                    "end_timestamp": 1704067200000,  # Jan 1, 2024
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "result" in data


@pytest.mark.e2e
@pytest.mark.slow
class TestSchemaValidation:
    """Schema introspection tests against live ClickHouse."""

    def test_schema_matches_live_clickhouse(self, skip_without_credentials):
        """YAML schema matches live ClickHouse table structure."""
        from gapless_deribit_clickhouse.schema.introspector import (
            format_diff_report,
            validate_schema,
        )
        from gapless_deribit_clickhouse.schema.loader import load_schema

        schema = load_schema("options_trades")
        is_valid, diffs = validate_schema(schema)

        if not is_valid:
            report = format_diff_report(diffs)
            pytest.fail(f"Schema drift detected:\n{report}")
