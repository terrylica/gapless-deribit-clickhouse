"""
Deribit instrument name parser.

Parses instrument names like "BTC-27DEC24-100000-C" into components.

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from gapless_deribit_clickhouse.exceptions import InstrumentParseError

# Deribit instrument name format: {UNDERLYING}-{EXPIRY}-{STRIKE}-{TYPE}
# Examples: BTC-27DEC24-100000-C, ETH-28MAR25-5000-P
INSTRUMENT_PATTERN = re.compile(
    r"^(?P<underlying>BTC|ETH)-"
    r"(?P<expiry>\d{1,2}[A-Z]{3}\d{2})-"
    r"(?P<strike>\d+)-"
    r"(?P<option_type>[CP])$"
)

# Month abbreviations used by Deribit
MONTH_MAP = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


@dataclass(frozen=True)
class ParsedInstrument:
    """Parsed components of a Deribit instrument name."""

    instrument_name: str
    underlying: Literal["BTC", "ETH"]
    expiry: date
    strike: float
    option_type: Literal["C", "P"]

    @property
    def is_call(self) -> bool:
        """Check if this is a call option."""
        return self.option_type == "C"

    @property
    def is_put(self) -> bool:
        """Check if this is a put option."""
        return self.option_type == "P"


def parse_expiry(expiry_str: str) -> date:
    """
    Parse Deribit expiry string to date.

    Args:
        expiry_str: Expiry string like "27DEC24" or "7MAR25"

    Returns:
        date object

    Raises:
        InstrumentParseError: If expiry format is invalid
    """
    # Match pattern: 1-2 digit day, 3 letter month, 2 digit year
    match = re.match(r"^(\d{1,2})([A-Z]{3})(\d{2})$", expiry_str)
    if not match:
        raise InstrumentParseError(f"Invalid expiry format: {expiry_str}")

    day_str, month_str, year_str = match.groups()

    if month_str not in MONTH_MAP:
        raise InstrumentParseError(f"Invalid month: {month_str}")

    day = int(day_str)
    month = MONTH_MAP[month_str]
    # Deribit uses 2-digit years; assume 20xx for now
    year = 2000 + int(year_str)

    try:
        return date(year, month, day)
    except ValueError as e:
        raise InstrumentParseError(f"Invalid date {expiry_str}: {e}") from e


def parse_instrument(instrument_name: str) -> ParsedInstrument:
    """
    Parse a Deribit instrument name into components.

    Args:
        instrument_name: Full instrument name (e.g., "BTC-27DEC24-100000-C")

    Returns:
        ParsedInstrument with all components

    Raises:
        InstrumentParseError: If instrument name format is invalid

    Examples:
        >>> inst = parse_instrument("BTC-27DEC24-100000-C")
        >>> inst.underlying
        'BTC'
        >>> inst.strike
        100000.0
        >>> inst.option_type
        'C'
    """
    match = INSTRUMENT_PATTERN.match(instrument_name)
    if not match:
        raise InstrumentParseError(
            f"Invalid instrument name format: {instrument_name}. "
            "Expected format: {UNDERLYING}-{DDMMMYY}-{STRIKE}-{C|P}"
        )

    groups = match.groupdict()

    return ParsedInstrument(
        instrument_name=instrument_name,
        underlying=groups["underlying"],  # type: ignore[arg-type]
        expiry=parse_expiry(groups["expiry"]),
        strike=float(groups["strike"]),
        option_type=groups["option_type"],  # type: ignore[arg-type]
    )


def is_valid_instrument(instrument_name: str) -> bool:
    """
    Check if an instrument name is valid.

    Args:
        instrument_name: Instrument name to validate

    Returns:
        True if valid, False otherwise
    """
    return INSTRUMENT_PATTERN.match(instrument_name) is not None


def format_instrument(
    underlying: str,
    expiry: date,
    strike: float,
    option_type: str,
) -> str:
    """
    Format components into a Deribit instrument name.

    Args:
        underlying: "BTC" or "ETH"
        expiry: Option expiration date
        strike: Strike price
        option_type: "C" or "P"

    Returns:
        Formatted instrument name

    Raises:
        InstrumentParseError: If components are invalid
    """
    if underlying not in ("BTC", "ETH"):
        raise InstrumentParseError(f"Invalid underlying: {underlying}")

    if option_type not in ("C", "P"):
        raise InstrumentParseError(f"Invalid option type: {option_type}")

    # Format expiry as DDMMMYY
    month_abbr = list(MONTH_MAP.keys())[expiry.month - 1]
    expiry_str = f"{expiry.day}{month_abbr}{expiry.year % 100:02d}"

    # Strike should be integer for Deribit
    strike_str = str(int(strike))

    return f"{underlying}-{expiry_str}-{strike_str}-{option_type}"
