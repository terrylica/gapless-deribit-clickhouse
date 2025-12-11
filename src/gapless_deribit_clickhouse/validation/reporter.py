# ADR: 2025-12-11-e2e-validation-pipeline
"""
Formatted validation output with mode indicator for CLI display.

Generates structured reports showing infrastructure status, data quality
metrics, and clear indication of which ClickHouse instance is being used.

Usage:
    from gapless_deribit_clickhouse.validation.reporter import (
        print_validation_summary,
    )

    client = get_client(...)
    print_validation_summary(client, verbose=True)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clickhouse_connect.driver import Client

logger = logging.getLogger(__name__)

# ADR: 2025-12-11-e2e-validation-pipeline - Report formatting constants
REPORT_WIDTH = 60
MAX_GAPS_DISPLAYED = 5


def format_validation_report(
    infra_status: dict,
    quality_metrics: dict,
    mode_indicator: str,
    gaps: list[dict] | None = None,
) -> str:
    """Generate formatted validation report.

    ADR: 2025-12-11-e2e-validation-pipeline - Formatted CLI output

    Args:
        infra_status: Dict from validate_schema_version()
        quality_metrics: Dict from get_quality_metrics()
        mode_indicator: String from get_mode_indicator()
        gaps: Optional list from get_gap_analysis()

    Returns:
        Formatted report string for CLI output.
    """
    lines = []

    # Header with mode indicator
    lines.append("=" * REPORT_WIDTH)
    lines.append(f"E2E Validation Report {mode_indicator}")
    lines.append("=" * REPORT_WIDTH)

    # Infrastructure section
    lines.append("")
    lines.append("Infrastructure:")
    if infra_status.get("valid"):
        lines.append("  [OK] Schema v3.0.0 validated")
    else:
        lines.append("  [!!] Schema validation failed")
        for error in infra_status.get("errors", []):
            lines.append(f"       - {error}")

    if infra_status.get("table_exists"):
        lines.append("  [OK] Table exists")

    order_by = infra_status.get("order_by_columns", [])
    if order_by:
        lines.append(f"  [OK] ORDER BY: {', '.join(order_by)}")

    low_card = infra_status.get("low_cardinality_columns", [])
    if low_card:
        lines.append(f"  [OK] LowCardinality: {', '.join(low_card)}")

    # Data quality section
    lines.append("")
    lines.append("Data Quality:")
    total = quality_metrics.get("total_rows", 0)
    unique = quality_metrics.get("unique_trades", 0)
    dedup_rate = quality_metrics.get("dedup_rate", 0)

    lines.append(f"  Total rows: {total:,}")
    lines.append(f"  Unique trades: {unique:,} ({dedup_rate:.1%} deduped)")

    earliest = quality_metrics.get("earliest")
    latest = quality_metrics.get("latest")
    if earliest and latest:
        lines.append(f"  Date range: {earliest} to {latest}")

    date_span = quality_metrics.get("date_span_days", 0)
    lines.append(f"  Date span: {date_span} days")

    avg_per_hour = quality_metrics.get("avg_trades_per_hour", 0)
    lines.append(f"  Avg trades/hour: {avg_per_hour:.1f}")

    null_iv = quality_metrics.get("null_iv_count", 0)
    null_iv_rate = quality_metrics.get("null_iv_rate", 0)
    lines.append(f"  Null IV: {null_iv:,} ({null_iv_rate:.2%})")

    null_idx = quality_metrics.get("null_index_count", 0)
    null_idx_rate = quality_metrics.get("null_index_rate", 0)
    lines.append(f"  Null index: {null_idx:,} ({null_idx_rate:.2%})")

    # Gap analysis section (optional)
    if gaps is not None:
        lines.append("")
        lines.append("Gap Analysis:")
        if gaps:
            lines.append(f"  Gaps found: {len(gaps)}")
            for gap in gaps[:MAX_GAPS_DISPLAYED]:
                start = gap.get("gap_start", "?")
                end = gap.get("gap_end", "?")
                hours = gap.get("gap_hours", 0)
                lines.append(f"    {start} - {end} ({hours}h)")
            if len(gaps) > MAX_GAPS_DISPLAYED:
                lines.append(f"    ... and {len(gaps) - MAX_GAPS_DISPLAYED} more")
        else:
            lines.append("  No significant gaps found")

    lines.append("")
    lines.append("=" * REPORT_WIDTH)

    return "\n".join(lines)


def print_validation_summary(
    client: Client,
    verbose: bool = False,
    gap_threshold_hours: int = 4,
) -> bool:
    """Print validation summary to stdout.

    ADR: 2025-12-11-e2e-validation-pipeline - CLI summary output

    Args:
        client: ClickHouse client instance
        verbose: If True, include gap analysis
        gap_threshold_hours: Threshold for gap detection (default: 4)

    Returns:
        True if all validations pass, False otherwise.

    Raises:
        RuntimeError: If validation fails critically.
    """
    from gapless_deribit_clickhouse.validation.data_quality import (
        get_gap_analysis,
        get_quality_metrics,
    )
    from gapless_deribit_clickhouse.validation.infrastructure import (
        get_mode_indicator,
        validate_schema_version,
    )

    mode_indicator = get_mode_indicator()
    success = True

    # Validate infrastructure
    try:
        infra_status = validate_schema_version(client)
        if not infra_status.get("valid"):
            success = False
    except RuntimeError as e:
        infra_status = {
            "valid": False,
            "table_exists": False,
            "errors": [str(e)],
            "order_by_columns": [],
            "low_cardinality_columns": [],
        }
        success = False

    # Get quality metrics
    try:
        quality_metrics = get_quality_metrics(client)
    except RuntimeError as e:
        quality_metrics = {
            "total_rows": 0,
            "unique_trades": 0,
            "dedup_rate": 0,
            "earliest": None,
            "latest": None,
            "date_span_days": 0,
            "avg_trades_per_hour": 0,
            "null_iv_count": 0,
            "null_iv_rate": 0,
            "null_index_count": 0,
            "null_index_rate": 0,
        }
        logger.warning(f"Quality metrics failed: {e}")
        success = False

    # Get gaps if verbose
    gaps = None
    if verbose:
        try:
            gaps = get_gap_analysis(client, threshold_hours=gap_threshold_hours)
        except Exception as e:
            logger.warning(f"Gap analysis failed: {e}")
            gaps = []

    # Format and print report
    report = format_validation_report(
        infra_status=infra_status,
        quality_metrics=quality_metrics,
        mode_indicator=mode_indicator,
        gaps=gaps,
    )
    print(report)

    # Print summary line
    if success:
        print("Status: PASSED")
    else:
        print("Status: FAILED")

    return success


if __name__ == "__main__":
    # CLI entry point for mise task
    import os
    import sys

    from dotenv import load_dotenv

    load_dotenv()

    from clickhouse_connect import get_client

    from gapless_deribit_clickhouse.validation.infrastructure import (
        ensure_spot_dictionary,
        get_connection_info,
    )

    conn_info = get_connection_info()

    try:
        client = get_client(
            host=conn_info["host"],
            port=conn_info["port"],
            database=conn_info["database"],
            secure=conn_info["secure"],
            username=os.environ.get("CLICKHOUSE_USER_READONLY", "default"),
            password=os.environ.get("CLICKHOUSE_PASSWORD_READONLY", ""),
        )

        # Ensure dictionary exists
        ensure_spot_dictionary(client, auto_create=True)

        # Print full report with gaps
        success = print_validation_summary(client, verbose=True)

        sys.exit(0 if success else 1)

    except Exception as e:
        print(f"\nValidation failed: {e}")
        sys.exit(1)
