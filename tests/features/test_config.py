# ADR: 2025-12-10-deribit-options-alpha-features
"""Tests for features.config module."""

import pytest

from gapless_deribit_clickhouse.features.config import (
    DEFAULT_CONFIG,
    CONSERVATIVE_CONFIG,
    HIGH_FREQUENCY_CONFIG,
    FeatureConfig,
)


class TestFeatureConfig:
    """Test FeatureConfig dataclass."""

    def test_default_config_values(self) -> None:
        """Test default configuration values match ADR specifications."""
        config = DEFAULT_CONFIG

        # EGARCH parameters (ADR-validated)
        assert config.egarch_p == 1
        assert config.egarch_o == 1
        assert config.egarch_q == 1
        assert config.egarch_dist == "t"
        assert config.min_observations == 100

        # Greeks parameters (matches Deribit internal models)
        assert config.risk_free_rate == 0.02

        # Contract selection
        assert config.atm_width == 0.05
        assert config.min_volume == 10.0

        # IV features
        assert config.iv_lookback_days == 90
        assert config.resample_freq == "15min"

    def test_dte_buckets_complete(self) -> None:
        """Test DTE buckets cover full range including LEAPS."""
        config = DEFAULT_CONFIG
        buckets = config.dte_buckets

        # Should have 6 buckets
        assert len(buckets) == 6

        # First bucket starts at 0
        assert buckets[0][0] == 0

        # Last bucket includes LEAPS (91-999)
        assert buckets[-1] == (91, 999)

        # No gaps between buckets
        for i in range(len(buckets) - 1):
            assert buckets[i][1] + 1 == buckets[i + 1][0]

    def test_pcr_dte_buckets_excludes_leaps(self) -> None:
        """Test PCR buckets exclude LEAPS (91+) as per ADR."""
        config = DEFAULT_CONFIG
        pcr_buckets = config.get_pcr_dte_buckets()

        # Should have 5 buckets (excludes LEAPS)
        assert len(pcr_buckets) == 5

        # No bucket should have max > 90
        for bucket in pcr_buckets:
            assert bucket[1] <= 90

    def test_moneyness_bucket_labels(self) -> None:
        """Test moneyness bucket labels are correct."""
        config = DEFAULT_CONFIG
        labels = config.get_moneyness_bucket_labels()

        assert labels == [
            "deep_otm_put",
            "otm_put",
            "atm",
            "otm_call",
            "deep_otm_call",
        ]

    def test_moneyness_thresholds(self) -> None:
        """Test moneyness thresholds are symmetric around 1.0."""
        config = DEFAULT_CONFIG
        t = config.moneyness_thresholds

        assert len(t) == 4
        # Check symmetry: 0.90, 0.95, 1.05, 1.10
        assert t[0] == 0.90
        assert t[1] == 0.95
        assert t[2] == 1.05
        assert t[3] == 1.10

    def test_config_is_frozen(self) -> None:
        """Test config is immutable (frozen dataclass)."""
        config = DEFAULT_CONFIG

        with pytest.raises(AttributeError):
            config.risk_free_rate = 0.05  # type: ignore[misc]

    def test_custom_config(self) -> None:
        """Test creating custom configuration."""
        custom = FeatureConfig(
            risk_free_rate=0.03,
            iv_lookback_days=60,
            min_volume=50.0,
        )

        assert custom.risk_free_rate == 0.03
        assert custom.iv_lookback_days == 60
        assert custom.min_volume == 50.0

        # Other values should be defaults
        assert custom.egarch_p == 1
        assert custom.atm_width == 0.05

    def test_preset_configs(self) -> None:
        """Test preset configurations have expected values."""
        # Conservative: more data, longer lookback
        assert CONSERVATIVE_CONFIG.min_observations == 200
        assert CONSERVATIVE_CONFIG.iv_lookback_days == 120
        assert CONSERVATIVE_CONFIG.min_volume == 50.0

        # High frequency: finer granularity, faster adaptation
        assert HIGH_FREQUENCY_CONFIG.resample_freq == "5min"
        assert HIGH_FREQUENCY_CONFIG.iv_lookback_days == 30
        assert HIGH_FREQUENCY_CONFIG.min_observations == 50
