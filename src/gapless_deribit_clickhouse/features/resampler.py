# ADR: 2025-12-10-deribit-options-alpha-features
"""
IV resampling for regular time series.

Converts irregular trade-level IV data to fixed-interval time series
required by GARCH models. Default frequency is 15-minute, which works
across all historical periods (2018-2024: 19-327 trades/hour).
"""

from __future__ import annotations

import pandas as pd

# Default resample frequency - works for 2018-2024 trade density
DEFAULT_RESAMPLE_FREQ = "15min"

# Default aggregation for IV OHLC bars
DEFAULT_IV_AGGREGATIONS: dict[str, str] = {
    "iv": "ohlc",  # Open, High, Low, Close
    "amount": "sum",  # Total volume
    "price": "mean",  # VWAP approximation
}


def resample_iv(
    df: pd.DataFrame,
    freq: str = DEFAULT_RESAMPLE_FREQ,
    iv_col: str = "iv",
    timestamp_col: str = "timestamp",
    include_volume: bool = True,
) -> pd.DataFrame:
    """
    Resample trade-level IV to regular time series.

    Converts irregular trade timestamps to fixed-interval OHLC bars
    suitable for GARCH modeling and other time series analysis.

    Args:
        df: DataFrame with trade data (must have timestamp and iv columns)
        freq: Resample frequency (default: "15min")
        iv_col: Name of IV column
        timestamp_col: Name of timestamp column
        include_volume: If True, include volume (amount) sum

    Returns:
        DataFrame with regular timestamps and OHLC IV values

    Raises:
        ValueError: If required columns are missing or df is empty

    Example:
        >>> df = pd.DataFrame({
        ...     "timestamp": pd.date_range("2024-01-01", periods=100, freq="1min"),
        ...     "iv": np.random.uniform(0.5, 1.0, 100),
        ...     "amount": np.random.uniform(1, 10, 100),
        ... })
        >>> resampled = resample_iv(df)
        >>> resampled.columns
        Index(['iv_open', 'iv_high', 'iv_low', 'iv_close', 'volume'])
    """
    if df.empty:
        raise ValueError("Cannot resample empty DataFrame")

    required_cols = {timestamp_col, iv_col}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Ensure timestamp is datetime and set as index
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df[timestamp_col]):
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])

    df = df.set_index(timestamp_col).sort_index()

    # Drop rows with null IV (can't aggregate nulls meaningfully)
    df = df.dropna(subset=[iv_col])

    if df.empty:
        raise ValueError("No valid IV data after dropping nulls")

    # Build aggregation dict
    agg_dict: dict[str, str | list[str]] = {
        iv_col: ["first", "max", "min", "last"],  # OHLC
    }

    if include_volume and "amount" in df.columns:
        agg_dict["amount"] = "sum"

    # Resample
    resampled = df.resample(freq).agg(agg_dict)

    # Flatten column names
    resampled.columns = [
        f"{col}_{agg}" if agg != "sum" else "volume"
        for col, agg in resampled.columns
    ]

    # Rename IV columns to standard OHLC naming
    rename_map = {
        f"{iv_col}_first": "iv_open",
        f"{iv_col}_max": "iv_high",
        f"{iv_col}_min": "iv_low",
        f"{iv_col}_last": "iv_close",
    }
    resampled = resampled.rename(columns=rename_map)

    # Drop periods with no trades
    resampled = resampled.dropna(subset=["iv_close"])

    return resampled


def resample_iv_by_dte(
    df: pd.DataFrame,
    freq: str = DEFAULT_RESAMPLE_FREQ,
    dte_col: str = "dte",
    dte_buckets: list[tuple[int, int]] | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Resample IV separately for each DTE bucket.

    Useful for term structure analysis where different expiry tenors
    have different volatility characteristics.

    Args:
        df: DataFrame with trade data
        freq: Resample frequency
        dte_col: Name of DTE column (or compute from expiry)
        dte_buckets: List of (min_dte, max_dte) tuples
                     Default: [(0,7), (8,14), (15,30), (31,60), (61,90), (91,999)]

    Returns:
        Dict mapping bucket name to resampled DataFrame
    """
    if dte_buckets is None:
        dte_buckets = [
            (0, 7),      # Weekly
            (8, 14),     # Bi-weekly
            (15, 30),    # Monthly
            (31, 60),    # Bi-monthly
            (61, 90),    # Quarterly
            (91, 999),   # LEAPS
        ]

    # Compute DTE if not present
    df = df.copy()
    if dte_col not in df.columns and "expiry" in df.columns and "timestamp" in df.columns:
        expiry_dt = pd.to_datetime(df["expiry"])
        timestamp_dt = pd.to_datetime(df["timestamp"]).dt.normalize()
        df[dte_col] = (expiry_dt - timestamp_dt).dt.days

    if dte_col not in df.columns:
        raise ValueError(
            f"Cannot compute DTE: missing {dte_col} column and cannot derive"
        )

    result = {}
    for min_dte, max_dte in dte_buckets:
        bucket_name = f"dte_{min_dte}_{max_dte}"
        bucket_df = df[(df[dte_col] >= min_dte) & (df[dte_col] <= max_dte)]

        if not bucket_df.empty:
            try:
                result[bucket_name] = resample_iv(bucket_df, freq=freq)
            except ValueError:
                # Skip buckets with insufficient data
                pass

    return result
