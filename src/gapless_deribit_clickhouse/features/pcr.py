# ADR: 2025-12-10-deribit-options-alpha-features
"""
Put-Call Ratio (PCR) calculation by expiry tenor.

PCR is a lagging sentiment indicator (not predictive for direction).
Segmented by DTE bucket to capture term structure of sentiment.

Research finding: PCR is useful as a confirmation signal but should
NOT be used as a standalone directional predictor.
"""

from __future__ import annotations

import pandas as pd

# Default DTE buckets for tenor segmentation
DEFAULT_DTE_BUCKETS: list[tuple[int, int]] = [
    (0, 7),      # Weekly
    (8, 14),     # Bi-weekly
    (15, 30),    # Monthly
    (31, 60),    # Bi-monthly
    (61, 90),    # Quarterly
]


def pcr_by_tenor(
    df: pd.DataFrame,
    dte_buckets: list[tuple[int, int]] | None = None,
    timestamp_col: str = "timestamp",
    option_type_col: str = "option_type",
    amount_col: str = "amount",
    dte_col: str = "dte",
    freq: str = "15min",
    method: str = "volume",
) -> pd.DataFrame:
    """
    Calculate Put-Call Ratio by DTE bucket.

    PCR = Put Volume / Call Volume (or count)

    >1.0: More puts than calls (bearish sentiment)
    <1.0: More calls than puts (bullish sentiment)
    =1.0: Neutral

    Note: PCR is a LAGGING indicator. Use as sentiment gauge,
    not as a predictive signal.

    Args:
        df: DataFrame with trade data
        dte_buckets: List of (min_dte, max_dte) tuples
                     Default: [(0,7), (8,14), (15,30), (31,60), (61,90)]
        timestamp_col: Timestamp column name
        option_type_col: Option type column ("C" or "P")
        amount_col: Volume/amount column
        dte_col: DTE column name
        freq: Aggregation frequency (default: 15min)
        method: "volume" (sum of amount) or "count" (trade count)

    Returns:
        DataFrame with PCR per bucket per timestamp

    Raises:
        ValueError: If required columns missing
    """
    if df.empty:
        raise ValueError("Cannot compute PCR on empty DataFrame")

    if dte_buckets is None:
        dte_buckets = DEFAULT_DTE_BUCKETS

    df = df.copy()

    # Compute DTE if not present
    if dte_col not in df.columns:
        if "expiry" not in df.columns or timestamp_col not in df.columns:
            raise ValueError(f"Missing {dte_col} column and cannot derive")
        df[dte_col] = (
            pd.to_datetime(df["expiry"]) - pd.to_datetime(df[timestamp_col]).dt.normalize()
        ).dt.days

    # Validate required columns
    required = {timestamp_col, option_type_col, amount_col, dte_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Ensure datetime
    if not pd.api.types.is_datetime64_any_dtype(df[timestamp_col]):
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])

    df = df.set_index(timestamp_col)

    results = {}

    for min_dte, max_dte in dte_buckets:
        bucket_name = f"pcr_{min_dte}_{max_dte}d"
        bucket_df = df[(df[dte_col] >= min_dte) & (df[dte_col] <= max_dte)]

        if bucket_df.empty:
            continue

        # Split by option type
        puts = bucket_df[bucket_df[option_type_col] == "P"]
        calls = bucket_df[bucket_df[option_type_col] == "C"]

        if method == "volume":
            put_vol = puts[amount_col].resample(freq).sum()
            call_vol = calls[amount_col].resample(freq).sum()
        else:  # count
            put_vol = puts[amount_col].resample(freq).count()
            call_vol = calls[amount_col].resample(freq).count()

        # Align and compute ratio
        aligned = pd.DataFrame({"puts": put_vol, "calls": call_vol}).fillna(0)

        # Avoid division by zero
        pcr = aligned["puts"] / aligned["calls"].replace(0, float("nan"))
        results[bucket_name] = pcr

    if not results:
        raise ValueError("No data available for any DTE bucket")

    result_df = pd.DataFrame(results)
    return result_df


def pcr_aggregate(
    df: pd.DataFrame,
    timestamp_col: str = "timestamp",
    option_type_col: str = "option_type",
    amount_col: str = "amount",
    freq: str = "15min",
    method: str = "volume",
) -> pd.Series:
    """
    Calculate aggregate PCR across all expiries.

    Simpler version without DTE segmentation.

    Args:
        df: DataFrame with trade data
        timestamp_col: Timestamp column
        option_type_col: Option type column
        amount_col: Volume column
        freq: Aggregation frequency
        method: "volume" or "count"

    Returns:
        Series of PCR values
    """
    if df.empty:
        raise ValueError("Cannot compute PCR on empty DataFrame")

    required = {timestamp_col, option_type_col, amount_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df.copy()

    if not pd.api.types.is_datetime64_any_dtype(df[timestamp_col]):
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])

    df = df.set_index(timestamp_col)

    puts = df[df[option_type_col] == "P"]
    calls = df[df[option_type_col] == "C"]

    if method == "volume":
        put_vol = puts[amount_col].resample(freq).sum()
        call_vol = calls[amount_col].resample(freq).sum()
    else:
        put_vol = puts[amount_col].resample(freq).count()
        call_vol = calls[amount_col].resample(freq).count()

    aligned = pd.DataFrame({"puts": put_vol, "calls": call_vol}).fillna(0)
    pcr = aligned["puts"] / aligned["calls"].replace(0, float("nan"))
    pcr.name = "pcr"

    return pcr
