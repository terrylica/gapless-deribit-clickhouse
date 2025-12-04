"""
Deribit trades collector for historical backfill.

Uses history.deribit.com API to fetch historical trade data since 2018.
Implements cursor-based pagination with end_timestamp.

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from gapless_deribit_clickhouse.clickhouse.connection import get_client
from gapless_deribit_clickhouse.exceptions import APIError
from gapless_deribit_clickhouse.utils.instrument_parser import parse_instrument

logger = logging.getLogger(__name__)

# API configuration
HISTORY_API_BASE = "https://history.deribit.com/api/v2/public"
TRADES_ENDPOINT = f"{HISTORY_API_BASE}/get_last_trades_by_currency_and_time"

# Request configuration
DEFAULT_COUNT = 1000  # Max trades per request
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3

# HTTP status codes
HTTP_OK = 200

# Progress logging interval
PROGRESS_LOG_INTERVAL_SECONDS = 30


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
def _fetch_trades_page(
    currency: str,
    kind: str,
    start_timestamp: int,
    end_timestamp: int,
    count: int = DEFAULT_COUNT,
) -> dict[str, Any]:
    """
    Fetch a single page of trades from Deribit history API.

    Args:
        currency: "BTC" or "ETH"
        kind: "option" for options trades
        start_timestamp: Start timestamp in milliseconds
        end_timestamp: End timestamp in milliseconds
        count: Number of trades to fetch (max 1000)

    Returns:
        API response dict

    Raises:
        APIError: If API returns an error
    """
    params = {
        "currency": currency,
        "kind": kind,
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "count": count,
        "sorting": "desc",  # Most recent first
    }

    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.get(TRADES_ENDPOINT, params=params)

    if response.status_code != HTTP_OK:
        raise APIError(f"Deribit API returned {response.status_code}: {response.text}")

    data = response.json()

    if "error" in data:
        raise APIError(f"Deribit API error: {data['error']}")

    return data.get("result", {})


def _trade_to_row(trade: dict[str, Any]) -> dict[str, Any]:
    """
    Convert API trade dict to database row.

    Parses instrument name to extract derived fields.
    """
    instrument_name = trade["instrument_name"]
    parsed = parse_instrument(instrument_name)

    return {
        "trade_id": trade["trade_id"],
        "instrument_name": instrument_name,
        "timestamp": datetime.fromtimestamp(trade["timestamp"] / 1000),
        "price": trade["price"],
        "amount": trade["amount"],
        "direction": trade["direction"],
        "iv": trade.get("iv"),
        "index_price": trade.get("index_price"),
        "underlying": parsed.underlying,
        "expiry": parsed.expiry,
        "strike": parsed.strike,
        "option_type": parsed.option_type,
    }


def collect_trades(
    currency: str = "BTC",
    start_date: str | None = None,
    end_date: str | None = None,
    insert_to_db: bool = True,
) -> pd.DataFrame:
    """
    Collect historical options trades from Deribit.

    Args:
        currency: "BTC" or "ETH"
        start_date: Start date string (e.g., "2024-01-01")
        end_date: End date string (defaults to now)
        insert_to_db: If True, insert to ClickHouse

    Returns:
        DataFrame with collected trades
    """
    # Convert dates to timestamps
    if start_date:
        start_ts = int(pd.to_datetime(start_date).timestamp() * 1000)
    else:
        # Default to 2018-01-01 (Deribit options launch)
        start_ts = int(pd.to_datetime("2018-01-01").timestamp() * 1000)

    if end_date:
        end_ts = int(pd.to_datetime(end_date).timestamp() * 1000)
    else:
        end_ts = int(datetime.now().timestamp() * 1000)

    logger.info(f"Collecting {currency} options trades from {start_date or '2018-01-01'} to {end_date or 'now'}")

    all_trades: list[dict[str, Any]] = []
    current_end_ts = end_ts
    last_log_time = datetime.now()

    while current_end_ts > start_ts:
        result = _fetch_trades_page(
            currency=currency,
            kind="option",
            start_timestamp=start_ts,
            end_timestamp=current_end_ts,
        )

        trades = result.get("trades", [])
        if not trades:
            break

        # Convert to rows
        rows = [_trade_to_row(trade) for trade in trades]
        all_trades.extend(rows)

        # Update cursor for next page
        oldest_timestamp = min(trade["timestamp"] for trade in trades)
        current_end_ts = oldest_timestamp - 1

        # Progress logging
        if (datetime.now() - last_log_time).seconds >= PROGRESS_LOG_INTERVAL_SECONDS:
            logger.info(f"Collected {len(all_trades)} trades so far...")
            last_log_time = datetime.now()

    logger.info(f"Collected {len(all_trades)} total trades")

    if not all_trades:
        return pd.DataFrame()

    df = pd.DataFrame(all_trades)

    if insert_to_db:
        _insert_trades(df)

    return df


def _insert_trades(df: pd.DataFrame) -> None:
    """Insert trades DataFrame to ClickHouse."""
    if df.empty:
        return

    client = get_client()

    # Convert to format expected by ClickHouse
    # Note: clickhouse-connect handles the conversion
    client.insert(
        "deribit_options.trades",
        df.to_dict("records"),
        column_names=list(df.columns),
    )

    logger.info(f"Inserted {len(df)} trades to ClickHouse")
