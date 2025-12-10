# ADR: 2025-12-10-deribit-options-alpha-features
"""Tests for features.contract_selector module.

These tests validate SQL query generation without requiring ClickHouse.
Integration tests requiring ClickHouse are marked with @pytest.mark.e2e.
"""

import pytest

from gapless_deribit_clickhouse.features.config import DEFAULT_CONFIG, FeatureConfig
from gapless_deribit_clickhouse.features.contract_selector import (
    build_contract_selection_query,
)


class TestBuildContractSelectionQuery:
    """Test SQL query generation for contract selection."""

    def test_all_strategy_returns_simple_select(self) -> None:
        """Test 'all' strategy returns unfiltered SELECT."""
        query = build_contract_selection_query(
            strategy="all",
            start="2024-01-01",
            end="2024-06-01",
            underlying="BTC",
        )

        assert "SELECT" in query
        assert "options_trades" in query
        assert "2024-01-01" in query
        assert "2024-06-01" in query
        assert "BTC" in query
        # Should NOT have argMin (no front-month selection)
        assert "argMin" not in query

    def test_front_month_uses_argmin(self) -> None:
        """Test front_month strategy uses argMin pattern."""
        query = build_contract_selection_query(
            strategy="front_month",
            start="2024-01-01",
            end="2024-06-01",
            underlying="BTC",
        )

        # Should use argMin for efficient front-month selection
        assert "argMin" in query
        assert "dateDiff" in query
        assert "toStartOfFifteenMinutes" in query

    def test_front_atm_includes_moneyness_filter(self) -> None:
        """Test front_atm strategy adds moneyness filter."""
        query = build_contract_selection_query(
            strategy="front_atm",
            start="2024-01-01",
            end="2024-06-01",
            underlying="BTC",
        )

        # Should have moneyness filter
        assert "strike / index_price" in query
        assert "BETWEEN" in query
        # Default ATM width is 0.05, so bounds are 0.95 and 1.05
        assert "0.95" in query
        assert "1.05" in query

    def test_front_atm_liquid_includes_volume_filter(self) -> None:
        """Test front_atm_liquid strategy adds liquidity filter."""
        query = build_contract_selection_query(
            strategy="front_atm_liquid",
            start="2024-01-01",
            end="2024-06-01",
            underlying="BTC",
        )

        # Should have volume filter
        assert "total_volume" in query
        assert ">=" in query
        # Default min_volume is 10.0
        assert "10.0" in query

    def test_custom_atm_width(self) -> None:
        """Test custom ATM width is applied."""
        config = FeatureConfig(atm_width=0.10)  # +/- 10%

        query = build_contract_selection_query(
            strategy="front_atm",
            start="2024-01-01",
            end="2024-06-01",
            underlying="BTC",
            config=config,
        )

        # Bounds should be 0.90 and 1.10
        assert "0.9" in query
        assert "1.1" in query

    def test_custom_min_volume(self) -> None:
        """Test custom min volume is applied."""
        config = FeatureConfig(min_volume=50.0)

        query = build_contract_selection_query(
            strategy="front_atm_liquid",
            start="2024-01-01",
            end="2024-06-01",
            underlying="BTC",
            config=config,
        )

        assert "50.0" in query

    def test_eth_underlying(self) -> None:
        """Test ETH underlying is included in query."""
        query = build_contract_selection_query(
            strategy="front_month",
            start="2024-01-01",
            end="2024-06-01",
            underlying="ETH",
        )

        assert "ETH" in query

    def test_custom_database_and_table(self) -> None:
        """Test custom database and table names."""
        query = build_contract_selection_query(
            strategy="all",
            start="2024-01-01",
            end="2024-06-01",
            underlying="BTC",
            database="custom_db",
            table="custom_table",
        )

        assert "custom_db.custom_table" in query


class TestSpotProviderQueries:
    """Test SQL query generation for spot price enrichment."""

    def test_spot_enriched_query_includes_dictget(self) -> None:
        """Test spot enrichment uses dictGet pattern."""
        from gapless_deribit_clickhouse.features.spot_provider import (
            build_spot_enriched_query,
        )

        inner_query = "SELECT * FROM options_trades"
        query = build_spot_enriched_query(
            inner_query=inner_query,
            underlying="BTC",
        )

        # Should use dictGet for efficient lookups
        assert "dictGet" in query
        assert "spot_prices_dict" in query
        assert "BTCUSDT" in query  # Binance symbol
        assert "coalesce" in query  # Hybrid approach

    def test_spot_enriched_direct_query(self) -> None:
        """Test direct spot enrichment without inner query."""
        from gapless_deribit_clickhouse.features.spot_provider import (
            build_spot_enriched_query,
        )

        query = build_spot_enriched_query(
            inner_query=None,
            underlying="BTC",
            start="2024-01-01",
            end="2024-06-01",
        )

        assert "dictGet" in query
        assert "2024-01-01" in query
        assert "moneyness" in query

    def test_spot_symbol_mapping(self) -> None:
        """Test underlying to spot symbol mapping."""
        from gapless_deribit_clickhouse.features.spot_provider import (
            UNDERLYING_TO_SPOT_SYMBOL,
        )

        assert UNDERLYING_TO_SPOT_SYMBOL["BTC"] == "BTCUSDT"
        assert UNDERLYING_TO_SPOT_SYMBOL["ETH"] == "ETHUSDT"


class TestMoneynessQueries:
    """Test SQL query generation for moneyness aggregations."""

    def test_moneyness_pivot_query_includes_buckets(self) -> None:
        """Test moneyness query includes all bucket aggregations."""
        from gapless_deribit_clickhouse.features.moneyness import (
            build_moneyness_aggregation_query,
        )

        inner_query = "SELECT * FROM enriched_trades"
        query = build_moneyness_aggregation_query(inner_query, pivot=True)

        # Should have all bucket columns
        assert "atm_iv_mean" in query
        assert "otm_put_iv_mean" in query
        assert "otm_call_iv_mean" in query
        assert "deep_otm_put_iv_mean" in query
        assert "deep_otm_call_iv_mean" in query

        # Should have derived features
        assert "put_call_skew" in query
        assert "smile_curvature" in query
        assert "wing_ratio" in query

    def test_moneyness_long_format_query(self) -> None:
        """Test moneyness query in long format."""
        from gapless_deribit_clickhouse.features.moneyness import (
            build_moneyness_aggregation_query,
        )

        inner_query = "SELECT * FROM enriched_trades"
        query = build_moneyness_aggregation_query(inner_query, pivot=False)

        # Should have bucket column for grouping
        assert "moneyness_bucket" in query
        assert "GROUP BY ts, moneyness_bucket" in query

    def test_moneyness_thresholds_from_config(self) -> None:
        """Test custom moneyness thresholds are used."""
        from gapless_deribit_clickhouse.features.moneyness import (
            build_moneyness_aggregation_query,
        )

        # Custom thresholds
        config = FeatureConfig(
            moneyness_thresholds=(0.85, 0.92, 1.08, 1.15)
        )

        inner_query = "SELECT * FROM enriched_trades"
        query = build_moneyness_aggregation_query(inner_query, pivot=True, config=config)

        assert "0.85" in query
        assert "0.92" in query
        assert "1.08" in query
        assert "1.15" in query
