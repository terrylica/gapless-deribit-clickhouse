"""
gapless-deribit-clickhouse: Deribit options data pipeline with ClickHouse storage.

This package provides historical options trade data (backfillable from 2018).

Quick Start:
    import gapless_deribit_clickhouse as gdch

    # Fetch historical trades
    df = gdch.fetch_trades(underlying="BTC", start="2024-01-01")

    # Collect trades to ClickHouse
    gdch.collect_trades(underlying="BTC", start="2024-01-01")

ADR: 2025-12-05-trades-only-architecture-pivot
"""

from gapless_deribit_clickhouse.api import fetch_trades
from gapless_deribit_clickhouse.collectors import collect_trades
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

# ADR: 2025-12-05-trades-only-architecture-pivot - dynamic version with fallback
try:
    from importlib.metadata import version as _get_version

    __version__ = _get_version("gapless-deribit-clickhouse")
except Exception:
    __version__ = "0.1.0"  # Fallback for editable installs

__all__ = [
    # Version
    "__version__",
    # Public API
    "fetch_trades",
    # Collectors
    "collect_trades",
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
