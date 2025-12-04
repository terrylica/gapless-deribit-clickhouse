"""
Public API for gapless-deribit-clickhouse.

This module provides the main programmatic interface for:
- Deribit options trade data (historical from 2018)
- Deribit options ticker snapshots (OI + Greeks, forward-only)

Usage:
    import gapless_deribit_clickhouse as gdch

    # Fetch historical trades
    df = gdch.fetch_trades(
        underlying="BTC",
        start="2024-01-01",
        end="2024-01-31",
    )

    # Fetch ticker snapshots (OI + Greeks)
    df = gdch.fetch_ticker_snapshots(
        underlying="BTC",
        start="2024-12-01",
    )

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
"""

from __future__ import annotations

import pandas as pd

from gapless_deribit_clickhouse.clickhouse.connection import get_client
from gapless_deribit_clickhouse.exceptions import QueryError


def _normalize_timestamp(ts_str: str, is_end: bool = False) -> str:
    """
    Normalize timestamp string for inclusive date range queries.

    Expands date-only strings to include the full day:
    - Start dates: midnight of that day
    - End dates: midnight of the NEXT day (for exclusive < comparison)

    Args:
        ts_str: Timestamp string (various formats)
        is_end: If True, expand date-only to next day start for < comparison

    Returns:
        Formatted timestamp string with millisecond precision
    """
    ts = pd.to_datetime(ts_str)

    # Detect date-only input
    is_date_only = (
        ts.hour == 0
        and ts.minute == 0
        and ts.second == 0
        and ts.microsecond == 0
        and "T" not in str(ts_str)
        and ":" not in str(ts_str)
    )

    if is_date_only and is_end:
        ts = ts + pd.Timedelta(days=1)

    return ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def fetch_trades(
    underlying: str | None = None,
    start: str | None = None,
    end: str | None = None,
    option_type: str | None = None,
    expiry: str | None = None,
    strike: float | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """
    Fetch historical options trades from ClickHouse.

    Args:
        underlying: Filter by underlying asset ("BTC" or "ETH")
        start: Start date/timestamp (inclusive)
        end: End date/timestamp (inclusive)
        option_type: Filter by option type ("C" or "P")
        expiry: Filter by expiration date (YYYY-MM-DD)
        strike: Filter by strike price
        limit: Maximum rows to return

    Returns:
        DataFrame with trade data

    Raises:
        QueryError: If query fails
    """
    if start is None and end is None and limit is None:
        raise QueryError(
            "Must specify at least one of: start, end, or limit. "
            "Examples:\n"
            "  fetch_trades(limit=1000)\n"
            "  fetch_trades(start='2024-01-01')\n"
            "  fetch_trades(start='2024-01-01', end='2024-01-31')"
        )

    conditions: list[str] = []
    params: dict[str, str | float | int] = {}

    if underlying:
        conditions.append("underlying = {underlying:String}")
        params["underlying"] = underlying

    if start:
        conditions.append("timestamp >= {start:DateTime64(3)}")
        params["start"] = _normalize_timestamp(start, is_end=False)

    if end:
        conditions.append("timestamp < {end:DateTime64(3)}")
        params["end"] = _normalize_timestamp(end, is_end=True)

    if option_type:
        conditions.append("option_type = {option_type:String}")
        params["option_type"] = option_type

    if expiry:
        conditions.append("expiry = {expiry:Date}")
        params["expiry"] = expiry

    if strike:
        conditions.append("strike = {strike:Float64}")
        params["strike"] = strike

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    limit_clause = f"LIMIT {limit}" if limit else ""

    query = f"""
        SELECT *
        FROM deribit_options.trades
        WHERE {where_clause}
        ORDER BY timestamp DESC
        {limit_clause}
    """

    client = get_client()

    try:
        result = client.query(query, parameters=params)
        return result.result_set_as_dataframe()
    except Exception as e:
        raise QueryError(f"Failed to fetch trades: {e}") from e


def fetch_ticker_snapshots(
    underlying: str | None = None,
    start: str | None = None,
    end: str | None = None,
    option_type: str | None = None,
    expiry: str | None = None,
    strike: float | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """
    Fetch ticker snapshots (OI + Greeks) from ClickHouse.

    Args:
        underlying: Filter by underlying asset ("BTC" or "ETH")
        start: Start date/timestamp (inclusive)
        end: End date/timestamp (inclusive)
        option_type: Filter by option type ("C" or "P")
        expiry: Filter by expiration date (YYYY-MM-DD)
        strike: Filter by strike price
        limit: Maximum rows to return

    Returns:
        DataFrame with ticker snapshot data

    Raises:
        QueryError: If query fails
    """
    if start is None and end is None and limit is None:
        raise QueryError(
            "Must specify at least one of: start, end, or limit. "
            "Examples:\n"
            "  fetch_ticker_snapshots(limit=1000)\n"
            "  fetch_ticker_snapshots(start='2024-12-01')"
        )

    conditions: list[str] = []
    params: dict[str, str | float | int] = {}

    if underlying:
        conditions.append("underlying = {underlying:String}")
        params["underlying"] = underlying

    if start:
        conditions.append("timestamp >= {start:DateTime64(3)}")
        params["start"] = _normalize_timestamp(start, is_end=False)

    if end:
        conditions.append("timestamp < {end:DateTime64(3)}")
        params["end"] = _normalize_timestamp(end, is_end=True)

    if option_type:
        conditions.append("option_type = {option_type:String}")
        params["option_type"] = option_type

    if expiry:
        conditions.append("expiry = {expiry:Date}")
        params["expiry"] = expiry

    if strike:
        conditions.append("strike = {strike:Float64}")
        params["strike"] = strike

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    limit_clause = f"LIMIT {limit}" if limit else ""

    query = f"""
        SELECT *
        FROM deribit_options.ticker_snapshots
        WHERE {where_clause}
        ORDER BY timestamp DESC
        {limit_clause}
    """

    client = get_client()

    try:
        result = client.query(query, parameters=params)
        return result.result_set_as_dataframe()
    except Exception as e:
        raise QueryError(f"Failed to fetch ticker snapshots: {e}") from e


def get_active_instruments(underlying: str = "BTC") -> list[str]:
    """
    Get list of currently active option instruments.

    Queries the most recent ticker snapshot to find active instruments.

    Args:
        underlying: "BTC" or "ETH"

    Returns:
        List of instrument names
    """
    query = """
        SELECT DISTINCT instrument_name
        FROM deribit_options.ticker_snapshots
        WHERE underlying = {underlying:String}
          AND timestamp >= now() - INTERVAL 1 HOUR
        ORDER BY instrument_name
    """

    client = get_client()

    try:
        result = client.query(query, parameters={"underlying": underlying})
        return [row[0] for row in result.result_rows]
    except Exception as e:
        raise QueryError(f"Failed to get active instruments: {e}") from e
