# ADR: 2025-12-10-deribit-options-alpha-features
"""
IV Term Structure Slope calculation.

Measures the difference between near-term and far-term implied volatility.
Positive slope (contango): near > far - suggests near-term uncertainty
Negative slope (backwardation): far > near - typical calm market state
"""

from __future__ import annotations

import pandas as pd

# Default DTE boundaries for near/far term buckets
DEFAULT_NEAR_DTE_MAX = 30   # Near-term: 0-30 days
DEFAULT_FAR_DTE_MIN = 60    # Far-term: 60+ days


def term_structure_slope(
    df: pd.DataFrame,
    near_dte_max: int = DEFAULT_NEAR_DTE_MAX,
    far_dte_min: int = DEFAULT_FAR_DTE_MIN,
    timestamp_col: str = "timestamp",
    iv_col: str = "iv",
    dte_col: str = "dte",
    freq: str = "15min",
) -> pd.Series:
    """
    Calculate term structure slope (IV spread).

    Slope = Mean(Near-term IV) - Mean(Far-term IV)

    Positive: Near-term elevated (event risk, uncertainty)
    Negative: Far-term elevated (typical market structure)

    Args:
        df: DataFrame with 'iv', 'dte', and 'timestamp' columns
        near_dte_max: Max DTE for near-term bucket (default: 30)
        far_dte_min: Min DTE for far-term bucket (default: 60)
        timestamp_col: Name of timestamp column
        iv_col: Name of IV column
        dte_col: Name of DTE column (or computed from expiry)
        freq: Aggregation frequency (default: 15min)

    Returns:
        Series of slope values indexed by timestamp

    Raises:
        ValueError: If required columns missing or insufficient data
    """
    if df.empty:
        raise ValueError("Cannot compute term structure on empty DataFrame")

    df = df.copy()

    # Compute DTE if not present
    if dte_col not in df.columns:
        if "expiry" not in df.columns or timestamp_col not in df.columns:
            raise ValueError(f"Missing {dte_col} column and cannot derive from expiry/timestamp")
        df[dte_col] = (
            pd.to_datetime(df["expiry"]) - pd.to_datetime(df[timestamp_col]).dt.normalize()
        ).dt.days

    # Validate required columns
    required = {timestamp_col, iv_col, dte_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Filter to near and far term
    near_term = df[df[dte_col] <= near_dte_max].copy()
    far_term = df[df[dte_col] >= far_dte_min].copy()

    if near_term.empty or far_term.empty:
        raise ValueError(
            f"Insufficient data: near_term={len(near_term)}, far_term={len(far_term)}"
        )

    # Ensure datetime index
    for subset in [near_term, far_term]:
        if not pd.api.types.is_datetime64_any_dtype(subset[timestamp_col]):
            subset[timestamp_col] = pd.to_datetime(subset[timestamp_col])

    # Aggregate IV by timestamp
    near_term = near_term.set_index(timestamp_col)
    far_term = far_term.set_index(timestamp_col)

    near_iv = near_term[iv_col].resample(freq).mean()
    far_iv = far_term[iv_col].resample(freq).mean()

    # Align indexes and compute slope
    aligned = pd.DataFrame({"near": near_iv, "far": far_iv})
    aligned = aligned.dropna()

    if aligned.empty:
        raise ValueError("No overlapping timestamps between near and far term data")

    slope = aligned["near"] - aligned["far"]
    slope.name = "term_structure_slope"

    return slope


def term_structure_ratio(
    df: pd.DataFrame,
    near_dte_max: int = DEFAULT_NEAR_DTE_MAX,
    far_dte_min: int = DEFAULT_FAR_DTE_MIN,
    timestamp_col: str = "timestamp",
    iv_col: str = "iv",
    dte_col: str = "dte",
    freq: str = "15min",
) -> pd.Series:
    """
    Calculate term structure ratio.

    Ratio = Near-term IV / Far-term IV

    >1.0: Contango (near elevated)
    <1.0: Backwardation (far elevated)
    =1.0: Flat term structure

    Args:
        df: DataFrame with trade data
        near_dte_max: Max DTE for near-term
        far_dte_min: Min DTE for far-term
        timestamp_col: Timestamp column name
        iv_col: IV column name
        dte_col: DTE column name
        freq: Aggregation frequency

    Returns:
        Series of ratio values
    """
    if df.empty:
        raise ValueError("Cannot compute term structure on empty DataFrame")

    df = df.copy()

    # Compute DTE if not present
    if dte_col not in df.columns:
        if "expiry" not in df.columns or timestamp_col not in df.columns:
            raise ValueError(f"Missing {dte_col} column")
        df[dte_col] = (
            pd.to_datetime(df["expiry"]) - pd.to_datetime(df[timestamp_col]).dt.normalize()
        ).dt.days

    near_term = df[df[dte_col] <= near_dte_max].copy()
    far_term = df[df[dte_col] >= far_dte_min].copy()

    if near_term.empty or far_term.empty:
        raise ValueError("Insufficient data for term structure calculation")

    for subset in [near_term, far_term]:
        if not pd.api.types.is_datetime64_any_dtype(subset[timestamp_col]):
            subset[timestamp_col] = pd.to_datetime(subset[timestamp_col])

    near_term = near_term.set_index(timestamp_col)
    far_term = far_term.set_index(timestamp_col)

    near_iv = near_term[iv_col].resample(freq).mean()
    far_iv = far_term[iv_col].resample(freq).mean()

    aligned = pd.DataFrame({"near": near_iv, "far": far_iv})
    aligned = aligned.dropna()

    if aligned.empty:
        raise ValueError("No overlapping timestamps")

    # Avoid division by zero
    ratio = aligned["near"] / aligned["far"].replace(0, float("nan"))
    ratio.name = "term_structure_ratio"

    return ratio
