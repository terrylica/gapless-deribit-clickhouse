# ADR: 2025-12-10-deribit-options-alpha-features
"""
EGARCH(1,1) volatility model for IV forecasting.

Uses the arch package to fit Exponential GARCH models to resampled IV.
EGARCH captures asymmetric volatility response (leverage effect) and
Student's t distribution handles crypto's fat-tailed returns.

Configuration (from ADR research):
- p=1, o=1, q=1: Standard EGARCH(1,1) specification
- dist='t': Student's t for fat tails
- Requires REGULAR time series (use resampler first)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pandas as pd

if TYPE_CHECKING:
    from arch.univariate.base import ARCHModelResult

from gapless_deribit_clickhouse.features.config import DEFAULT_CONFIG, FeatureConfig

# EGARCH model parameters (validated in ADR research)
DEFAULT_P = 1  # ARCH order
DEFAULT_O = 1  # Asymmetry order
DEFAULT_Q = 1  # GARCH order
DEFAULT_DIST = "t"  # Student's t distribution for fat tails

# Minimum observations for reliable estimation
MIN_OBSERVATIONS = 100


def fit_egarch(
    iv_series: pd.Series,
    p: int = DEFAULT_P,
    o: int = DEFAULT_O,
    q: int = DEFAULT_Q,
    dist: str = DEFAULT_DIST,
    rescale: bool = True,
) -> ARCHModelResult:
    """
    Fit EGARCH model to IV series.

    EGARCH captures asymmetric volatility response:
    - Negative shocks increase volatility more than positive shocks
    - Critical for crypto where fear drives larger vol spikes

    Args:
        iv_series: Resampled IV (MUST be regular time series)
        p: ARCH order (default: 1)
        o: Asymmetry order (default: 1)
        q: GARCH order (default: 1)
        dist: Error distribution - 't' for Student's t (default)
        rescale: If True, rescale data for numerical stability

    Returns:
        Fitted ARCHModelResult

    Raises:
        ValueError: If series is empty, irregular, or too short
        ImportError: If arch package not installed

    Example:
        >>> from gapless_deribit_clickhouse.features import resample_iv, fit_egarch
        >>> resampled = resample_iv(trades_df)
        >>> result = fit_egarch(resampled["iv_close"])
        >>> print(result.summary())
    """
    try:
        from arch import arch_model
    except ImportError as e:
        raise ImportError(
            "arch package required for EGARCH. Install with: pip install arch"
        ) from e

    if iv_series.empty:
        raise ValueError("Cannot fit EGARCH on empty series")

    # Drop NaN values
    iv_series = iv_series.dropna()

    if len(iv_series) < MIN_OBSERVATIONS:
        raise ValueError(
            f"Insufficient data: {len(iv_series)} observations "
            f"(minimum: {MIN_OBSERVATIONS})"
        )

    # Check for regular time series
    if isinstance(iv_series.index, pd.DatetimeIndex):
        time_diffs = iv_series.index.to_series().diff().dropna()
        unique_diffs = time_diffs.unique()

        # Allow small tolerance for floating point
        if len(unique_diffs) > 3:  # More than 3 unique intervals suggests irregular
            raise ValueError(
                "IV series appears irregular. Use resample_iv() first to create "
                "regular time series. EGARCH requires fixed-interval data."
            )

    # Rescale for numerical stability (arch recommends this)
    if rescale:
        scale_factor = iv_series.std()
        if scale_factor > 0:
            iv_series = iv_series / scale_factor
        else:
            rescale = False  # Can't rescale if std is 0

    # Fit EGARCH model
    model = arch_model(
        iv_series,
        vol="EGARCH",
        p=p,
        o=o,
        q=q,
        dist=dist,
        rescale=False,  # We already rescaled manually
    )

    result = model.fit(disp="off", show_warning=False)

    # Store scale factor for later use
    if rescale:
        result._scale_factor = scale_factor  # type: ignore[attr-defined]
    else:
        result._scale_factor = 1.0  # type: ignore[attr-defined]

    return result


def auto_select_egarch(
    iv_series: pd.Series,
    p_range: tuple[int, int] = (1, 2),
    q_range: tuple[int, int] = (1, 2),
    criterion: Literal["aic", "bic"] = "aic",
    config: FeatureConfig = DEFAULT_CONFIG,
) -> ARCHModelResult:
    """
    Auto-select EGARCH order using information criteria grid search.

    Since no pmdarima equivalent exists for GARCH models, this function
    performs a grid search over (p, q) combinations and selects the model
    with the lowest AIC or BIC.

    The asymmetry order (o) is fixed at 1 as this is the standard EGARCH
    specification that captures the leverage effect.

    Args:
        iv_series: Resampled IV (MUST be regular time series)
        p_range: (min_p, max_p) for ARCH order search (default: (1, 2))
        q_range: (min_q, max_q) for GARCH order search (default: (1, 2))
        criterion: Selection criterion - 'aic' or 'bic' (default: 'aic')
        config: FeatureConfig for distribution and other parameters

    Returns:
        Best fitted ARCHModelResult based on criterion

    Raises:
        ValueError: If no valid model could be fit
        ImportError: If arch package not installed

    Example:
        >>> from gapless_deribit_clickhouse.features import resample_iv, auto_select_egarch
        >>> resampled = resample_iv(trades_df)
        >>> best_model = auto_select_egarch(resampled["iv_close"])
        >>> print(f"Selected: EGARCH({best_model.model.p}, 1, {best_model.model.q})")
        >>> print(f"AIC: {best_model.aic:.2f}")
    """
    best_result: ARCHModelResult | None = None
    best_score = float("inf")
    best_params: tuple[int, int] | None = None

    for p in range(p_range[0], p_range[1] + 1):
        for q in range(q_range[0], q_range[1] + 1):
            try:
                result = fit_egarch(
                    iv_series,
                    p=p,
                    o=config.egarch_o,  # Asymmetry order fixed
                    q=q,
                    dist=config.egarch_dist,
                )
                score = result.aic if criterion == "aic" else result.bic

                if score < best_score:
                    best_score = score
                    best_result = result
                    best_params = (p, q)

            except (ValueError, RuntimeError):
                # Skip combinations that fail to converge
                continue

    if best_result is None:
        raise ValueError(
            f"No valid EGARCH model found in grid search "
            f"(p={p_range}, q={q_range}). Check data quality."
        )

    # Store selection metadata for diagnostics
    best_result._auto_selected = True  # type: ignore[attr-defined]
    best_result._selection_criterion = criterion  # type: ignore[attr-defined]
    best_result._selection_score = best_score  # type: ignore[attr-defined]
    best_result._selected_params = best_params  # type: ignore[attr-defined]

    return best_result


def forecast_volatility(
    result: ARCHModelResult,
    horizon: int = 1,
    method: str = "analytic",
) -> pd.DataFrame:
    """
    Generate volatility forecast from fitted EGARCH model.

    Args:
        result: Fitted ARCHModelResult from fit_egarch()
        horizon: Forecast horizon in periods (default: 1)
        method: Forecast method - 'analytic', 'simulation', 'bootstrap'

    Returns:
        DataFrame with forecast variance and mean

    Raises:
        ValueError: If horizon < 1
    """
    if horizon < 1:
        raise ValueError("Horizon must be at least 1")

    forecast = result.forecast(horizon=horizon, method=method)

    # Get scale factor if we rescaled
    scale_factor = getattr(result, "_scale_factor", 1.0)

    # Extract variance forecast and rescale
    variance_forecast = forecast.variance.iloc[-1] * (scale_factor ** 2)

    return pd.DataFrame({
        "variance": variance_forecast,
        "volatility": variance_forecast ** 0.5,
    })


def egarch_residuals(
    result: ARCHModelResult,
) -> pd.Series:
    """
    Extract standardized residuals from fitted model.

    Useful for model diagnostics and regime detection.

    Args:
        result: Fitted ARCHModelResult

    Returns:
        Series of standardized residuals
    """
    return result.std_resid


def egarch_conditional_volatility(
    result: ARCHModelResult,
) -> pd.Series:
    """
    Extract conditional volatility (fitted values) from model.

    This is the model's estimate of volatility at each time point.

    Args:
        result: Fitted ARCHModelResult

    Returns:
        Series of conditional volatility values
    """
    scale_factor = getattr(result, "_scale_factor", 1.0)
    return result.conditional_volatility * scale_factor


def iv_vs_egarch_spread(
    iv_series: pd.Series,
    result: ARCHModelResult,
) -> pd.Series:
    """
    Calculate spread between realized IV and EGARCH forecast.

    Positive spread: IV elevated relative to model (potential mean reversion)
    Negative spread: IV depressed relative to model

    Args:
        iv_series: Original IV series (aligned with model)
        result: Fitted ARCHModelResult

    Returns:
        Series of spread values
    """
    conditional_vol = egarch_conditional_volatility(result)

    # Align indexes
    aligned = pd.DataFrame({
        "iv": iv_series,
        "egarch": conditional_vol,
    }).dropna()

    spread = aligned["iv"] - aligned["egarch"]
    spread.name = "iv_egarch_spread"

    return spread
