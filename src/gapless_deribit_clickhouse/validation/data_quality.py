# ADR: 2025-12-11-e2e-validation-pipeline
"""
ClickHouse-native data quality metrics for options trades pipeline.

All metrics are computed server-side using ClickHouse SQL to minimize
data transfer and leverage ClickHouse's efficient aggregation engine.

Usage:
    from gapless_deribit_clickhouse.validation.data_quality import (
        get_quality_metrics,
        get_gap_analysis,
    )

    client = get_client(...)
    metrics = get_quality_metrics(client)
    gaps = get_gap_analysis(client, threshold_hours=4)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clickhouse_connect.driver import Client

logger = logging.getLogger(__name__)

# ADR: 2025-12-11-e2e-validation-pipeline - Server-side quality metrics
QUALITY_METRICS_QUERY = """
SELECT
    count() AS total_rows,
    uniqExact(trade_id) AS unique_trades,
    min(timestamp) AS earliest,
    max(timestamp) AS latest,
    dateDiff('day', min(timestamp), max(timestamp)) AS date_span_days,
    countIf(iv IS NULL OR iv = 0) AS null_iv_count,
    countIf(index_price IS NULL OR index_price = 0) AS null_index_count,
    if(
        dateDiff('hour', min(timestamp), max(timestamp)) > 0,
        toFloat64(count()) / dateDiff('hour', min(timestamp), max(timestamp)),
        toFloat64(count())
    ) AS avg_trades_per_hour
FROM {database}.{table}
"""

# Gap analysis query - finds gaps larger than threshold
GAP_ANALYSIS_QUERY = """
WITH sorted AS (
    SELECT
        timestamp,
        leadInFrame(timestamp) OVER (
            ORDER BY timestamp ROWS BETWEEN CURRENT ROW AND 1 FOLLOWING
        ) AS next_ts
    FROM {database}.{table}
)
SELECT
    timestamp AS gap_start,
    next_ts AS gap_end,
    dateDiff('hour', timestamp, next_ts) AS gap_hours
FROM sorted
WHERE next_ts IS NOT NULL
  AND dateDiff('hour', timestamp, next_ts) > {threshold}
ORDER BY gap_hours DESC
LIMIT 100
"""

# Coverage statistics by underlying
COVERAGE_STATS_QUERY = """
SELECT
    underlying,
    count() AS trade_count,
    uniqExact(instrument_name) AS unique_instruments,
    min(timestamp) AS earliest,
    max(timestamp) AS latest,
    countIf(iv IS NULL OR iv = 0) / count() AS null_iv_rate,
    countIf(index_price IS NULL OR index_price = 0) / count() AS null_index_rate
