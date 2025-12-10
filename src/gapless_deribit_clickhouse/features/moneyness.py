# ADR: 2025-12-10-deribit-options-alpha-features
"""
Moneyness-based feature calculations using ClickHouse native aggregations.

Provides moneyness bucket aggregations for volatility smile/skew analysis:
- Deep OTM Put (moneyness < 0.90)
- OTM Put (0.90 <= moneyness < 0.95)
- ATM (0.95 <= moneyness < 1.05)
- OTM Call (1.05 <= moneyness < 1.10)
- Deep OTM Call (moneyness >= 1.10)

Performance Optimization:
- CASE WHEN bucket assignment computed server-side
- avgIf(), sumIf() for conditional aggregation in single pass
- Wide pivot format ready for ML features

Key Metrics:
- put_call_skew: OTM put IV - OTM call IV (fear gauge)
- smile_curvature: Wing IV average - ATM IV (volatility smile shape)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from clickhouse_connect.driver import Client

from gapless_deribit_clickhouse.features.config import DEFAULT_CONFIG, FeatureConfig

# Moneyness bucket aggregation query (long format)
MONEYNESS_AGGREGATION_QUERY = """
-- Moneyness bucket aggregations (long format)
WITH enriched AS (
    {inner_query}
),
bucketed AS (
    SELECT
        toStartOfFifteenMinutes(timestamp) AS ts,
        CASE
            WHEN moneyness < {t0} THEN 'deep_otm_put'
            WHEN moneyness >= {t0} AND moneyness < {t1} THEN 'otm_put'
            WHEN moneyness >= {t1} AND moneyness < {t2} THEN 'atm'
            WHEN moneyness >= {t2} AND moneyness < {t3} THEN 'otm_call'
            ELSE 'deep_otm_call'
        END AS moneyness_bucket,
        iv,
        amount,
        option_type
    FROM enriched
    WHERE moneyness > 0  -- Filter invalid moneyness
      AND iv > 0         -- Filter invalid IV
)
SELECT
    ts,
    moneyness_bucket,
    avg(iv) AS iv_mean,
    stddevPop(iv) AS iv_std,
    count(*) AS trade_count,
    sum(amount) AS total_volume,
    countIf(option_type = 'C') AS call_count,
    countIf(option_type = 'P') AS put_count
FROM bucketed
GROUP BY ts, moneyness_bucket
ORDER BY ts, moneyness_bucket
"""

# Pivoted moneyness aggregation (wide format for ML)
MONEYNESS_PIVOT_QUERY = """
-- Moneyness bucket aggregations (wide format for ML features)
WITH enriched AS (
    {inner_query}
),
bucketed AS (
    SELECT
        toStartOfFifteenMinutes(timestamp) AS ts,
        CASE
            WHEN moneyness < {t0} THEN 'deep_otm_put'
            WHEN moneyness >= {t0} AND moneyness < {t1} THEN 'otm_put'
            WHEN moneyness >= {t1} AND moneyness < {t2} THEN 'atm'
            WHEN moneyness >= {t2} AND moneyness < {t3} THEN 'otm_call'
            ELSE 'deep_otm_call'
        END AS bucket,
        iv,
        amount
    FROM enriched
    WHERE moneyness > 0
      AND iv > 0
)
SELECT
    ts,
    -- ATM bucket (primary reference)
    avgIf(iv, bucket = 'atm') AS atm_iv_mean,
    stddevPopIf(iv, bucket = 'atm') AS atm_iv_std,
    countIf(bucket = 'atm') AS atm_count,
    sumIf(amount, bucket = 'atm') AS atm_volume,

    -- OTM Put
    avgIf(iv, bucket = 'otm_put') AS otm_put_iv_mean,
    stddevPopIf(iv, bucket = 'otm_put') AS otm_put_iv_std,
    countIf(bucket = 'otm_put') AS otm_put_count,
    sumIf(amount, bucket = 'otm_put') AS otm_put_volume,

    -- OTM Call
    avgIf(iv, bucket = 'otm_call') AS otm_call_iv_mean,
    stddevPopIf(iv, bucket = 'otm_call') AS otm_call_iv_std,
    countIf(bucket = 'otm_call') AS otm_call_count,
    sumIf(amount, bucket = 'otm_call') AS otm_call_volume,

    -- Deep OTM (wings)
    avgIf(iv, bucket = 'deep_otm_put') AS deep_otm_put_iv_mean,
    countIf(bucket = 'deep_otm_put') AS deep_otm_put_count,
    avgIf(iv, bucket = 'deep_otm_call') AS deep_otm_call_iv_mean,
    countIf(bucket = 'deep_otm_call') AS deep_otm_call_count,

    -- Derived features (computed server-side)
    -- Put-call skew: OTM put IV - OTM call IV (fear gauge)
    avgIf(iv, bucket = 'otm_put') - avgIf(iv, bucket = 'otm_call') AS put_call_skew,

    -- Smile curvature: average wing IV - ATM IV
    (avgIf(iv, bucket = 'otm_put') + avgIf(iv, bucket = 'otm_call')) / 2
        - avgIf(iv, bucket = 'atm') AS smile_curvature,

    -- Wing ratio: deep OTM put IV / deep OTM call IV
    avgIf(iv, bucket = 'deep_otm_put') / nullIf(avgIf(iv, bucket = 'deep_otm_call'), 0)
        AS wing_ratio

