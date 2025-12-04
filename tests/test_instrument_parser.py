"""
Unit tests for instrument parser.

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
"""

from datetime import date

import pytest

from gapless_deribit_clickhouse.exceptions import InstrumentParseError
from gapless_deribit_clickhouse.utils.instrument_parser import (
    format_instrument,
    is_valid_instrument,
    parse_expiry,
    parse_instrument,
)


class TestParseInstrument:
    """Tests for parse_instrument function."""

    def test_btc_call(self):
        """Parse BTC call option."""
        result = parse_instrument("BTC-27DEC24-100000-C")

        assert result.instrument_name == "BTC-27DEC24-100000-C"
        assert result.underlying == "BTC"
        assert result.expiry == date(2024, 12, 27)
        assert result.strike == 100000.0
        assert result.option_type == "C"
        assert result.is_call is True
        assert result.is_put is False

    def test_eth_put(self):
        """Parse ETH put option."""
        result = parse_instrument("ETH-28MAR25-5000-P")

        assert result.instrument_name == "ETH-28MAR25-5000-P"
        assert result.underlying == "ETH"
        assert result.expiry == date(2025, 3, 28)
        assert result.strike == 5000.0
        assert result.option_type == "P"
        assert result.is_call is False
        assert result.is_put is True

    def test_single_digit_day(self):
        """Parse instrument with single digit day."""
        result = parse_instrument("BTC-7MAR25-80000-C")

        assert result.expiry == date(2025, 3, 7)

    def test_invalid_format_raises(self):
        """Invalid format raises InstrumentParseError."""
        with pytest.raises(InstrumentParseError):
            parse_instrument("INVALID")

    def test_invalid_underlying_raises(self):
        """Invalid underlying raises InstrumentParseError."""
        with pytest.raises(InstrumentParseError):
            parse_instrument("SOL-27DEC24-100-C")

    def test_missing_option_type_raises(self):
        """Missing option type raises InstrumentParseError."""
        with pytest.raises(InstrumentParseError):
            parse_instrument("BTC-27DEC24-100000")


class TestParseExpiry:
    """Tests for parse_expiry function."""

    def test_standard_expiry(self):
        """Parse standard expiry format."""
        result = parse_expiry("27DEC24")
        assert result == date(2024, 12, 27)

    def test_single_digit_day(self):
        """Parse expiry with single digit day."""
        result = parse_expiry("7MAR25")
        assert result == date(2025, 3, 7)

    def test_all_months(self):
        """Parse expiry for all months."""
        months = [
            ("1JAN24", date(2024, 1, 1)),
            ("1FEB24", date(2024, 2, 1)),
            ("1MAR24", date(2024, 3, 1)),
            ("1APR24", date(2024, 4, 1)),
            ("1MAY24", date(2024, 5, 1)),
            ("1JUN24", date(2024, 6, 1)),
            ("1JUL24", date(2024, 7, 1)),
            ("1AUG24", date(2024, 8, 1)),
            ("1SEP24", date(2024, 9, 1)),
            ("1OCT24", date(2024, 10, 1)),
            ("1NOV24", date(2024, 11, 1)),
            ("1DEC24", date(2024, 12, 1)),
        ]
        for expiry_str, expected in months:
            assert parse_expiry(expiry_str) == expected

    def test_invalid_month_raises(self):
        """Invalid month raises InstrumentParseError."""
        with pytest.raises(InstrumentParseError):
            parse_expiry("27XXX24")

    def test_invalid_format_raises(self):
        """Invalid format raises InstrumentParseError."""
        with pytest.raises(InstrumentParseError):
            parse_expiry("invalid")


class TestIsValidInstrument:
    """Tests for is_valid_instrument function."""

    def test_valid_btc_call(self):
        """Valid BTC call returns True."""
        assert is_valid_instrument("BTC-27DEC24-100000-C") is True

    def test_valid_eth_put(self):
        """Valid ETH put returns True."""
        assert is_valid_instrument("ETH-28MAR25-5000-P") is True

    def test_invalid_returns_false(self):
        """Invalid instrument returns False."""
        assert is_valid_instrument("INVALID") is False
        assert is_valid_instrument("SOL-27DEC24-100-C") is False
        assert is_valid_instrument("") is False


class TestFormatInstrument:
    """Tests for format_instrument function."""

    def test_format_btc_call(self):
        """Format BTC call option."""
        result = format_instrument("BTC", date(2024, 12, 27), 100000, "C")
        assert result == "BTC-27DEC24-100000-C"

    def test_format_eth_put(self):
        """Format ETH put option."""
        result = format_instrument("ETH", date(2025, 3, 28), 5000, "P")
        assert result == "ETH-28MAR25-5000-P"

    def test_roundtrip(self):
        """Parse and format should roundtrip."""
        original = "BTC-27DEC24-100000-C"
        parsed = parse_instrument(original)
        formatted = format_instrument(
            parsed.underlying,
            parsed.expiry,
            parsed.strike,
            parsed.option_type,
        )
        assert formatted == original

    def test_invalid_underlying_raises(self):
        """Invalid underlying raises InstrumentParseError."""
        with pytest.raises(InstrumentParseError):
            format_instrument("SOL", date(2024, 12, 27), 100, "C")

    def test_invalid_option_type_raises(self):
        """Invalid option type raises InstrumentParseError."""
        with pytest.raises(InstrumentParseError):
            format_instrument("BTC", date(2024, 12, 27), 100000, "X")
