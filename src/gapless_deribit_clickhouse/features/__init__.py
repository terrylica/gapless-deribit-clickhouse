# ADR: 2025-12-10-deribit-options-alpha-features
"""
Alpha features module for Deribit options data.

Provides ML-ready features derived from options trades for consumption
by alpha-forge YAML DSL strategy platform.

Phase 1 Features (IV-Only):
- 15-minute IV resampling (regular time series for GARCH)
- IV Percentile (90-day rolling rank)
- Term Structure Slope (near vs far IV)
- Put-Call Ratio by tenor
- DTE Bucket Aggregations
- EGARCH(1,1) volatility model with auto-selection

Phase 2 Features (Contract Selection & Spot Integration):
- Systematic contract selection (front-month, ATM, liquidity filters)
- Hybrid spot price provider (Deribit index + Binance fallback)
- Moneyness bucket aggregations with smile metrics
- Greeks calculation with inverse option adjustment
"""

# Configuration
from gapless_deribit_clickhouse.features.config import (
    CONSERVATIVE_CONFIG,
    DEFAULT_CONFIG,
    HIGH_FREQUENCY_CONFIG,
    FeatureConfig,
)

# Phase 2: Contract Selection & Spot Integration
from gapless_deribit_clickhouse.features.contract_selector import (
    build_contract_selection_query,
    select_contracts,
)

# Phase 1: IV-Only Features
from gapless_deribit_clickhouse.features.dte_buckets import dte_bucket_agg
from gapless_deribit_clickhouse.features.egarch import (
    auto_select_egarch,
    fit_egarch,
    forecast_volatility,
)
from gapless_deribit_clickhouse.features.greeks import (
    calculate_greeks,
    calculate_portfolio_greeks,
)
from gapless_deribit_clickhouse.features.iv_percentile import iv_percentile
from gapless_deribit_clickhouse.features.moneyness import (
    aggregate_by_moneyness,
    build_moneyness_aggregation_query,
)
from gapless_deribit_clickhouse.features.pcr import pcr_by_tenor
from gapless_deribit_clickhouse.features.resampler import resample_iv
from gapless_deribit_clickhouse.features.spot_provider import (
    build_spot_enriched_query,
    enrich_with_spot,
)
from gapless_deribit_clickhouse.features.term_structure import term_structure_slope

__all__ = [
    # Configuration
    "FeatureConfig",
    "DEFAULT_CONFIG",
    "CONSERVATIVE_CONFIG",
    "HIGH_FREQUENCY_CONFIG",
    # Phase 1: IV Features
    "resample_iv",
    "iv_percentile",
    "term_structure_slope",
    "pcr_by_tenor",
    "dte_bucket_agg",
    "fit_egarch",
    "auto_select_egarch",
    "forecast_volatility",
    # Phase 2: Contract Selection
    "build_contract_selection_query",
    "select_contracts",
    # Phase 2: Spot Integration
    "build_spot_enriched_query",
    "enrich_with_spot",
    # Phase 2: Moneyness
    "build_moneyness_aggregation_query",
    "aggregate_by_moneyness",
    # Phase 2: Greeks
    "calculate_greeks",
    "calculate_portfolio_greeks",
]
