# ADR: 2025-12-10-deribit-options-alpha-features
"""
DTE (Days-to-Expiry) Bucket Aggregations.

Aggregates trade metrics by expiry tenor buckets. Useful for analyzing
how trading activity and IV vary across the term structure.
"""

from __future__ import annotations

import pandas as pd

# Default DTE bucket definitions
DEFAULT_DTE_BUCKETS: list[tuple[int, int]] = [
    (0, 7),      # Weekly / front-month
    (8, 14),     # Bi-weekly
    (15, 30),    # Monthly
    (31, 60),    # Bi-monthly
    (61, 90),    # Quarterly
    (91, 999),   # LEAPS (long-term)
]

# Default metrics to aggregate
DEFAULT_METRICS: list[str] = ["iv", "amount", "price"]


def dte_bucket_agg(
    df: pd.DataFrame,
    buckets: list[tuple[int, int]] | None = None,
    metrics: list[str] | None = None,
    timestamp_col: str = "timestamp",
    dte_col: str = "dte",
    freq: str = "15min",
) -> pd.DataFrame:
    """
    Aggregate trade metrics by DTE bucket.

    Groups trades into tenor buckets and computes aggregated statistics
    for each bucket at the specified frequency.

    Args:
        df: DataFrame with trade data
        buckets: DTE bucket definitions as (min_dte, max_dte) tuples
                 Default: [(0,7), (8,14), (15,30), (31,60), (61,90), (91,999)]
        metrics: Columns to aggregate (default: iv, amount, price)
        timestamp_col: Timestamp column name
        dte_col: DTE column name (computed from expiry if missing)
        freq: Aggregation frequency (default: 15min)

    Returns:
        DataFrame with multi-level columns: (bucket, metric_agg)

    Raises:
        ValueError: If required columns missing or no data
    """
    if df.empty:
        raise ValueError("Cannot aggregate empty DataFrame")

    if buckets is None:
        buckets = DEFAULT_DTE_BUCKETS

    if metrics is None:
        metrics = DEFAULT_METRICS

    df = df.copy()

    # Compute DTE if not present
    if dte_col not in df.columns:
        if "expiry" not in df.columns or timestamp_col not in df.columns:
            raise ValueError(f"Missing {dte_col} column and cannot derive")
        df[dte_col] = (
            pd.to_datetime(df["expiry"]) - pd.to_datetime(df[timestamp_col]).dt.normalize()
        ).dt.days

    # Validate columns
    required = {timestamp_col, dte_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Filter metrics to those present in df
    available_metrics = [m for m in metrics if m in df.columns]
    if not available_metrics:
        raise ValueError(f"None of the requested metrics found in DataFrame: {metrics}")

    # Ensure datetime
    if not pd.api.types.is_datetime64_any_dtype(df[timestamp_col]):
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])

    df = df.set_index(timestamp_col)

    all_results = {}

    for min_dte, max_dte in buckets:
        bucket_name = f"dte_{min_dte}_{max_dte}"
        bucket_df = df[(df[dte_col] >= min_dte) & (df[dte_col] <= max_dte)]

        if bucket_df.empty:
            continue

        # Aggregate each metric
        for metric in available_metrics:
            if metric not in bucket_df.columns:
                continue

            metric_data = bucket_df[metric].dropna()
            if metric_data.empty:
                continue

            resampled = metric_data.resample(freq)

            # Different aggregations based on metric type
            if metric == "iv":
                # For IV: mean and std
                all_results[f"{bucket_name}_iv_mean"] = resampled.mean()
                all_results[f"{bucket_name}_iv_std"] = resampled.std()
            elif metric == "amount":
                # For volume: sum and count
                all_results[f"{bucket_name}_volume"] = resampled.sum()
                all_results[f"{bucket_name}_trade_count"] = resampled.count()
            elif metric == "price":
                # For price: VWAP-style mean
                all_results[f"{bucket_name}_price_mean"] = resampled.mean()

    if not all_results:
        raise ValueError("No data available for any bucket/metric combination")

    result_df = pd.DataFrame(all_results)
    return result_df


def dte_distribution(
    df: pd.DataFrame,
    buckets: list[tuple[int, int]] | None = None,
    timestamp_col: str = "timestamp",
    dte_col: str = "dte",
    amount_col: str = "amount",
    freq: str = "15min",
) -> pd.DataFrame:
    """
    Calculate volume distribution across DTE buckets.

    Shows what percentage of total volume is in each tenor bucket.

    Args:
        df: DataFrame with trade data
        buckets: DTE bucket definitions
        timestamp_col: Timestamp column
        dte_col: DTE column
        amount_col: Volume column
        freq: Aggregation frequency

    Returns:
        DataFrame with percentage distribution per bucket
    """
    if df.empty:
        raise ValueError("Cannot compute distribution on empty DataFrame")

    if buckets is None:
        buckets = DEFAULT_DTE_BUCKETS

    df = df.copy()

    # Compute DTE if needed
    if dte_col not in df.columns:
        if "expiry" not in df.columns or timestamp_col not in df.columns:
            raise ValueError(f"Missing {dte_col} column")
        df[dte_col] = (
            pd.to_datetime(df["expiry"]) - pd.to_datetime(df[timestamp_col]).dt.normalize()
        ).dt.days

    if not pd.api.types.is_datetime64_any_dtype(df[timestamp_col]):
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])

    df = df.set_index(timestamp_col)

    bucket_volumes = {}

    for min_dte, max_dte in buckets:
        bucket_name = f"dte_{min_dte}_{max_dte}_pct"
        bucket_df = df[(df[dte_col] >= min_dte) & (df[dte_col] <= max_dte)]

        if not bucket_df.empty and amount_col in bucket_df.columns:
            bucket_volumes[bucket_name] = bucket_df[amount_col].resample(freq).sum()

    if not bucket_volumes:
        raise ValueError("No volume data for any bucket")

    result_df = pd.DataFrame(bucket_volumes).fillna(0)

    # Convert to percentages
    row_totals = result_df.sum(axis=1)
    result_df = result_df.div(row_totals, axis=0) * 100

    # Handle division by zero
    result_df = result_df.replace([float("inf"), float("-inf")], float("nan"))

    return result_df
