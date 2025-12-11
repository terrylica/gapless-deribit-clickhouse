# ADR: 2025-12-10-deribit-options-alpha-features
# ADR: 2025-12-10-pipeline-memory-optimization (vectorized percentile)
# ADR: 2025-12-10-schema-optimization (raw=True for O(n) performance)
"""
IV Percentile (IV Rank) calculation.

Computes the percentile rank of current IV relative to a rolling
historical window. Uses 90-day lookback by default (crypto cycles
faster than traditional finance 252-day convention).

Performance Note:
- Uses vectorized rolling operations (O(n) instead of O(n²))
- Avoids .apply() with raw=False which creates Series per call
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Default lookback in days - crypto cycles faster than TradFi
DEFAULT_LOOKBACK_DAYS = 90


def iv_percentile(
    iv_series: pd.Series,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_periods: int | None = None,
) -> pd.Series:
    """
    Calculate IV percentile (rank) over rolling window.

    IV Percentile shows where current IV stands relative to its
    historical range. High percentile (>80) suggests IV is elevated;
    low percentile (<20) suggests IV is depressed.

    Args:
        iv_series: IV values indexed by timestamp (must be sorted)
        lookback_days: Rolling window in days (default: 90)
        min_periods: Minimum observations required. Default: lookback_days // 2

    Returns:
        Series of percentile values (0-100)

    Raises:
        ValueError: If iv_series is empty or not datetime-indexed

    Example:
        >>> iv = pd.Series([0.5, 0.6, 0.4, 0.7, 0.55],
        ...                index=pd.date_range("2024-01-01", periods=5))
        >>> iv_percentile(iv, lookback_days=3)
    """
    if iv_series.empty:
        raise ValueError("Cannot compute percentile on empty series")

    if not isinstance(iv_series.index, pd.DatetimeIndex):
        raise ValueError("iv_series must have DatetimeIndex")

    # Ensure sorted
    iv_series = iv_series.sort_index()

    # Convert lookback days to window size based on data frequency
    # Infer frequency from data
    if len(iv_series) < 2:
        raise ValueError("Need at least 2 data points for percentile calculation")

    # Calculate average time delta to estimate frequency
    time_deltas = iv_series.index.to_series().diff().dropna()
    avg_delta = time_deltas.mean()

    # Convert lookback_days to number of periods
    lookback_periods = int(pd.Timedelta(days=lookback_days) / avg_delta)
    lookback_periods = max(lookback_periods, 2)  # At least 2 periods

    if min_periods is None:
        min_periods = max(lookback_periods // 2, 1)

    # ADR: 2025-12-10-pipeline-memory-optimization
    # Performance fix: Use raw=True to pass numpy array instead of Series
    # This avoids O(n²) overhead from pandas Series construction per window
    #
    # Algorithm: For each point, count how many values in the lookback
    # window are <= current value, divide by window size.
    def _count_leq(arr: np.ndarray) -> float:
        """Count values in window <= last value (vectorized-friendly)."""
        if len(arr) < 2:
            return np.nan
        current = arr[-1]
        historical = arr[:-1]
        return (np.sum(historical <= current) / len(historical)) * 100

    percentiles = iv_series.rolling(
        window=lookback_periods,
        min_periods=min_periods,
    ).apply(_count_leq, raw=True)  # raw=True passes numpy array (faster)

    return percentiles


def iv_rank(
    iv_series: pd.Series,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_periods: int | None = None,
) -> pd.Series:
    """
    Calculate IV Rank (alternative formulation).

    IV Rank = (Current IV - Min IV) / (Max IV - Min IV) * 100

    This is an alternative to IV Percentile that only considers
    the min/max range, not the full distribution.

    Args:
        iv_series: IV values indexed by timestamp
        lookback_days: Rolling window in days (default: 90)
        min_periods: Minimum observations required

    Returns:
        Series of rank values (0-100)
    """
    if iv_series.empty:
        raise ValueError("Cannot compute rank on empty series")

    if not isinstance(iv_series.index, pd.DatetimeIndex):
        raise ValueError("iv_series must have DatetimeIndex")

    iv_series = iv_series.sort_index()

    # Calculate window size
    if len(iv_series) < 2:
        raise ValueError("Need at least 2 data points")

    time_deltas = iv_series.index.to_series().diff().dropna()
    avg_delta = time_deltas.mean()
    lookback_periods = int(pd.Timedelta(days=lookback_days) / avg_delta)
    lookback_periods = max(lookback_periods, 2)

    if min_periods is None:
        min_periods = max(lookback_periods // 2, 1)

    # Calculate rolling min and max
    rolling_min = iv_series.rolling(window=lookback_periods, min_periods=min_periods).min()
    rolling_max = iv_series.rolling(window=lookback_periods, min_periods=min_periods).max()

    # IV Rank formula
    range_size = rolling_max - rolling_min
    iv_rank_values = ((iv_series - rolling_min) / range_size) * 100

    # Handle division by zero (when min == max)
    iv_rank_values = iv_rank_values.replace([float("inf"), float("-inf")], float("nan"))

    return iv_rank_values
