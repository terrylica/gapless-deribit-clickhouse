# ADR: 2025-12-10-deribit-options-alpha-features
"""
Alpha features module for Deribit options data.

Provides ML-ready features derived from options trades for consumption
by alpha-forge YAML DSL strategy platform.

Features:
- 15-minute IV resampling (regular time series for GARCH)
- IV Percentile (90-day rolling rank)
- Term Structure Slope (near vs far IV)
- Put-Call Ratio by tenor
- DTE Bucket Aggregations
- EGARCH(1,1) volatility model
"""

from gapless_deribit_clickhouse.features.dte_buckets import dte_bucket_agg
from gapless_deribit_clickhouse.features.egarch import fit_egarch, forecast_volatility
from gapless_deribit_clickhouse.features.iv_percentile import iv_percentile
from gapless_deribit_clickhouse.features.pcr import pcr_by_tenor
from gapless_deribit_clickhouse.features.resampler import resample_iv
from gapless_deribit_clickhouse.features.term_structure import term_structure_slope

__all__ = [
    "resample_iv",
    "iv_percentile",
    "term_structure_slope",
    "pcr_by_tenor",
    "dte_bucket_agg",
    "fit_egarch",
    "forecast_volatility",
]
