"""
Integration tests for public API.

These tests require ClickHouse credentials to be configured.
Skip if credentials not available.

ADR: 2025-12-05-trades-only-architecture-pivot
"""

import pytest

from gapless_deribit_clickhouse.exceptions import CredentialError


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

        # ADR: 2025-12-05-trades-only-architecture-pivot - fail-fast validation
        with pytest.raises(ValueError, match="At least one constraint required"):
            fetch_trades()

    def test_empty_string_start_rejected(self):
        """Empty string start is explicit error."""
        from gapless_deribit_clickhouse.api import fetch_trades

        with pytest.raises(ValueError, match="start cannot be empty string"):
            fetch_trades(start="")

    def test_empty_string_end_rejected(self):
        """Empty string end is explicit error."""
        from gapless_deribit_clickhouse.api import fetch_trades

        with pytest.raises(ValueError, match="end cannot be empty string"):
            fetch_trades(end="")

    def test_date_ordering_validation(self):
        """Start must be before or equal to end."""
        from gapless_deribit_clickhouse.api import fetch_trades

        with pytest.raises(ValueError, match="start .* must be <= end"):
            fetch_trades(start="2024-02-01", end="2024-01-01")

    def test_negative_limit_rejected(self):
        """Negative limit is explicit error."""
        from gapless_deribit_clickhouse.api import fetch_trades

        with pytest.raises(ValueError, match="limit must be non-negative"):
            fetch_trades(limit=-1)

    def test_with_limit(self, skip_without_credentials):
        """fetch_trades with limit returns DataFrame."""
        from gapless_deribit_clickhouse.api import fetch_trades

        df = fetch_trades(underlying="BTC", limit=10)

        assert len(df) <= 10
        if len(df) > 0:
            assert "trade_id" in df.columns
            assert "instrument_name" in df.columns
            assert "underlying" in df.columns
