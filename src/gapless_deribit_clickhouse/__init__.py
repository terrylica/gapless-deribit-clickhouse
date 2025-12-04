"""
gapless-deribit-clickhouse: Deribit options data pipeline with ClickHouse storage.

This package provides:
- Historical options trade data (backfillable from 2018)
- Point-in-time OI and Greeks snapshots (forward-only)

Quick Start:
    import gapless_deribit_clickhouse as gdch

    # Fetch historical trades
    df = gdch.fetch_trades(underlying="BTC", start="2024-01-01")

    # Fetch ticker snapshots (OI + Greeks)
    df = gdch.fetch_ticker_snapshots(underlying="BTC", limit=1000)

    # Get active instruments
    instruments = gdch.get_active_instruments(underlying="BTC")

IMPORTANT: Open Interest cannot be reconstructed from trades.
The ticker_snapshots table is forward-only (no historical backfill).

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
"""

from gapless_deribit_clickhouse.api import (
    fetch_ticker_snapshots,
    fetch_trades,
    get_active_instruments,
)
from gapless_deribit_clickhouse.collectors import (
    collect_ticker_snapshot,
    collect_trades,
    run_daemon,
)
from gapless_deribit_clickhouse.exceptions import (
    APIError,
    ConfigurationError,
    ConnectionError,
    CredentialError,
    GaplessDeribitError,
    InstrumentParseError,
    QueryError,
    RateLimitError,
    SchemaError,
)
from gapless_deribit_clickhouse.probe import describe, get_capabilities, get_data_sources
from gapless_deribit_clickhouse.utils import parse_instrument

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Public API
    "fetch_trades",
    "fetch_ticker_snapshots",
    "get_active_instruments",
    # Collectors
    "collect_trades",
    "collect_ticker_snapshot",
    "run_daemon",
    # Utilities
    "parse_instrument",
    # Probe (AI discoverability)
    "describe",
    "get_capabilities",
    "get_data_sources",
    # Exceptions
    "GaplessDeribitError",
    "ConfigurationError",
    "CredentialError",
    "APIError",
    "RateLimitError",
    "ConnectionError",
    "QueryError",
    "SchemaError",
    "InstrumentParseError",
]
