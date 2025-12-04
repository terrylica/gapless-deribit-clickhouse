"""
AI discoverability module for gapless-deribit-clickhouse.

Provides structured information about available data for AI agents
to understand and utilize the package capabilities.

Usage:
    from gapless_deribit_clickhouse.probe import get_data_sources, get_capabilities

    # AI agent discovers available data
    sources = get_data_sources()
    caps = get_capabilities()

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DataSource:
    """Description of an available data source."""

    name: str
    description: str
    table: str
    key_fields: list[str]
    time_range: str
    update_frequency: str
    use_cases: list[str]


@dataclass(frozen=True)
class Capability:
    """Description of a package capability."""

    name: str
    function: str
    description: str
    example: str
    parameters: dict[str, str]


def get_data_sources() -> list[DataSource]:
    """
    Get available data sources for AI discovery.

    Returns:
        List of DataSource objects describing available data
    """
    return [
        DataSource(
            name="Deribit Options Trades",
            description="Historical trade data for BTC and ETH options on Deribit exchange",
            table="deribit_options.trades",
            key_fields=["trade_id", "instrument_name", "price", "amount", "iv"],
            time_range="2018-present (historical backfill available)",
            update_frequency="Continuous (can backfill)",
            use_cases=[
                "Options flow analysis",
                "Implied volatility tracking",
                "Large trade detection",
                "Historical price analysis",
            ],
        ),
        DataSource(
            name="Deribit Options Ticker Snapshots",
            description="Point-in-time Open Interest and Greeks for BTC and ETH options",
            table="deribit_options.ticker_snapshots",
            key_fields=["instrument_name", "open_interest", "delta", "gamma", "vega", "theta"],
            time_range="Forward-only (no historical backfill)",
            update_frequency="Every 5 minutes",
            use_cases=[
                "Gamma Exposure (GEX) calculation",
                "Options positioning analysis",
                "Greeks-based hedging",
                "Open Interest trends",
            ],
        ),
    ]


def get_capabilities() -> list[Capability]:
    """
    Get package capabilities for AI discovery.

    Returns:
        List of Capability objects describing available functions
    """
    return [
        Capability(
            name="Fetch Historical Trades",
            function="gapless_deribit_clickhouse.fetch_trades()",
            description="Query historical options trades with flexible filters",
            example='fetch_trades(underlying="BTC", start="2024-01-01", option_type="C")',
            parameters={
                "underlying": "BTC or ETH",
                "start": "Start date (inclusive)",
                "end": "End date (inclusive)",
                "option_type": "C (call) or P (put)",
                "expiry": "Filter by expiration date",
                "strike": "Filter by strike price",
                "limit": "Maximum rows",
            },
        ),
        Capability(
            name="Fetch Ticker Snapshots",
            function="gapless_deribit_clickhouse.fetch_ticker_snapshots()",
            description="Query Open Interest and Greeks snapshots",
            example='fetch_ticker_snapshots(underlying="BTC", start="2024-12-01")',
            parameters={
                "underlying": "BTC or ETH",
                "start": "Start date (inclusive)",
                "end": "End date (inclusive)",
                "option_type": "C (call) or P (put)",
                "expiry": "Filter by expiration date",
                "strike": "Filter by strike price",
                "limit": "Maximum rows",
            },
        ),
        Capability(
            name="Get Active Instruments",
            function="gapless_deribit_clickhouse.get_active_instruments()",
            description="List currently active option instruments",
            example='get_active_instruments(underlying="BTC")',
            parameters={
                "underlying": "BTC or ETH",
            },
        ),
    ]


def get_schema_info() -> dict[str, Any]:
    """
    Get schema information for AI understanding.

    Returns:
        Dict with schema details
    """
    return {
        "trades_fields": {
            "trade_id": "Unique trade identifier",
            "instrument_name": "Full instrument (e.g., BTC-27DEC24-100000-C)",
            "timestamp": "Trade time (ms precision)",
            "price": "Trade price in USD",
            "amount": "Contract amount",
            "direction": "buy or sell",
            "iv": "Implied volatility at trade",
            "index_price": "Underlying price at trade",
            "underlying": "BTC or ETH (derived)",
            "expiry": "Option expiration (derived)",
            "strike": "Strike price (derived)",
            "option_type": "C or P (derived)",
        },
        "ticker_fields": {
            "instrument_name": "Full instrument name",
            "timestamp": "Snapshot time (ms precision)",
            "open_interest": "Current OI in contracts",
            "delta": "Option delta (-1 to 1)",
            "gamma": "Option gamma",
            "vega": "Option vega",
            "theta": "Option theta",
            "mark_iv": "Mark implied volatility",
            "mark_price": "Mark price in USD",
            "index_price": "Underlying price",
            "underlying": "BTC or ETH (derived)",
            "expiry": "Option expiration (derived)",
            "strike": "Strike price (derived)",
            "option_type": "C or P (derived)",
        },
        "instrument_format": "{UNDERLYING}-{DDMMMYY}-{STRIKE}-{C|P}",
        "instrument_examples": [
            "BTC-27DEC24-100000-C",
            "ETH-28MAR25-5000-P",
        ],
    }


def describe() -> str:
    """
    Get human-readable description of the package.

    Returns:
        Formatted string describing the package
    """
    return """
gapless-deribit-clickhouse: Deribit Options Data Pipeline

Data Sources:
  - trades: Historical options trades (2018-present, backfillable)
  - ticker_snapshots: OI + Greeks (forward-only, collected every 5 min)

Key Capabilities:
  - fetch_trades(): Query historical trade data
  - fetch_ticker_snapshots(): Query OI and Greeks snapshots
  - get_active_instruments(): List active option contracts

Instrument Format: {UNDERLYING}-{DDMMMYY}-{STRIKE}-{C|P}
  Example: BTC-27DEC24-100000-C = BTC call, $100k strike, expires Dec 27 2024

IMPORTANT: Open Interest cannot be reconstructed from trades.
  Historical OI data is not available - ticker_snapshots is forward-only.

For GEX calculation, use ticker_snapshots for OI and delta per strike.
""".strip()
