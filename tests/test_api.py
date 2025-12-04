"""
Integration tests for public API.

These tests require ClickHouse credentials to be configured.
Skip if credentials not available.

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
"""

import pytest

from gapless_deribit_clickhouse.exceptions import CredentialError, QueryError


@pytest.fixture
def skip_without_credentials():
    """Skip test if ClickHouse credentials not configured."""
    try:
        from gapless_deribit_clickhouse.clickhouse.config import get_credentials

        get_credentials()
    except CredentialError:
        pytest.skip("ClickHouse credentials not configured")


class TestFetchTrades:
    """Tests for fetch_trades function."""

    def test_requires_constraint(self):
        """fetch_trades requires at least one constraint."""
        from gapless_deribit_clickhouse.api import fetch_trades

        with pytest.raises(QueryError, match="Must specify at least one"):
            fetch_trades()

    def test_with_limit(self, skip_without_credentials):
        """fetch_trades with limit returns DataFrame."""
        from gapless_deribit_clickhouse.api import fetch_trades

        df = fetch_trades(underlying="BTC", limit=10)

        assert len(df) <= 10
        if len(df) > 0:
            assert "trade_id" in df.columns
            assert "instrument_name" in df.columns
            assert "underlying" in df.columns


class TestFetchTickerSnapshots:
    """Tests for fetch_ticker_snapshots function."""

    def test_requires_constraint(self):
        """fetch_ticker_snapshots requires at least one constraint."""
        from gapless_deribit_clickhouse.api import fetch_ticker_snapshots

        with pytest.raises(QueryError, match="Must specify at least one"):
            fetch_ticker_snapshots()

    def test_with_limit(self, skip_without_credentials):
        """fetch_ticker_snapshots with limit returns DataFrame."""
        from gapless_deribit_clickhouse.api import fetch_ticker_snapshots

        df = fetch_ticker_snapshots(underlying="BTC", limit=10)

        assert len(df) <= 10
        if len(df) > 0:
            assert "instrument_name" in df.columns
            assert "open_interest" in df.columns
            assert "delta" in df.columns


class TestGetActiveInstruments:
    """Tests for get_active_instruments function."""

    def test_returns_list(self, skip_without_credentials):
        """get_active_instruments returns list of strings."""
        from gapless_deribit_clickhouse.api import get_active_instruments

        instruments = get_active_instruments(underlying="BTC")

        assert isinstance(instruments, list)
        # May be empty if no recent snapshots
        for inst in instruments:
            assert isinstance(inst, str)
            assert "BTC" in inst
