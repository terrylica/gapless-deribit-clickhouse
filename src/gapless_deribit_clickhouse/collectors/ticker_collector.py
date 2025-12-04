"""
Deribit ticker collector for forward-only OI and Greeks snapshots.

Uses www.deribit.com API to poll current ticker data.
CRITICAL: Historical OI data is not available - must collect going forward.

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from gapless_deribit_clickhouse.clickhouse.connection import get_client
from gapless_deribit_clickhouse.exceptions import APIError, RateLimitError
from gapless_deribit_clickhouse.utils.instrument_parser import parse_instrument

logger = logging.getLogger(__name__)

# API configuration
API_BASE = "https://www.deribit.com/api/v2/public"
TICKER_ENDPOINT = f"{API_BASE}/ticker"
INSTRUMENTS_ENDPOINT = f"{API_BASE}/get_instruments"

# Request configuration
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3

# HTTP status codes
HTTP_OK = 200
HTTP_TOO_MANY_REQUESTS = 429

# Rate limiting (10 req/sec max)
RATE_LIMIT_DELAY_SECONDS = 0.1

# Polling interval for daemon mode
DEFAULT_POLL_INTERVAL_SECONDS = 300  # 5 minutes

# Progress logging interval
PROGRESS_LOG_INTERVAL_SECONDS = 30


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
def _fetch_ticker(instrument_name: str) -> dict[str, Any]:
    """
    Fetch ticker data for a single instrument.

    Args:
        instrument_name: Full instrument name (e.g., "BTC-27DEC24-100000-C")

    Returns:
        API response result dict

    Raises:
        APIError: If API returns an error
        RateLimitError: If rate limit exceeded
    """
    params = {"instrument_name": instrument_name}

    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.get(TICKER_ENDPOINT, params=params)

    if response.status_code == HTTP_TOO_MANY_REQUESTS:
        raise RateLimitError("Deribit API rate limit exceeded")

    if response.status_code != HTTP_OK:
        raise APIError(f"Deribit API returned {response.status_code}: {response.text}")

    data = response.json()

    if "error" in data:
        raise APIError(f"Deribit API error: {data['error']}")

    return data.get("result", {})


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
def _fetch_instruments(currency: str) -> list[dict[str, Any]]:
    """
    Fetch all active option instruments for a currency.

    Args:
        currency: "BTC" or "ETH"

    Returns:
        List of instrument dicts

    Raises:
        APIError: If API returns an error
    """
    params = {
        "currency": currency,
        "kind": "option",
        "expired": "false",
    }

    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.get(INSTRUMENTS_ENDPOINT, params=params)

    if response.status_code != HTTP_OK:
        raise APIError(f"Deribit API returned {response.status_code}: {response.text}")

    data = response.json()

    if "error" in data:
        raise APIError(f"Deribit API error: {data['error']}")

    return data.get("result", [])


def _ticker_to_row(ticker: dict[str, Any], snapshot_time: datetime) -> dict[str, Any]:
    """
    Convert API ticker dict to database row.

    Parses instrument name to extract derived fields.
    """
    instrument_name = ticker["instrument_name"]
    parsed = parse_instrument(instrument_name)

    greeks = ticker.get("greeks", {})

    return {
        "instrument_name": instrument_name,
        "timestamp": snapshot_time,
        "open_interest": ticker.get("open_interest", 0),
        "delta": greeks.get("delta"),
        "gamma": greeks.get("gamma"),
        "vega": greeks.get("vega"),
        "theta": greeks.get("theta"),
        "mark_iv": ticker.get("mark_iv"),
        "mark_price": ticker.get("mark_price"),
        "index_price": ticker.get("index_price"),
        "underlying": parsed.underlying,
        "expiry": parsed.expiry,
        "strike": parsed.strike,
        "option_type": parsed.option_type,
    }


def collect_ticker_snapshot(
    currency: str = "BTC",
    insert_to_db: bool = True,
) -> pd.DataFrame:
    """
    Collect current ticker snapshots for all active options.

    Args:
        currency: "BTC" or "ETH"
        insert_to_db: If True, insert to ClickHouse

    Returns:
        DataFrame with ticker snapshots
    """
    snapshot_time = datetime.now()
    logger.info(f"Collecting {currency} options ticker snapshot at {snapshot_time}")

    # Get all active instruments
    instruments = _fetch_instruments(currency)
    logger.info(f"Found {len(instruments)} active {currency} options")

    rows: list[dict[str, Any]] = []
    last_log_time = datetime.now()

    for i, instrument in enumerate(instruments):
        instrument_name = instrument["instrument_name"]

        try:
            ticker = _fetch_ticker(instrument_name)
            row = _ticker_to_row(ticker, snapshot_time)
            rows.append(row)
        except (APIError, RateLimitError) as e:
            logger.warning(f"Failed to fetch ticker for {instrument_name}: {e}")
            continue

        # Rate limiting
        time.sleep(RATE_LIMIT_DELAY_SECONDS)

        # Progress logging
        if (datetime.now() - last_log_time).seconds >= PROGRESS_LOG_INTERVAL_SECONDS:
            logger.info(f"Collected {len(rows)}/{len(instruments)} tickers...")
            last_log_time = datetime.now()

    logger.info(f"Collected {len(rows)} ticker snapshots")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    if insert_to_db:
        _insert_ticker_snapshots(df)

    return df


def _insert_ticker_snapshots(df: pd.DataFrame) -> None:
    """Insert ticker snapshots DataFrame to ClickHouse."""
    if df.empty:
        return

    client = get_client()

    client.insert(
        "deribit_options.ticker_snapshots",
        df.to_dict("records"),
        column_names=list(df.columns),
    )

    logger.info(f"Inserted {len(df)} ticker snapshots to ClickHouse")


def run_daemon(
    currency: str = "BTC",
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> None:
    """
    Run continuous ticker collection in daemon mode.

    Collects snapshots at regular intervals until interrupted.

    Args:
        currency: "BTC" or "ETH"
        poll_interval_seconds: Seconds between snapshots
    """
    logger.info(f"Starting ticker daemon for {currency} (interval: {poll_interval_seconds}s)")

    while True:
        try:
            collect_ticker_snapshot(currency=currency, insert_to_db=True)
        except Exception as e:
            logger.error(f"Error collecting ticker snapshot: {e}")

        logger.info(f"Sleeping {poll_interval_seconds}s until next collection...")
        time.sleep(poll_interval_seconds)
