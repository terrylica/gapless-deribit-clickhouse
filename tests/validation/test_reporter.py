# ADR: 2025-12-11-e2e-validation-pipeline
"""Tests for validation reporter module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch


class TestFormatValidationReport:
    """Test format_validation_report() function."""

    def test_includes_mode_indicator_in_header(self):
        """Report should include mode indicator in header."""
        from gapless_deribit_clickhouse.validation.reporter import (
            format_validation_report,
        )

        infra_status = {"valid": True, "table_exists": True, "errors": []}
        quality_metrics = {
            "total_rows": 1000,
            "unique_trades": 1000,
            "dedup_rate": 1.0,
            "earliest": datetime(2024, 1, 1),
            "latest": datetime(2024, 12, 31),
            "date_span_days": 365,
            "avg_trades_per_hour": 1.0,
            "null_iv_count": 0,
            "null_iv_rate": 0.0,
            "null_index_count": 0,
            "null_index_rate": 0.0,
        }

        report = format_validation_report(
            infra_status=infra_status,
            quality_metrics=quality_metrics,
            mode_indicator="[CLOUD] test.clickhouse.cloud",
        )

        assert "[CLOUD]" in report
        assert "test.clickhouse.cloud" in report

    def test_shows_valid_schema_status(self):
        """Report should show OK for valid schema."""
        from gapless_deribit_clickhouse.validation.reporter import (
            format_validation_report,
        )

        infra_status = {
            "valid": True,
            "table_exists": True,
            "errors": [],
            "order_by_columns": ["timestamp"],
            "low_cardinality_columns": ["direction"],
        }
        quality_metrics = {
            "total_rows": 100,
            "unique_trades": 100,
            "dedup_rate": 1.0,
            "earliest": None,
            "latest": None,
            "date_span_days": 0,
            "avg_trades_per_hour": 0,
            "null_iv_count": 0,
            "null_iv_rate": 0.0,
            "null_index_count": 0,
            "null_index_rate": 0.0,
        }

        report = format_validation_report(
            infra_status=infra_status,
            quality_metrics=quality_metrics,
            mode_indicator="[LOCAL] localhost",
        )

        assert "[OK] Schema v3.0.0 validated" in report

    def test_shows_invalid_schema_errors(self):
        """Report should show errors for invalid schema."""
        from gapless_deribit_clickhouse.validation.reporter import (
            format_validation_report,
        )

        infra_status = {
            "valid": False,
            "table_exists": True,
            "errors": ["Missing LowCardinality columns: {'direction'}"],
            "order_by_columns": [],
            "low_cardinality_columns": [],
        }
        quality_metrics = {
            "total_rows": 100,
            "unique_trades": 100,
            "dedup_rate": 1.0,
            "earliest": None,
            "latest": None,
            "date_span_days": 0,
            "avg_trades_per_hour": 0,
            "null_iv_count": 0,
            "null_iv_rate": 0.0,
            "null_index_count": 0,
            "null_index_rate": 0.0,
        }

        report = format_validation_report(
            infra_status=infra_status,
            quality_metrics=quality_metrics,
            mode_indicator="[LOCAL] localhost",
        )

        assert "[!!] Schema validation failed" in report
        assert "LowCardinality" in report

    def test_shows_quality_metrics(self):
        """Report should display all quality metrics."""
        from gapless_deribit_clickhouse.validation.reporter import (
            format_validation_report,
        )

        infra_status = {"valid": True, "table_exists": True, "errors": []}
        quality_metrics = {
            "total_rows": 10000,
            "unique_trades": 9500,
            "dedup_rate": 0.95,
            "earliest": datetime(2024, 1, 1),
            "latest": datetime(2024, 6, 30),
            "date_span_days": 180,
            "avg_trades_per_hour": 2.3,
            "null_iv_count": 100,
            "null_iv_rate": 0.01,
            "null_index_count": 50,
            "null_index_rate": 0.005,
        }

        report = format_validation_report(
            infra_status=infra_status,
            quality_metrics=quality_metrics,
            mode_indicator="[LOCAL] localhost",
        )

        assert "10,000" in report  # Total rows formatted
        assert "9,500" in report  # Unique trades
        assert "95.0%" in report  # Dedup rate
        assert "180 days" in report  # Date span
        assert "2.3" in report  # Avg trades/hour

    def test_shows_gaps_when_provided(self):
        """Report should show gap analysis when gaps provided."""
        from gapless_deribit_clickhouse.validation.reporter import (
            format_validation_report,
        )

        infra_status = {"valid": True, "table_exists": True, "errors": []}
        quality_metrics = {
            "total_rows": 100,
            "unique_trades": 100,
            "dedup_rate": 1.0,
            "earliest": None,
            "latest": None,
            "date_span_days": 0,
            "avg_trades_per_hour": 0,
            "null_iv_count": 0,
            "null_iv_rate": 0.0,
            "null_index_count": 0,
            "null_index_rate": 0.0,
        }
        gaps = [
            {
                "gap_start": datetime(2024, 1, 1, 10, 0),
                "gap_end": datetime(2024, 1, 1, 18, 0),
                "gap_hours": 8,
            }
        ]

        report = format_validation_report(
            infra_status=infra_status,
            quality_metrics=quality_metrics,
            mode_indicator="[LOCAL] localhost",
            gaps=gaps,
        )

        assert "Gap Analysis" in report
        assert "Gaps found: 1" in report
        assert "8h" in report

    def test_shows_no_gaps_message(self):
        """Report should show 'no gaps' when gaps list is empty."""
        from gapless_deribit_clickhouse.validation.reporter import (
            format_validation_report,
        )

        infra_status = {"valid": True, "table_exists": True, "errors": []}
        quality_metrics = {
            "total_rows": 100,
            "unique_trades": 100,
            "dedup_rate": 1.0,
            "earliest": None,
            "latest": None,
            "date_span_days": 0,
            "avg_trades_per_hour": 0,
            "null_iv_count": 0,
            "null_iv_rate": 0.0,
            "null_index_count": 0,
            "null_index_rate": 0.0,
        }

        report = format_validation_report(
            infra_status=infra_status,
            quality_metrics=quality_metrics,
            mode_indicator="[LOCAL] localhost",
            gaps=[],
        )

        assert "No significant gaps found" in report


class TestPrintValidationSummary:
    """Test print_validation_summary() function."""

    def test_returns_true_on_success(self):
        """Should return True when all validations pass."""
        from gapless_deribit_clickhouse.validation.reporter import (
            print_validation_summary,
        )

        mock_client = MagicMock()

        # Patch at source modules where functions are defined
        with patch(
            "gapless_deribit_clickhouse.validation.infrastructure.validate_schema_version"
        ) as mock_validate:
            mock_validate.return_value = {
                "valid": True,
                "table_exists": True,
                "errors": [],
                "order_by_columns": ["timestamp"],
                "low_cardinality_columns": ["direction"],
            }

            with patch(
                "gapless_deribit_clickhouse.validation.data_quality.get_quality_metrics"
            ) as mock_metrics:
                mock_metrics.return_value = {
                    "total_rows": 100,
                    "unique_trades": 100,
                    "dedup_rate": 1.0,
                    "earliest": None,
                    "latest": None,
                    "date_span_days": 0,
                    "avg_trades_per_hour": 0,
                    "null_iv_count": 0,
                    "null_iv_rate": 0.0,
                    "null_index_count": 0,
                    "null_index_rate": 0.0,
                }

                with patch(
                    "gapless_deribit_clickhouse.validation.infrastructure.get_mode_indicator"
                ) as mock_mode:
                    mock_mode.return_value = "[LOCAL] localhost"

                    result = print_validation_summary(mock_client, verbose=False)

        assert result is True

    def test_returns_false_on_schema_failure(self):
        """Should return False when schema validation fails."""
        from gapless_deribit_clickhouse.validation.reporter import (
            print_validation_summary,
        )

        mock_client = MagicMock()

        with patch(
            "gapless_deribit_clickhouse.validation.infrastructure.validate_schema_version"
        ) as mock_validate:
            mock_validate.return_value = {
                "valid": False,
                "table_exists": True,
                "errors": ["timestamp not in ORDER BY"],
                "order_by_columns": [],
                "low_cardinality_columns": [],
            }

            with patch(
                "gapless_deribit_clickhouse.validation.data_quality.get_quality_metrics"
            ) as mock_metrics:
                mock_metrics.return_value = {
                    "total_rows": 100,
                    "unique_trades": 100,
                    "dedup_rate": 1.0,
                    "earliest": None,
                    "latest": None,
                    "date_span_days": 0,
                    "avg_trades_per_hour": 0,
                    "null_iv_count": 0,
                    "null_iv_rate": 0.0,
                    "null_index_count": 0,
                    "null_index_rate": 0.0,
                }

                with patch(
                    "gapless_deribit_clickhouse.validation.infrastructure.get_mode_indicator"
                ) as mock_mode:
                    mock_mode.return_value = "[LOCAL] localhost"

                    result = print_validation_summary(mock_client, verbose=False)

        assert result is False

    def test_includes_gaps_when_verbose(self):
        """Should include gap analysis when verbose=True."""
        from gapless_deribit_clickhouse.validation.reporter import (
            print_validation_summary,
        )

        mock_client = MagicMock()

        with patch(
            "gapless_deribit_clickhouse.validation.infrastructure.validate_schema_version"
        ) as mock_validate:
            mock_validate.return_value = {
                "valid": True,
                "table_exists": True,
                "errors": [],
            }

            with patch(
                "gapless_deribit_clickhouse.validation.data_quality.get_quality_metrics"
            ) as mock_metrics:
                mock_metrics.return_value = {
                    "total_rows": 100,
                    "unique_trades": 100,
                    "dedup_rate": 1.0,
                    "earliest": None,
                    "latest": None,
                    "date_span_days": 0,
                    "avg_trades_per_hour": 0,
                    "null_iv_count": 0,
                    "null_iv_rate": 0.0,
                    "null_index_count": 0,
                    "null_index_rate": 0.0,
                }

                with patch(
                    "gapless_deribit_clickhouse.validation.infrastructure.get_mode_indicator"
                ) as mock_mode:
                    mock_mode.return_value = "[LOCAL] localhost"

                    with patch(
                        "gapless_deribit_clickhouse.validation.data_quality.get_gap_analysis"
                    ) as mock_gaps:
                        mock_gaps.return_value = []

                        print_validation_summary(mock_client, verbose=True)

                        # Verify gap analysis was called
                        mock_gaps.assert_called_once()
