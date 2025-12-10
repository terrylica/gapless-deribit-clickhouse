# ADR: 2025-12-10-deribit-options-alpha-features
"""Tests for features.greeks module."""

import numpy as np
import pandas as pd
import pytest

from gapless_deribit_clickhouse.features.config import DEFAULT_CONFIG
from gapless_deribit_clickhouse.features.greeks import (
    calculate_greeks,
    calculate_portfolio_greeks,
)
from gapless_deribit_clickhouse.features.moneyness import compute_moneyness_bucket


class TestCalculateGreeks:
    """Test Greeks calculation with py_vollib_vectorized."""

    @pytest.fixture
    def sample_options_df(self) -> pd.DataFrame:
        """Create sample options DataFrame for testing."""
        return pd.DataFrame({
            "timestamp": pd.date_range("2024-06-01", periods=4, freq="h"),
            "expiry": pd.Timestamp("2024-06-15"),  # ~14 DTE
            "strike": [95000.0, 100000.0, 105000.0, 100000.0],
            "option_type": ["C", "C", "C", "P"],
            "spot_price": [100000.0, 100000.0, 100000.0, 100000.0],
            "iv": [0.75, 0.80, 0.85, 0.82],
            "price": [8000.0, 5000.0, 3000.0, 4500.0],
            "amount": [1.0, 2.0, 0.5, 1.5],
        })

    def test_greeks_calculation_returns_expected_columns(
        self, sample_options_df: pd.DataFrame
    ) -> None:
        """Test that calculate_greeks adds expected columns."""
        result = calculate_greeks(sample_options_df)

        expected_cols = ["T", "bs_delta", "adjusted_delta", "gamma", "vega", "theta"]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_atm_call_delta_approximately_055(
        self, sample_options_df: pd.DataFrame
    ) -> None:
        """Test ATM call delta is approximately 0.55."""
        result = calculate_greeks(sample_options_df)

        # Row 1 is ATM call (strike == spot)
        atm_call_delta = result.loc[1, "bs_delta"]

        # ATM call delta should be between 0.5 and 0.6
        assert 0.5 <= atm_call_delta <= 0.6, f"ATM call delta: {atm_call_delta}"

    def test_atm_put_delta_approximately_negative_045(
        self, sample_options_df: pd.DataFrame
    ) -> None:
        """Test ATM put delta is approximately -0.45."""
        result = calculate_greeks(sample_options_df)

        # Row 3 is ATM put (strike == spot)
        atm_put_delta = result.loc[3, "bs_delta"]

        # ATM put delta should be between -0.5 and -0.4
        assert -0.5 <= atm_put_delta <= -0.4, f"ATM put delta: {atm_put_delta}"

    def test_gamma_is_positive(self, sample_options_df: pd.DataFrame) -> None:
        """Test all gamma values are positive."""
        result = calculate_greeks(sample_options_df)

        assert (result["gamma"] > 0).all(), "All gamma values should be positive"

    def test_vega_is_positive(self, sample_options_df: pd.DataFrame) -> None:
        """Test all vega values are positive."""
        result = calculate_greeks(sample_options_df)

        assert (result["vega"] > 0).all(), "All vega values should be positive"

    def test_theta_is_negative(self, sample_options_df: pd.DataFrame) -> None:
        """Test theta is negative (time decay)."""
        result = calculate_greeks(sample_options_df)

        assert (result["theta"] < 0).all(), "All theta values should be negative"

    def test_adjusted_delta_less_than_bs_delta_for_calls(
        self, sample_options_df: pd.DataFrame
    ) -> None:
        """Test premium-adjusted delta < BS delta for calls (inverse adjustment)."""
        result = calculate_greeks(sample_options_df)

        # For calls (rows 0, 1, 2), adjusted_delta should be less than bs_delta
        calls = result[result["option_type"] == "C"]
        assert (calls["adjusted_delta"] < calls["bs_delta"]).all()

    def test_handles_expired_options(self) -> None:
        """Test handles expired options gracefully (T <= 0)."""
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-06-20")],
            "expiry": [pd.Timestamp("2024-06-15")],  # Already expired
            "strike": [100000.0],
            "option_type": ["C"],
            "spot_price": [100000.0],
            "iv": [0.80],
            "price": [0.0],
            "amount": [1.0],
        })

        result = calculate_greeks(df)

        # Should have NaN for expired options
        assert np.isnan(result.loc[0, "bs_delta"])
        assert np.isnan(result.loc[0, "gamma"])

    def test_handles_zero_iv(self) -> None:
        """Test handles zero IV gracefully."""
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-06-01")],
            "expiry": [pd.Timestamp("2024-06-15")],
            "strike": [100000.0],
            "option_type": ["C"],
            "spot_price": [100000.0],
            "iv": [0.0],  # Zero IV
            "price": [0.0],
            "amount": [1.0],
        })

        result = calculate_greeks(df)

        # Should have NaN for zero IV
        assert np.isnan(result.loc[0, "bs_delta"])

    def test_missing_columns_raises_error(self) -> None:
        """Test missing required columns raises ValueError."""
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2024-06-01")],
            "strike": [100000.0],
            # Missing: expiry, option_type, spot_price, iv, price
        })

        with pytest.raises(ValueError, match="Missing required columns"):
            calculate_greeks(df)