FROM {database}.{table}
WHERE underlying = '{underlying}'
GROUP BY underlying
"""


def get_quality_metrics(
    client: Client,
    database: str = "deribit",
    table: str = "options_trades",
) -> dict:
    """Get comprehensive data quality metrics computed server-side.

    ADR: 2025-12-11-e2e-validation-pipeline - ClickHouse-native aggregation

    Args:
        client: ClickHouse client instance
        database: Database name (default: deribit)
        table: Table name (default: options_trades)

    Returns:
        Dict with quality metrics:
        - total_rows: int
        - unique_trades: int
        - earliest: datetime
        - latest: datetime
        - date_span_days: int
        - null_iv_count: int
        - null_index_count: int
        - avg_trades_per_hour: float
        - dedup_rate: float (unique/total)

    Raises:
        RuntimeError: If query fails or table is empty.
    """
    query = QUALITY_METRICS_QUERY.format(database=database, table=table)
    result = client.query(query)

    if not result.result_rows:
        raise RuntimeError(f"No data in {database}.{table}")

    row = result.result_rows[0]
    columns = result.column_names

    metrics = dict(zip(columns, row))

    # Add derived metrics
    total = metrics.get("total_rows", 0)
    unique = metrics.get("unique_trades", 0)
    metrics["dedup_rate"] = unique / total if total > 0 else 0.0

    # Calculate null rates
    metrics["null_iv_rate"] = metrics["null_iv_count"] / total if total > 0 else 0.0
    metrics["null_index_rate"] = (
        metrics["null_index_count"] / total if total > 0 else 0.0
    )

    logger.debug(f"Quality metrics: {metrics}")
    return metrics


def get_gap_analysis(
    client: Client,
    threshold_hours: int = 4,
    database: str = "deribit",
    table: str = "options_trades",
) -> list[dict]:
    """Find gaps in data larger than threshold.

    ADR: 2025-12-11-e2e-validation-pipeline - Gap detection

    Args:
        client: ClickHouse client instance
        threshold_hours: Minimum gap size to report (default: 4 hours)
        database: Database name (default: deribit)
        table: Table name (default: options_trades)

    Returns:
        List of dicts with gap information:
        - gap_start: datetime
        - gap_end: datetime
        - gap_hours: int
    """
    query = GAP_ANALYSIS_QUERY.format(
        database=database,
        table=table,
        threshold=threshold_hours,
    )
    result = client.query(query)

    gaps = []
    for row in result.result_rows:
        gaps.append(
            {
                "gap_start": row[0],
                "gap_end": row[1],
                "gap_hours": row[2],
            }
        )

    logger.debug(f"Found {len(gaps)} gaps > {threshold_hours}h")
    return gaps


def get_coverage_stats(
    client: Client,
    underlying: str = "BTC",
    database: str = "deribit",
    table: str = "options_trades",
) -> dict:
    """Get coverage statistics for a specific underlying.

    Args:
        client: ClickHouse client instance
        underlying: Underlying asset (default: BTC)
        database: Database name (default: deribit)
        table: Table name (default: options_trades)

    Returns:
        Dict with coverage statistics:
        - underlying: str
        - trade_count: int
        - unique_instruments: int
        - earliest: datetime
        - latest: datetime
        - null_iv_rate: float
        - null_index_rate: float
    """
    query = COVERAGE_STATS_QUERY.format(
        database=database,
        table=table,
        underlying=underlying,
    )
    result = client.query(query)

    if not result.result_rows:
        return {
            "underlying": underlying,
            "trade_count": 0,
            "unique_instruments": 0,
            "earliest": None,
            "latest": None,
            "null_iv_rate": 0.0,
            "null_index_rate": 0.0,
        }

    row = result.result_rows[0]
    columns = result.column_names
    return dict(zip(columns, row))


if __name__ == "__main__":
    # CLI entry point for mise task
    import os
    import sys

    from dotenv import load_dotenv

    load_dotenv()

    from clickhouse_connect import get_client

    from gapless_deribit_clickhouse.validation.infrastructure import get_connection_info

    conn_info = get_connection_info()

    # Mode-aware credentials: local uses default/empty, cloud uses READONLY env vars
    if conn_info["mode"] == "local":
        username = "default"
        password = ""
    else:
        username = os.environ.get("CLICKHOUSE_USER_READONLY", "default")
        password = os.environ.get("CLICKHOUSE_PASSWORD_READONLY", "")

    try:
        client = get_client(
            host=conn_info["host"],
            port=conn_info["port"],
            database=conn_info["database"],
            secure=conn_info["secure"],
            username=username,
            password=password,
        )

        print("Data Quality Metrics")
        print("=" * 50)

        metrics = get_quality_metrics(client)
        print(f"  Total rows: {metrics['total_rows']:,}")
        print(f"  Unique trades: {metrics['unique_trades']:,}")
        print(f"  Dedup rate: {metrics['dedup_rate']:.1%}")
        print(f"  Date range: {metrics['earliest']} to {metrics['latest']}")
        print(f"  Date span: {metrics['date_span_days']} days")
        print(f"  Avg trades/hour: {metrics['avg_trades_per_hour']:.1f}")
        print(f"  Null IV: {metrics['null_iv_count']:,} ({metrics['null_iv_rate']:.2%})")
        print(
            f"  Null index: {metrics['null_index_count']:,} ({metrics['null_index_rate']:.2%})"
        )

        print("\nGap Analysis (>4h)")
        print("-" * 50)
        gaps = get_gap_analysis(client, threshold_hours=4)
        if gaps:
            for gap in gaps[:10]:  # Show top 10
                print(f"  {gap['gap_start']} - {gap['gap_end']} ({gap['gap_hours']}h)")
        else:
            print("  No gaps > 4h found")

        print("\n✓ Data quality check complete")

    except Exception as e:
        print(f"\n✗ Data quality check failed: {e}")
        sys.exit(1)
