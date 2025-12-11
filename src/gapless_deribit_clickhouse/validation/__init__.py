# ADR: 2025-12-11-e2e-validation-pipeline
"""
Validation module for gapless-deribit-clickhouse pipeline.

Provides infrastructure validation, data quality metrics, and CLI reporting
with ClickHouse mode indication (local/cloud).

Usage:
    from gapless_deribit_clickhouse.validation import (
        ensure_spot_dictionary,
        get_quality_metrics,
        print_validation_summary,
    )
"""

from gapless_deribit_clickhouse.validation.data_quality import (
    get_coverage_stats,
    get_gap_analysis,
    get_quality_metrics,
)
from gapless_deribit_clickhouse.validation.infrastructure import (
    ensure_spot_dictionary,
    get_connection_info,
    get_mode_indicator,
    validate_schema_version,
)
from gapless_deribit_clickhouse.validation.reporter import (
    format_validation_report,
    print_validation_summary,
)

__all__ = [
    # infrastructure
    "ensure_spot_dictionary",
    "validate_schema_version",
    "get_mode_indicator",
    "get_connection_info",
    # data_quality
    "get_quality_metrics",
    "get_gap_analysis",
    "get_coverage_stats",
    # reporter
    "format_validation_report",
    "print_validation_summary",
]
