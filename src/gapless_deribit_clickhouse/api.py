"""
Public API for gapless-deribit-clickhouse.

This module provides the main programmatic interface for
Deribit options trade data (historical from 2018).

Usage:
    import gapless_deribit_clickhouse as gdch

    # Fetch historical trades
    df = gdch.fetch_trades(
        underlying="BTC",
        start="2024-01-01",
        end="2024-01-31",
    )

ADR: 2025-12-08-clickhouse-naming-convention
ADR: 2025-12-10-schema-optimization (FINAL clause for deduplication)
"""

from __future__ import annotations

import pandas as pd

from gapless_deribit_clickhouse.clickhouse.connection import get_client
from gapless_deribit_clickhouse.exceptions import QueryError


def _validate_fetch_params(
    start: str | None,
    end: str | None,
    limit: int | None,
) -> None:
    """
    Validate fetch parameters before database query.

    ADR: 2025-12-05-trades-only-architecture-pivot - fail-fast validation

    Raises:
        ValueError: If parameters are invalid
    """
    # Rule 1: At least one constraint required
    if start is None and end is None and limit is None:
        raise ValueError(
            "At least one constraint required: start, end, or limit. "
            "Examples:\n"
            "  fetch_trades(limit=1000)\n"
            "  fetch_trades(start='2024-01-01')\n"
            "  fetch_trades(start='2024-01-01', end='2024-01-31')"
        )

    # Rule 2: Empty strings are explicit errors
    if start == "":
        raise ValueError("start cannot be empty string; use None instead")
    if end == "":
        raise ValueError("end cannot be empty string; use None instead")

    # Rule 3: Date ordering (if both specified)
    if start and end and start > end:
        raise ValueError(f"start ({start}) must be <= end ({end})")

    # Rule 4: Negative limit
    if limit is not None and limit < 0:
        raise ValueError(f"limit must be non-negative, got {limit}")


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
    use_final: bool = True,
) -> pd.DataFrame:
    """
    Fetch historical options trades from ClickHouse.

    ADR: 2025-12-10-schema-optimization (FINAL clause for deduplication)

    Args:
        underlying: Filter by underlying asset ("BTC" or "ETH")
        start: Start date/timestamp (inclusive)
        end: End date/timestamp (inclusive)
        option_type: Filter by option type ("C" or "P")
        expiry: Filter by expiration date (YYYY-MM-DD)
        strike: Filter by strike price
        limit: Maximum rows to return
        use_final: If True (default), use FINAL to deduplicate results.
                  Set to False for faster queries when duplicates are acceptable.

    Returns:
        DataFrame with trade data

    Raises:
        ValueError: If parameters are invalid
        QueryError: If query fails
    """
    # ADR: 2025-12-05-trades-only-architecture-pivot - fail-fast validation
    _validate_fetch_params(start, end, limit)

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
    # ADR: 2025-12-10-schema-optimization
    # FINAL ensures deduplication with ReplacingMergeTree (trade_id uniqueness)
    final_clause = "FINAL" if use_final else ""

    query = f"""
        SELECT *
        FROM deribit.options_trades {final_clause}
        WHERE {where_clause}
        ORDER BY timestamp DESC
        {limit_clause}
    """

    client = get_client()

    try:
        return client.query_df(query, parameters=params)
    except Exception as e:
        raise QueryError(f"Failed to fetch trades: {e}") from e
