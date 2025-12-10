# ADR: 2025-12-10-deribit-options-alpha-features
"""
Centralized configuration for feature calculations.

This module provides a single source of truth for all configurable parameters
across the features module. All values were validated during ADR research
and can be overridden per-use-case.

Usage:
    from gapless_deribit_clickhouse.features.config import DEFAULT_CONFIG, FeatureConfig

    # Use defaults
    result = resample_iv(df, config=DEFAULT_CONFIG)

    # Override specific values
    custom = FeatureConfig(iv_lookback_days=60, risk_free_rate=0.03)
    result = calculate_greeks(df, config=custom)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Type aliases for clarity
DTEBucket = tuple[int, int]
MoneynessThreshold = float


@dataclass(frozen=True)
class FeatureConfig:
    """Centralized configuration for feature calculations.

    All defaults are validated from ADR research:
    - EGARCH parameters: Industry standard for crypto volatility
    - Risk-free rate: Matches Deribit internal models
    - DTE buckets: Standard option tenor classification
    - IV lookback: Crypto-specific (faster cycles than TradFi)

    Attributes:
        min_observations: Minimum data points for EGARCH estimation
        egarch_p: ARCH order (default: 1)
        egarch_o: Asymmetry order for leverage effect (default: 1)
        egarch_q: GARCH order (default: 1)
        egarch_dist: Error distribution - 't' for Student's t (fat tails)
        risk_free_rate: Risk-free rate for Greeks (2% matches Deribit)
        atm_width: ATM filter width as fraction (0.05 = +/-5%)
        min_volume: Minimum daily volume for liquidity filter
        iv_lookback_days: Rolling window for IV percentile (90d for crypto)
        resample_freq: Default resampling frequency
        dte_buckets: DTE bucket boundaries for term structure
        moneyness_thresholds: Boundaries for moneyness buckets
    """

    # EGARCH model parameters
    min_observations: int = 100
    egarch_p: int = 1
    egarch_o: int = 1  # Asymmetry order
    egarch_q: int = 1
    egarch_dist: Literal["normal", "t", "skewt", "ged"] = "t"

    # Greeks calculation
    risk_free_rate: float = 0.02  # 2% - matches Deribit internal models

    # Contract selection
    atm_width: float = 0.05  # +/- 5% of spot
    min_volume: float = 10.0  # Minimum daily notional

    # IV features
    iv_lookback_days: int = 90  # 90 days - crypto cycles faster than TradFi
    resample_freq: str = "15min"  # Works for 2018-2024 trade density

    # DTE buckets - full set including LEAPS
    # Note: PCR module excludes LEAPS internally (PCR not meaningful for long-dated)
    dte_buckets: tuple[DTEBucket, ...] = (
        (0, 7),      # Weekly
        (8, 14),     # Bi-weekly
        (15, 30),    # Monthly
        (31, 60),    # Bi-monthly
        (61, 90),    # Quarterly
        (91, 999),   # LEAPS
    )

    # Moneyness buckets for smile/skew analysis
    moneyness_thresholds: tuple[MoneynessThreshold, ...] = (
        0.90,   # Deep OTM put boundary
        0.95,   # OTM put boundary
        1.05,   # OTM call boundary
        1.10,   # Deep OTM call boundary
    )

    # Term structure parameters
    near_dte_max: int = 30   # "Near" expiry: 0-30 DTE
    far_dte_min: int = 60    # "Far" expiry: 60+ DTE

    def get_pcr_dte_buckets(self) -> tuple[DTEBucket, ...]:
        """Return DTE buckets excluding LEAPS for PCR calculation.

        PCR (Put-Call Ratio) is a lagging indicator primarily useful for
        near-term sentiment analysis. LEAPS (91+ DTE) are excluded because:
        1. Low trading activity distorts ratios
        2. PCR as a sentiment gauge is not meaningful for long-dated hedges
        """
        return tuple(b for b in self.dte_buckets if b[1] <= 90)

    def get_moneyness_bucket_labels(self) -> list[str]:
        """Return human-readable labels for moneyness buckets.

        Returns bucket labels in order:
        ['deep_otm_put', 'otm_put', 'atm', 'otm_call', 'deep_otm_call']
        """
        return [
            "deep_otm_put",
            "otm_put",
            "atm",
            "otm_call",
            "deep_otm_call",
        ]


# Default instance - import this for standard usage
DEFAULT_CONFIG = FeatureConfig()

# Presets for common use cases
CONSERVATIVE_CONFIG = FeatureConfig(
    min_observations=200,  # More data for stability
    iv_lookback_days=120,  # Longer lookback
    min_volume=50.0,       # Stricter liquidity filter
)

HIGH_FREQUENCY_CONFIG = FeatureConfig(
    resample_freq="5min",  # Finer granularity (requires 2021+ data)
    iv_lookback_days=30,   # Faster adaptation
    min_observations=50,   # Less data needed
)