class TestCalculatePortfolioGreeks:
    """Test portfolio-level Greeks aggregation."""

    @pytest.fixture
    def portfolio_df(self) -> pd.DataFrame:
        """Create sample portfolio with Greeks already calculated."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-06-01", periods=3, freq="h"),
            "expiry": pd.Timestamp("2024-06-15"),
            "strike": [95000.0, 100000.0, 105000.0],
            "option_type": ["C", "C", "P"],
            "spot_price": [100000.0, 100000.0, 100000.0],
            "iv": [0.75, 0.80, 0.85],
            "price": [8000.0, 5000.0, 3000.0],
            "amount": [1.0, -2.0, 1.0],  # Long, Short, Long
        })
        return calculate_greeks(df)

    def test_portfolio_greeks_returns_dict(self, portfolio_df: pd.DataFrame) -> None:
        """Test returns dict with expected keys."""
        result = calculate_portfolio_greeks(portfolio_df)

        expected_keys = [
            "net_delta",
            "net_gamma",
            "net_vega",
            "net_theta",
            "dollar_delta",
            "dollar_gamma",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_empty_portfolio_returns_zeros(self) -> None:
        """Test empty DataFrame returns zero Greeks."""
        df = pd.DataFrame(columns=["adjusted_delta", "gamma", "vega", "theta", "amount", "spot_price"])
        result = calculate_portfolio_greeks(df)

        assert result["net_delta"] == 0.0
        assert result["net_gamma"] == 0.0


class TestMoneynessHelpers:
    """Test moneyness utility functions."""

    def test_compute_moneyness_bucket_deep_otm_put(self) -> None:
        """Test deep OTM put bucket (moneyness < 0.90)."""
        assert compute_moneyness_bucket(0.85) == "deep_otm_put"

    def test_compute_moneyness_bucket_otm_put(self) -> None:
        """Test OTM put bucket (0.90 <= moneyness < 0.95)."""
        assert compute_moneyness_bucket(0.92) == "otm_put"

    def test_compute_moneyness_bucket_atm(self) -> None:
        """Test ATM bucket (0.95 <= moneyness < 1.05)."""
        assert compute_moneyness_bucket(1.0) == "atm"
        assert compute_moneyness_bucket(0.95) == "atm"
        assert compute_moneyness_bucket(1.04) == "atm"

    def test_compute_moneyness_bucket_otm_call(self) -> None:
        """Test OTM call bucket (1.05 <= moneyness < 1.10)."""
        assert compute_moneyness_bucket(1.07) == "otm_call"

    def test_compute_moneyness_bucket_deep_otm_call(self) -> None:
        """Test deep OTM call bucket (moneyness >= 1.10)."""
        assert compute_moneyness_bucket(1.15) == "deep_otm_call"
