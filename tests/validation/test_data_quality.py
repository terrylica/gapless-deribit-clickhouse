# ADR: 2025-12-11-e2e-validation-pipeline
"""Tests for validation data_quality module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest


class TestGetQualityMetrics:
    """Test get_quality_metrics() function."""

    def test_returns_all_expected_fields(self):
        """Should return dict with all expected metric fields."""
        from gapless_deribit_clickhouse.validation.data_quality import (
            get_quality_metrics,
        )

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = [
            (
                1000,  # total_rows
                950,  # unique_trades
                datetime(2024, 1, 1),  # earliest
                datetime(2024, 12, 31),  # latest
                365,  # date_span_days
                10,  # null_iv_count
                5,  # null_index_count
                2.74,  # avg_trades_per_hour
            )
        ]
        mock_result.column_names = [
            "total_rows",
            "unique_trades",
            "earliest",
            "latest",
            "date_span_days",
            "null_iv_count",
            "null_index_count",
            "avg_trades_per_hour",
        ]
        mock_client.query.return_value = mock_result

        metrics = get_quality_metrics(mock_client)

        assert metrics["total_rows"] == 1000
        assert metrics["unique_trades"] == 950
        assert metrics["date_span_days"] == 365
        assert "dedup_rate" in metrics
        assert "null_iv_rate" in metrics
        assert "null_index_rate" in metrics

    def test_dedup_rate_calculation(self):
        """Should correctly calculate dedup rate."""
        from gapless_deribit_clickhouse.validation.data_quality import (
            get_quality_metrics,
        )

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = [
            (100, 95, datetime(2024, 1, 1), datetime(2024, 1, 2), 1, 0, 0, 1.0)
        ]
        mock_result.column_names = [
            "total_rows",
            "unique_trades",
            "earliest",
            "latest",
            "date_span_days",
            "null_iv_count",
            "null_index_count",
            "avg_trades_per_hour",
        ]
        mock_client.query.return_value = mock_result

        metrics = get_quality_metrics(mock_client)

        assert metrics["dedup_rate"] == 0.95

    def test_raises_on_empty_table(self):
        """Should raise RuntimeError when table is empty."""
        from gapless_deribit_clickhouse.validation.data_quality import (
            get_quality_metrics,
        )

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = []
        mock_client.query.return_value = mock_result

        with pytest.raises(RuntimeError, match="No data"):
            get_quality_metrics(mock_client)

    def test_null_rate_calculation(self):
        """Should correctly calculate null rates."""
        from gapless_deribit_clickhouse.validation.data_quality import (
            get_quality_metrics,
        )

        mock_client = MagicMock()
        mock_result = MagicMock()
        # 100 total, 10 null IV, 20 null index
        mock_result.result_rows = [
            (100, 100, datetime(2024, 1, 1), datetime(2024, 1, 2), 1, 10, 20, 1.0)
        ]
        mock_result.column_names = [
            "total_rows",
            "unique_trades",
            "earliest",
            "latest",
            "date_span_days",
            "null_iv_count",
            "null_index_count",
            "avg_trades_per_hour",
        ]
        mock_client.query.return_value = mock_result

        metrics = get_quality_metrics(mock_client)

        assert metrics["null_iv_rate"] == 0.1  # 10/100
        assert metrics["null_index_rate"] == 0.2  # 20/100


class TestGetGapAnalysis:
    """Test get_gap_analysis() function."""

    def test_returns_list_of_gaps(self):
        """Should return list of gap dictionaries."""
        from gapless_deribit_clickhouse.validation.data_quality import (
            get_gap_analysis,
        )

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = [
            (datetime(2024, 1, 1, 10, 0), datetime(2024, 1, 1, 18, 0), 8),
            (datetime(2024, 2, 1, 0, 0), datetime(2024, 2, 1, 6, 0), 6),
        ]
        mock_client.query.return_value = mock_result

        gaps = get_gap_analysis(mock_client, threshold_hours=4)

        assert len(gaps) == 2
        assert gaps[0]["gap_hours"] == 8
        assert gaps[1]["gap_hours"] == 6
        assert "gap_start" in gaps[0]
        assert "gap_end" in gaps[0]

    def test_returns_empty_list_when_no_gaps(self):
        """Should return empty list when no gaps found."""
        from gapless_deribit_clickhouse.validation.data_quality import (
            get_gap_analysis,
        )

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = []
        mock_client.query.return_value = mock_result

        gaps = get_gap_analysis(mock_client, threshold_hours=4)

        assert gaps == []

    def test_uses_threshold_parameter(self):
        """Should use threshold_hours in query."""
        from gapless_deribit_clickhouse.validation.data_quality import (
            get_gap_analysis,
        )

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = []
        mock_client.query.return_value = mock_result

        get_gap_analysis(mock_client, threshold_hours=12)

        # Verify query contains threshold
        call_args = mock_client.query.call_args[0][0]
        assert "12" in call_args


class TestGetCoverageStats:
    """Test get_coverage_stats() function."""

    def test_returns_coverage_dict(self):
        """Should return coverage statistics dictionary."""
        from gapless_deribit_clickhouse.validation.data_quality import (
            get_coverage_stats,
        )

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = [
            (
                "BTC",  # underlying
                5000,  # trade_count
                150,  # unique_instruments
                datetime(2024, 1, 1),  # earliest
                datetime(2024, 12, 31),  # latest
                0.01,  # null_iv_rate
                0.005,  # null_index_rate
            )
        ]
        mock_result.column_names = [
            "underlying",
            "trade_count",
            "unique_instruments",
            "earliest",
            "latest",
            "null_iv_rate",
            "null_index_rate",
        ]
        mock_client.query.return_value = mock_result

        stats = get_coverage_stats(mock_client, underlying="BTC")

        assert stats["underlying"] == "BTC"
        assert stats["trade_count"] == 5000
        assert stats["unique_instruments"] == 150

    def test_returns_empty_stats_when_no_data(self):
        """Should return zero-value dict when no data for underlying."""
        from gapless_deribit_clickhouse.validation.data_quality import (
            get_coverage_stats,
        )

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = []
        mock_client.query.return_value = mock_result

        stats = get_coverage_stats(mock_client, underlying="SOL")

        assert stats["underlying"] == "SOL"
        assert stats["trade_count"] == 0
        assert stats["earliest"] is None
