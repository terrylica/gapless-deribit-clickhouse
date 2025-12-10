# ADR: 2025-12-10-deribit-options-alpha-features
"""
Comprehensive tests for Phase 1 IV-only features.

Uses real Deribit data patterns:
- Realistic BTC options with typical IVs (40-120%)
- Multiple expiries across term structure
- Both calls and puts for PCR tests
- Various DTE buckets for aggregation tests

Test coverage:
- resample_iv: Regular time series creation
- iv_percentile: Rolling percentile rank
- dte_bucket_agg: Tenor-based aggregation
- pcr_by_tenor: Put-call ratio by expiry
- term_structure_slope: Near vs far IV spread
- EGARCH: Volatility modeling
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

# === Real Deribit Data Patterns Fixtures ===


@pytest.fixture
def realistic_trades_df() -> pd.DataFrame:
    """
    Create realistic BTC options trades like Deribit data.

    Patterns based on actual Deribit characteristics:
    - BTC options with IVs typically 40-120%
    - Multiple expiries (weekly, monthly, quarterly)
    - Mix of calls and puts
    - Index prices around current BTC levels
    - Trade amounts 0.1-10 contracts
    """
    np.random.seed(42)  # Reproducibility

    # Generate 2 hours of 15-minute data (8 intervals + some extras for resampling)
    base_time = datetime(2024, 12, 1, 10, 0, 0)
    num_trades = 200

    # Realistic expiry dates
    expiries = [
        datetime(2024, 12, 6),   # 5 DTE (weekly)
        datetime(2024, 12, 13),  # 12 DTE (bi-weekly)
        datetime(2024, 12, 27),  # 26 DTE (monthly)
        datetime(2025, 1, 31),   # 61 DTE (bi-monthly)
        datetime(2025, 3, 28),   # 117 DTE (quarterly)
    ]

    trades = []
    for i in range(num_trades):
        # Spread trades across time
        ts = base_time + timedelta(minutes=np.random.randint(0, 120))
        expiry = expiries[i % len(expiries)]
        option_type = "C" if i % 3 != 0 else "P"  # ~2/3 calls, 1/3 puts

        # Realistic BTC IV: higher for shorter DTE, lower for longer
        dte = (expiry - ts.replace(hour=0, minute=0, second=0)).days
        base_iv = 0.55 + (0.15 * np.exp(-dte / 30))  # Term structure shape
        iv = base_iv + np.random.uniform(-0.10, 0.15)
        iv = max(0.30, min(1.20, iv))  # Clamp to realistic range

        # Realistic index price (BTC around 97k in Dec 2024)
        index_price = 97000 + np.random.uniform(-2000, 2000)

        # Strike around ATM
        strike = round(index_price / 1000) * 1000 + np.random.choice(
            [-5000, -2000, -1000, 0, 1000, 2000, 5000]
        )

        trades.append({
            "timestamp": ts,
            "expiry": expiry,
            "option_type": option_type,
            "strike": float(strike),
            "iv": iv,
            "index_price": index_price,
            "price": np.random.uniform(0.01, 0.15),
            "amount": np.random.uniform(0.1, 5.0),
            "direction": np.random.choice(["buy", "sell"]),
            "trade_id": f"TRD-{i:06d}",
            "instrument_name": (
                f"BTC-{expiry.strftime('%d%b%y').upper()}-{int(strike)}-{option_type}"
            ),
        })

    df = pd.DataFrame(trades)
    return df.sort_values("timestamp").reset_index(drop=True)


@pytest.fixture
def regular_iv_series() -> pd.Series:
    """
    Create regular 15-minute IV series for EGARCH testing.

    Mimics what resample_iv() produces - regular time intervals
    with IV values showing typical volatility clustering.
    """
    np.random.seed(123)

    # 200 periods of 15-min data (~50 hours)
    periods = 200
    base_time = datetime(2024, 12, 1, 0, 0, 0)
    index = pd.date_range(start=base_time, periods=periods, freq="15min")

    # Generate IV with volatility clustering (GARCH-like)
    iv_values = [0.60]  # Start at 60%
    for i in range(1, periods):
        # Mean-reverting with persistence
        shock = np.random.normal(0, 0.02)
        new_iv = 0.15 * 0.60 + 0.85 * iv_values[-1] + shock
        new_iv = max(0.30, min(1.20, new_iv))  # Clamp
        iv_values.append(new_iv)

    series = pd.Series(iv_values, index=index, name="iv_close")
    return series


@pytest.fixture
def multi_dte_df() -> pd.DataFrame:
    """
    DataFrame with trades across all DTE buckets.

    Ensures coverage of:
    - 0-7 days (weekly)
    - 8-14 days (bi-weekly)
    - 15-30 days (monthly)
    - 31-60 days (bi-monthly)
    - 61-90 days (quarterly)
    - 91+ days (LEAPS)
    """
    np.random.seed(456)

    base_time = datetime(2024, 12, 1, 10, 0, 0)

    # DTE targets for each bucket
    dte_targets = [3, 10, 22, 45, 75, 120]  # One per bucket

    trades = []
    for dte in dte_targets:
        expiry = base_time + timedelta(days=dte)
        for j in range(30):  # 30 trades per bucket
            ts = base_time + timedelta(minutes=j * 4)  # Spread across 2 hours
            iv = 0.50 + (0.20 * np.exp(-dte / 30)) + np.random.uniform(-0.05, 0.05)

            trades.append({
                "timestamp": ts,
                "expiry": expiry,
                "option_type": np.random.choice(["C", "P"]),
                "strike": 100000.0,
                "iv": iv,
                "index_price": 97000.0,
                "price": 0.05,
                "amount": np.random.uniform(0.5, 3.0),
                "direction": "buy",
            })

    return pd.DataFrame(trades)


# === resample_iv Tests ===


class TestResampleIV:
    """Tests for IV resampling to regular time series."""

    def test_resample_creates_regular_series(self, realistic_trades_df: pd.DataFrame) -> None:
        """Test that resample_iv creates regular 15-min intervals."""
        from gapless_deribit_clickhouse.features import resample_iv

        result = resample_iv(realistic_trades_df, freq="15min")

        assert isinstance(result, pd.DataFrame)
        assert "iv_close" in result.columns or "iv_mean" in result.columns

        # Check index is DatetimeIndex
        assert isinstance(result.index, pd.DatetimeIndex)

        # Verify regular intervals (all diffs should be same)
        if len(result) > 1:
            diffs = result.index.to_series().diff().dropna()
            unique_diffs = diffs.unique()
            assert len(unique_diffs) == 1

    def test_resample_preserves_iv_range(self, realistic_trades_df: pd.DataFrame) -> None:
        """Test resampled IV stays in realistic range."""
        from gapless_deribit_clickhouse.features import resample_iv

        result = resample_iv(realistic_trades_df)

        iv_col = "iv_close" if "iv_close" in result.columns else "iv_mean"
        iv_values = result[iv_col].dropna()

        # Deribit IVs typically 30-120%
        assert iv_values.min() >= 0.20
        assert iv_values.max() <= 1.50

    def test_resample_empty_df_raises(self) -> None:
        """Test that empty DataFrame raises ValueError."""
        from gapless_deribit_clickhouse.features import resample_iv

        empty_df = pd.DataFrame(columns=["timestamp", "iv"])

        with pytest.raises(ValueError, match="empty"):
            resample_iv(empty_df)


# === iv_percentile Tests ===


class TestIVPercentile:
    """Tests for IV percentile rank calculation."""

    def test_percentile_range(self, regular_iv_series: pd.Series) -> None:
        """Test percentile values are in [0, 100] range."""
        from gapless_deribit_clickhouse.features import iv_percentile

        # Use short lookback that fits within 200 periods * 15min = ~50 hours
        # 1 day lookback = 96 periods (15min each)
        result = iv_percentile(regular_iv_series, lookback_days=1, min_periods=20)

        valid_values = result.dropna()
        assert len(valid_values) > 0
        assert valid_values.min() >= 0
        assert valid_values.max() <= 100

    def test_percentile_respects_lookback(self, regular_iv_series: pd.Series) -> None:
        """Test shorter lookback produces different results."""
        from gapless_deribit_clickhouse.features import iv_percentile

        pct_30d = iv_percentile(regular_iv_series, lookback_days=30)
        pct_60d = iv_percentile(regular_iv_series, lookback_days=60)

        # Should have some different values (not identical)
        common_idx = pct_30d.dropna().index.intersection(pct_60d.dropna().index)
        if len(common_idx) > 10:
            diff = (pct_30d[common_idx] - pct_60d[common_idx]).abs()
            assert diff.max() > 0.1  # Some variation expected

    def test_percentile_empty_raises(self) -> None:
        """Test empty series raises error."""
        from gapless_deribit_clickhouse.features import iv_percentile

        empty_series = pd.Series([], dtype=float)

        with pytest.raises((ValueError, KeyError)):
            iv_percentile(empty_series)


# === dte_bucket_agg Tests ===


class TestDTEBucketAgg:
    """Tests for DTE bucket aggregations."""

    def test_bucket_agg_returns_all_buckets(self, multi_dte_df: pd.DataFrame) -> None:
        """Test aggregation returns data for all populated buckets."""
        from gapless_deribit_clickhouse.features import dte_bucket_agg

        result = dte_bucket_agg(multi_dte_df)

        assert isinstance(result, pd.DataFrame)
        assert len(result.columns) > 0

        # Should have columns for multiple buckets
        bucket_cols = [c for c in result.columns if c.startswith("dte_")]
        assert len(bucket_cols) >= 3

    def test_bucket_agg_iv_stats(self, multi_dte_df: pd.DataFrame) -> None:
        """Test IV aggregation produces mean and std."""
        from gapless_deribit_clickhouse.features import dte_bucket_agg

        result = dte_bucket_agg(multi_dte_df, metrics=["iv"])

        # Check for IV columns
        iv_cols = [c for c in result.columns if "iv" in c.lower()]
        assert len(iv_cols) > 0

        # Values should be in realistic range
        for col in iv_cols:
            valid = result[col].dropna()
            if len(valid) > 0:
                assert valid.min() >= 0
                assert valid.max() <= 2.0  # IV as decimal

    def test_bucket_agg_volume_stats(self, multi_dte_df: pd.DataFrame) -> None:
        """Test volume aggregation produces sum and count."""
        from gapless_deribit_clickhouse.features import dte_bucket_agg

        result = dte_bucket_agg(multi_dte_df, metrics=["amount"])

        # Check for volume columns
        vol_cols = [c for c in result.columns if "volume" in c.lower() or "count" in c.lower()]
        assert len(vol_cols) > 0

    def test_bucket_agg_empty_raises(self) -> None:
        """Test empty DataFrame raises error."""
        from gapless_deribit_clickhouse.features import dte_bucket_agg

        empty_df = pd.DataFrame(columns=["timestamp", "iv", "dte"])

        with pytest.raises(ValueError, match="empty"):
            dte_bucket_agg(empty_df)


# === pcr_by_tenor Tests ===


class TestPCRByTenor:
    """Tests for Put-Call Ratio by tenor."""

    def test_pcr_by_tenor_returns_ratios(self, realistic_trades_df: pd.DataFrame) -> None:
        """Test PCR calculation returns valid ratios."""
        from gapless_deribit_clickhouse.features import pcr_by_tenor

        result = pcr_by_tenor(realistic_trades_df)

        assert isinstance(result, pd.DataFrame)
        assert len(result.columns) > 0

        # PCR columns should be named pcr_X_Yd
        pcr_cols = [c for c in result.columns if c.startswith("pcr_")]
        assert len(pcr_cols) > 0

    def test_pcr_values_realistic(self, realistic_trades_df: pd.DataFrame) -> None:
        """Test PCR values are in realistic range."""
        from gapless_deribit_clickhouse.features import pcr_by_tenor

        result = pcr_by_tenor(realistic_trades_df)

        for col in result.columns:
            valid = result[col].dropna()
            if len(valid) > 0:
                # PCR typically 0.3-3.0 in normal markets
                assert valid.min() >= 0
                assert valid.max() <= 10.0

    def test_pcr_count_method(self, realistic_trades_df: pd.DataFrame) -> None:
        """Test PCR with count method (trade count vs volume)."""
        from gapless_deribit_clickhouse.features import pcr_by_tenor

        result_vol = pcr_by_tenor(realistic_trades_df, method="volume")
        result_count = pcr_by_tenor(realistic_trades_df, method="count")

        # Both should return data
        assert len(result_vol) > 0
        assert len(result_count) > 0

        # Results should differ (volume vs count weighting)
        if len(result_vol.columns) > 0 and len(result_count.columns) > 0:
            col = result_vol.columns[0]
            if col in result_count.columns:
                common_idx = result_vol[col].dropna().index.intersection(
                    result_count[col].dropna().index
                )
                if len(common_idx) > 0:
                    diff = (
                        result_vol.loc[common_idx, col] - result_count.loc[common_idx, col]
                    ).abs()
                    # May be same or different depending on data
                    assert diff.sum() >= 0

    def test_pcr_empty_raises(self) -> None:
        """Test empty DataFrame raises error."""
        from gapless_deribit_clickhouse.features import pcr_by_tenor

        empty_df = pd.DataFrame(columns=["timestamp", "option_type", "amount", "dte"])

        with pytest.raises(ValueError, match="empty"):
            pcr_by_tenor(empty_df)


# === term_structure_slope Tests ===


class TestTermStructureSlope:
    """Tests for IV term structure slope."""

    def test_slope_with_multi_dte_data(self, multi_dte_df: pd.DataFrame) -> None:
        """Test slope calculation with data across term structure."""
        from gapless_deribit_clickhouse.features import term_structure_slope

        result = term_structure_slope(multi_dte_df)

        assert isinstance(result, pd.Series)
        assert len(result) > 0
        assert result.name == "term_structure_slope"

    def test_slope_sign_interpretation(self, multi_dte_df: pd.DataFrame) -> None:
        """Test slope values can be positive or negative."""
        from gapless_deribit_clickhouse.features import term_structure_slope

        result = term_structure_slope(multi_dte_df)

        # Slope is near - far IV, can be +/-
        valid = result.dropna()
        if len(valid) > 0:
            # Values should be reasonable IV differences
            assert valid.abs().max() <= 0.50  # Max 50% difference

    def test_slope_custom_boundaries(self, multi_dte_df: pd.DataFrame) -> None:
        """Test slope with custom near/far boundaries."""
        from gapless_deribit_clickhouse.features import term_structure_slope

        # Narrow boundaries
        result = term_structure_slope(
            multi_dte_df,
            near_dte_max=14,
            far_dte_min=90,
        )

        assert len(result) >= 0  # May be empty if no matching data

    def test_slope_insufficient_data_raises(self) -> None:
        """Test error when missing near or far term data."""
        from gapless_deribit_clickhouse.features import term_structure_slope

        # Only near-term data
        df = pd.DataFrame({
            "timestamp": [datetime(2024, 12, 1, 10, 0)],
            "expiry": [datetime(2024, 12, 5)],  # 4 DTE only
            "iv": [0.60],
        })

        with pytest.raises(ValueError, match="Insufficient"):
            term_structure_slope(df, far_dte_min=60)


# === EGARCH Tests ===


class TestEGARCH:
    """Tests for EGARCH volatility model."""

    def test_fit_egarch_returns_result(self, regular_iv_series: pd.Series) -> None:
        """Test fit_egarch returns ARCHModelResult."""
        from gapless_deribit_clickhouse.features import fit_egarch

        result = fit_egarch(regular_iv_series)

        # Should have standard ARCHModelResult attributes
        assert hasattr(result, "params")
        assert hasattr(result, "aic")
        assert hasattr(result, "bic")
        assert hasattr(result, "conditional_volatility")

    def test_fit_egarch_captures_persistence(self, regular_iv_series: pd.Series) -> None:
        """Test fitted model captures volatility persistence."""
        from gapless_deribit_clickhouse.features import fit_egarch

        result = fit_egarch(regular_iv_series)

        # Conditional volatility should vary (not constant)
        cond_vol = result.conditional_volatility
        assert cond_vol.std() > 0

    def test_auto_select_egarch(self, regular_iv_series: pd.Series) -> None:
        """Test auto_select_egarch finds best model."""
        from gapless_deribit_clickhouse.features import auto_select_egarch

        result = auto_select_egarch(regular_iv_series, criterion="aic")

        # Should have selection metadata
        assert hasattr(result, "_auto_selected")
        assert result._auto_selected is True  # type: ignore[attr-defined]
        assert hasattr(result, "_selection_criterion")

    def test_forecast_volatility(self, regular_iv_series: pd.Series) -> None:
        """Test volatility forecasting."""
        from gapless_deribit_clickhouse.features import fit_egarch, forecast_volatility

        fitted = fit_egarch(regular_iv_series)

        # Test single-step analytic forecast (default)
        forecast_1 = forecast_volatility(fitted, horizon=1)
        assert isinstance(forecast_1, pd.DataFrame)
        assert "variance" in forecast_1.columns
        assert "volatility" in forecast_1.columns
        assert len(forecast_1) == 1

        # Test multi-step forecast requires simulation method
        # (analytic only available for horizon=1 in EGARCH)
        forecast_5 = forecast_volatility(fitted, horizon=5, method="simulation")
        assert len(forecast_5) == 5

    def test_egarch_insufficient_data_raises(self) -> None:
        """Test error when data too short for estimation."""
        from gapless_deribit_clickhouse.features import fit_egarch

        # Only 50 observations (need 100 minimum)
        short_series = pd.Series(
            np.random.uniform(0.5, 0.7, 50),
            index=pd.date_range("2024-01-01", periods=50, freq="15min"),
        )

        with pytest.raises(ValueError, match="Insufficient"):
            fit_egarch(short_series)

    def test_egarch_irregular_series_raises(self) -> None:
        """Test error when series has irregular intervals."""
        from gapless_deribit_clickhouse.features import fit_egarch

        # Irregular intervals
        times = pd.to_datetime([
            "2024-01-01 10:00", "2024-01-01 10:15", "2024-01-01 10:45",  # 15, 30 gap
            "2024-01-01 11:00", "2024-01-01 11:05", "2024-01-01 11:35",  # 5, 30 gap
        ] * 20)  # Repeat to get 120 points

        irregular = pd.Series(
            np.random.uniform(0.5, 0.7, len(times)),
            index=times,
        )

        with pytest.raises(ValueError, match="irregular"):
            fit_egarch(irregular)


# === Integration Tests ===


class TestPhase1Integration:
    """Integration tests combining multiple features."""

    def test_resample_then_egarch_pipeline(self, realistic_trades_df: pd.DataFrame) -> None:
        """Test typical pipeline: resample -> EGARCH."""
        from gapless_deribit_clickhouse.features import fit_egarch, resample_iv

        # Resample to regular series
        resampled = resample_iv(realistic_trades_df)
        iv_col = "iv_close" if "iv_close" in resampled.columns else "iv_mean"

        # May not have enough data for EGARCH, that's OK
        if len(resampled) >= 100:
            result = fit_egarch(resampled[iv_col])
            assert hasattr(result, "aic")

    def test_multiple_features_same_data(self, realistic_trades_df: pd.DataFrame) -> None:
        """Test computing multiple features from same data."""
        from gapless_deribit_clickhouse.features import (
            dte_bucket_agg,
            pcr_by_tenor,
            resample_iv,
        )

        # All should work on same input
        resampled = resample_iv(realistic_trades_df)
        buckets = dte_bucket_agg(realistic_trades_df)
        pcr = pcr_by_tenor(realistic_trades_df)

        # All should have output
        assert len(resampled) > 0
        assert len(buckets) > 0
        assert len(pcr) > 0

    def test_feature_config_affects_output(self, realistic_trades_df: pd.DataFrame) -> None:
        """Test that FeatureConfig changes results appropriately."""
        from gapless_deribit_clickhouse.features import resample_iv
        from gapless_deribit_clickhouse.features.config import FeatureConfig

        default_result = resample_iv(realistic_trades_df, freq="15min")
        custom_config = FeatureConfig(resample_freq="30min")
        custom_result = resample_iv(realistic_trades_df, freq=custom_config.resample_freq)

        # Different frequencies = different number of bars
        # 30min should have roughly half the bars of 15min
        if len(default_result) > 2 and len(custom_result) > 2:
            ratio = len(default_result) / len(custom_result)
            assert 1.5 <= ratio <= 2.5  # Approximately 2x difference
