# ADR: 2025-12-10-deribit-options-alpha-features
"""
Greeks calculation for Deribit inverse options using vectorized operations.

Uses py_vollib_vectorized for NumPy-vectorized Black-Scholes Greeks
(~100x faster than row-by-row apply). Includes Premium-Adjusted Delta
correction for Deribit's inverse options structure.

Why Python (not ClickHouse):
- Black-Scholes requires scipy.stats.norm (not available in ClickHouse)
- py_vollib_vectorized uses numba JIT for near-native performance
- Greeks computed on fetched data after ClickHouse filtering

Premium-Adjusted Delta (Inverse Options):
Deribit options are inverse (settled in BTC/ETH, not USD). The standard
Black-Scholes delta overestimates exposure because it ignores the premium's
USD value changing with spot. The adjustment:

    adjusted_delta = bs_delta - (option_price / spot_price)

This reduces delta error from 5-20% to 2-5% for deep ITM options.

Reference: Carol Alexander et al. 2023 - "Inverse Options"
           https://arxiv.org/pdf/2107.12041
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    pass

from gapless_deribit_clickhouse.features.config import DEFAULT_CONFIG, FeatureConfig

# Constants
DAYS_PER_YEAR = 365.25


def calculate_greeks(
    df: pd.DataFrame,
    spot_col: str = "spot_price",
    iv_col: str = "iv",
    config: FeatureConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """
    Calculate Delta, Gamma, Vega, Theta with inverse option adjustment.

    Uses py_vollib_vectorized for vectorized Black-Scholes Greeks,
    then applies Premium-Adjusted Delta correction for Deribit inverse
    options.

    Args:
        df: DataFrame with options data. Required columns:
            - strike: Strike price
            - expiry: Expiration date/datetime
            - timestamp: Trade timestamp
            - option_type: 'C' or 'P'
            - price: Option price (in underlying units)
            - {spot_col}: Spot price column
            - {iv_col}: Implied volatility column
        spot_col: Name of spot price column (default: 'spot_price')
        iv_col: Name of IV column (default: 'iv')
        config: FeatureConfig for risk_free_rate

    Returns:
        DataFrame with additional columns:
        - T: Time to expiry in years
        - bs_delta: Standard Black-Scholes delta
        - adjusted_delta: Premium-adjusted delta for inverse options
        - gamma: Option gamma
        - vega: Option vega (per 1% IV move)
        - theta: Option theta (per day)

    Raises:
        ImportError: If py_vollib_vectorized not installed
        ValueError: If required columns are missing

    Example:
        >>> from gapless_deribit_clickhouse.features.spot_provider import (
        ...     enrich_with_spot
        ... )
        >>> df = enrich_with_spot(client, start="2024-01-01", end="2024-03-01")
        >>> df = calculate_greeks(df)
        >>> print(df[["timestamp", "bs_delta", "adjusted_delta", "gamma"]].head())
    """
    try:
        from py_vollib_vectorized.greeks import delta as bs_delta_func
        from py_vollib_vectorized.greeks import gamma as gamma_func
        from py_vollib_vectorized.greeks import theta as theta_func
        from py_vollib_vectorized.greeks import vega as vega_func
    except ImportError as e:
        raise ImportError(
            "py_vollib_vectorized required for Greeks calculation. "
            "Install with: pip install 'gapless-deribit-clickhouse[features]'"
        ) from e

    # Validate required columns
    required_cols = {"strike", "expiry", "timestamp", "option_type", "price", spot_col, iv_col}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df.copy()

    # Time to expiry in years (vectorized)
    expiry_dt = pd.to_datetime(df["expiry"])
    timestamp_dt = pd.to_datetime(df["timestamp"])
    df["T"] = (expiry_dt - timestamp_dt).dt.total_seconds() / (DAYS_PER_YEAR * 24 * 3600)

    # Map option_type to py_vollib format ('c' or 'p')
    df["_flag"] = df["option_type"].str.lower()

    # Filter valid rows for Greeks calculation
    # T > 0: Not expired
    # IV > 0: Valid volatility
    # spot > 0: Valid spot price
    valid_mask = (
        (df["T"] > 0)
        & (df[iv_col] > 0)
        & (df[spot_col] > 0)
        & (df["strike"] > 0)
    )

    # Initialize Greeks columns with NaN
    df["bs_delta"] = np.nan
    df["gamma"] = np.nan
    df["vega"] = np.nan
    df["theta"] = np.nan
    df["adjusted_delta"] = np.nan

    if valid_mask.any():
        # Extract valid data as numpy arrays for vectorized calculation
        flag = df.loc[valid_mask, "_flag"].values
        S = df.loc[valid_mask, spot_col].values.astype(np.float64)
        K = df.loc[valid_mask, "strike"].values.astype(np.float64)
        t = df.loc[valid_mask, "T"].values.astype(np.float64)
        r = config.risk_free_rate
        sigma = df.loc[valid_mask, iv_col].values.astype(np.float64)

        # Vectorized Greeks calculation (all rows at once)
        # py_vollib_vectorized returns DataFrames - extract values with .values.flatten()
        # First call may be slower due to numba JIT compilation
        delta_result = bs_delta_func(flag, S, K, t, r, sigma)
        gamma_result = gamma_func(flag, S, K, t, r, sigma)
        vega_result = vega_func(flag, S, K, t, r, sigma)
        theta_result = theta_func(flag, S, K, t, r, sigma)

        # Extract numpy arrays from DataFrame results
        df.loc[valid_mask, "bs_delta"] = delta_result.values.flatten()
        df.loc[valid_mask, "gamma"] = gamma_result.values.flatten()
        df.loc[valid_mask, "vega"] = vega_result.values.flatten() / 100  # Per 1% IV
        df.loc[valid_mask, "theta"] = theta_result.values.flatten() / DAYS_PER_YEAR

        # Premium-Adjusted Delta for inverse options (vectorized)
        # Reference: Carol Alexander et al. 2023
        option_price = df.loc[valid_mask, "price"].values.astype(np.float64)
        spot_price = df.loc[valid_mask, spot_col].values.astype(np.float64)
        df.loc[valid_mask, "adjusted_delta"] = (
            df.loc[valid_mask, "bs_delta"].values - (option_price / spot_price)
        )

    # Clean up temporary column
    df = df.drop(columns=["_flag"])

    return df


def calculate_portfolio_greeks(
    df: pd.DataFrame,
    position_col: str = "amount",
    spot_col: str = "spot_price",
) -> dict[str, float]:
    """
    Calculate aggregate portfolio Greeks from options positions.

    Sums individual position Greeks weighted by position size.

    Args:
        df: DataFrame with Greeks columns (from calculate_greeks)
            and position sizes
        position_col: Column with position size (positive=long, negative=short)
        spot_col: Spot price column for dollar Greeks

    Returns:
        Dict with portfolio Greeks:
        - net_delta: Sum of adjusted_delta * position
        - net_gamma: Sum of gamma * position
        - net_vega: Sum of vega * position
        - net_theta: Sum of theta * position
        - dollar_delta: net_delta * spot_price
        - dollar_gamma: net_gamma * spot_price

    Example:
        >>> df = calculate_greeks(options_df)
        >>> portfolio = calculate_portfolio_greeks(df)
        >>> print(f"Portfolio delta: {portfolio['net_delta']:.4f}")
    """
    # Use adjusted_delta if available, otherwise bs_delta
    delta_col = "adjusted_delta" if "adjusted_delta" in df.columns else "bs_delta"

    # Filter rows with valid Greeks
    valid = df[delta_col].notna()

    if not valid.any():
        return {
            "net_delta": 0.0,
            "net_gamma": 0.0,
            "net_vega": 0.0,
            "net_theta": 0.0,
            "dollar_delta": 0.0,
            "dollar_gamma": 0.0,
        }

    positions = df.loc[valid, position_col].values

    net_delta = float((df.loc[valid, delta_col].values * positions).sum())
    net_gamma = float((df.loc[valid, "gamma"].values * positions).sum())
    net_vega = float((df.loc[valid, "vega"].values * positions).sum())
    net_theta = float((df.loc[valid, "theta"].values * positions).sum())

    # Dollar Greeks (use median spot for portfolio)
    spot = df.loc[valid, spot_col].median()
    dollar_delta = net_delta * spot
    dollar_gamma = net_gamma * spot

    return {
        "net_delta": net_delta,
        "net_gamma": net_gamma,
        "net_vega": net_vega,
        "net_theta": net_theta,
        "dollar_delta": dollar_delta,
        "dollar_gamma": dollar_gamma,
    }


def aggregate_greeks_by_bucket(
    df: pd.DataFrame,
    bucket_col: str = "moneyness_bucket",
) -> pd.DataFrame:
    """
    Aggregate Greeks by moneyness bucket or DTE bucket.

    Useful for understanding Greek exposure distribution across
    the options surface.

    Args:
        df: DataFrame with Greeks columns
        bucket_col: Column to group by (e.g., 'moneyness_bucket', 'dte_bucket')

    Returns:
        DataFrame with mean Greeks per bucket
    """
    greek_cols = ["bs_delta", "adjusted_delta", "gamma", "vega", "theta"]
    available_cols = [c for c in greek_cols if c in df.columns]

    if not available_cols:
        raise ValueError("No Greek columns found. Run calculate_greeks() first.")

    return df.groupby(bucket_col)[available_cols].agg(["mean", "std", "count"])