FROM bucketed
GROUP BY ts
HAVING atm_count > 0  -- Ensure we have ATM data for reference
ORDER BY ts
"""


def build_moneyness_aggregation_query(
    inner_query: str,
    pivot: bool = True,
    config: FeatureConfig = DEFAULT_CONFIG,
) -> str:
    """
    Build ClickHouse query for moneyness bucket aggregations.

    Args:
        inner_query: Query with spot_price and moneyness columns
                    (typically from spot_provider.build_spot_enriched_query)
        pivot: If True, return wide format (one column per bucket).
               If False, return long format (bucket as a column).
        config: FeatureConfig for moneyness thresholds

    Returns:
        SQL query for 15-min moneyness aggregations

    Example:
        >>> from gapless_deribit_clickhouse.features.spot_provider import (
        ...     build_spot_enriched_query
        ... )
        >>> base = build_spot_enriched_query(start="2024-01-01", end="2024-03-01")
        >>> query = build_moneyness_aggregation_query(base, pivot=True)
    """
    thresholds = config.moneyness_thresholds

    template = MONEYNESS_PIVOT_QUERY if pivot else MONEYNESS_AGGREGATION_QUERY
    return template.format(
        inner_query=inner_query,
        t0=thresholds[0],  # 0.90 default
        t1=thresholds[1],  # 0.95 default
        t2=thresholds[2],  # 1.05 default
        t3=thresholds[3],  # 1.10 default
    )


def aggregate_by_moneyness(
    client: Client,
    inner_query: str,
    pivot: bool = True,
    config: FeatureConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """
    Execute moneyness aggregation query and return DataFrame.

    Aggregates options data by moneyness bucket per 15-minute period.
    Includes derived features like put-call skew and smile curvature.

    Args:
        client: ClickHouse client instance
        inner_query: Query with moneyness column (from spot_provider)
        pivot: If True, wide format. If False, long format.
        config: FeatureConfig for thresholds

    Returns:
        DataFrame with moneyness bucket aggregations

    Example:
        >>> from clickhouse_connect import get_client
        >>> from gapless_deribit_clickhouse.features.spot_provider import (
        ...     build_spot_enriched_query
        ... )
        >>> client = get_client(host='localhost', port=8123)
        >>> base = build_spot_enriched_query(
        ...     start="2024-01-01",
        ...     end="2024-03-01",
        ...     underlying="BTC",
        ... )
        >>> df = aggregate_by_moneyness(client, base, pivot=True)
        >>> print(df[["ts", "atm_iv_mean", "put_call_skew"]].head())
    """
    import pandas as pd

    query = build_moneyness_aggregation_query(
        inner_query=inner_query,
        pivot=pivot,
        config=config,
    )

    result = client.query(query)

    df = pd.DataFrame(
        result.result_rows,
        columns=result.column_names,
    )

    # Set timestamp as index for time series operations
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.set_index("ts")

    return df


def compute_moneyness_bucket(
    moneyness: float,
    config: FeatureConfig = DEFAULT_CONFIG,
) -> str:
    """
    Compute moneyness bucket label for a single value.

    Useful for Python-side bucketing when ClickHouse is not available.

    Args:
        moneyness: Moneyness value (strike / spot)
        config: FeatureConfig for thresholds

    Returns:
        Bucket label string

    Example:
        >>> compute_moneyness_bucket(0.92)
        'otm_put'
        >>> compute_moneyness_bucket(1.0)
        'atm'
    """
    t = config.moneyness_thresholds

    if moneyness < t[0]:
        return "deep_otm_put"
    elif moneyness < t[1]:
        return "otm_put"
    elif moneyness < t[2]:
        return "atm"
    elif moneyness < t[3]:
        return "otm_call"
    else:
        return "deep_otm_call"


def compute_smile_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute volatility smile metrics from wide-format moneyness DataFrame.

    This is a Python-side helper for when you already have the aggregated
    data but need additional derived metrics.

    Args:
        df: DataFrame from aggregate_by_moneyness(pivot=True)

    Returns:
        DataFrame with additional smile metrics added:
        - smile_slope_put: Slope from ATM to OTM put
        - smile_slope_call: Slope from ATM to OTM call
        - smile_asymmetry: Put slope - Call slope

    Example:
        >>> df = aggregate_by_moneyness(client, query, pivot=True)
        >>> df = compute_smile_metrics(df)
    """
    df = df.copy()

    # Smile slopes (IV change per 5% moneyness move)
    if "otm_put_iv_mean" in df.columns and "atm_iv_mean" in df.columns:
        df["smile_slope_put"] = (df["otm_put_iv_mean"] - df["atm_iv_mean"]) / 0.05

    if "otm_call_iv_mean" in df.columns and "atm_iv_mean" in df.columns:
        df["smile_slope_call"] = (df["otm_call_iv_mean"] - df["atm_iv_mean"]) / 0.05

    # Smile asymmetry
    if "smile_slope_put" in df.columns and "smile_slope_call" in df.columns:
        df["smile_asymmetry"] = df["smile_slope_put"] - df["smile_slope_call"]

    return df
