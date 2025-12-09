"""
Deribit trades collector for historical backfill.

Uses history.deribit.com API to fetch historical trade data since 2018.
Implements cursor-based pagination with end_timestamp.

Features:
- Idempotent inserts via deduplication tokens
- Resumable backfills via checkpoint files
- Progress tracking with batch metrics

ADR: 2025-12-08-clickhouse-naming-convention
ADR: 2025-12-08-clickhouse-data-pipeline-architecture (idempotency)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
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

# Checkpoint configuration
DEFAULT_CHECKPOINT_DIR = Path("tmp/checkpoints")
BATCH_SIZE_FOR_INSERT = 10000  # Insert every N trades


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


def _generate_deduplication_token(currency: str, start_ts: int, end_ts: int, batch: int) -> str:
    """
    Generate unique deduplication token for ClickHouse insert.

    Token is based on currency, time range, and batch number.
    ClickHouse will reject duplicate inserts with same token.
    """
    token_input = f"{currency}:{start_ts}:{end_ts}:{batch}"
    return hashlib.sha256(token_input.encode()).hexdigest()[:32]


def _get_checkpoint_path(currency: str, start_ts: int, end_ts: int) -> Path:
    """Get checkpoint file path for a backfill job."""
    checkpoint_id = f"{currency}_{start_ts}_{end_ts}"
    return DEFAULT_CHECKPOINT_DIR / f"{checkpoint_id}.json"


def _load_checkpoint(checkpoint_path: Path) -> dict[str, Any] | None:
    """Load checkpoint from file if exists."""
    if not checkpoint_path.exists():
        return None
    return json.loads(checkpoint_path.read_text())


def _save_checkpoint(checkpoint_path: Path, checkpoint: dict[str, Any]) -> None:
    """Save checkpoint to file."""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2))


def _clear_checkpoint(checkpoint_path: Path) -> None:
    """Remove checkpoint file after successful completion."""
    if checkpoint_path.exists():
        checkpoint_path.unlink()


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
    resume: bool = True,
) -> pd.DataFrame:
    """
    Collect historical options trades from Deribit.

    Supports resumable backfills via checkpoint files. If a backfill is
    interrupted, calling with the same parameters will resume from the
    last checkpoint.

    Args:
        currency: "BTC" or "ETH"
        start_date: Start date string (e.g., "2024-01-01")
        end_date: End date string (defaults to now)
        insert_to_db: If True, insert to ClickHouse
        resume: If True, resume from checkpoint if available

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

    # Checkpoint management
    checkpoint_path = _get_checkpoint_path(currency, start_ts, end_ts)
    checkpoint = _load_checkpoint(checkpoint_path) if resume else None

    if checkpoint:
        current_end_ts = checkpoint["last_end_ts"]
        batch_number = checkpoint["batch_number"]
        total_collected = checkpoint["total_collected"]
        logger.info(
            f"Resuming from checkpoint: batch {batch_number}, {total_collected} trades collected"
        )
    else:
        current_end_ts = end_ts
        batch_number = 0
        total_collected = 0

    start_label = start_date or "2018-01-01"
    end_label = end_date or "now"
    logger.info(f"Collecting {currency} options trades from {start_label} to {end_label}")

    all_trades: list[dict[str, Any]] = []
    batch_trades: list[dict[str, Any]] = []
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
        batch_trades.extend(rows)

        # Update cursor for next page
        oldest_timestamp = min(trade["timestamp"] for trade in trades)
        current_end_ts = oldest_timestamp - 1

        # Insert batch and checkpoint when threshold reached
        if insert_to_db and len(batch_trades) >= BATCH_SIZE_FOR_INSERT:
            batch_number += 1
            _insert_trades_with_dedup(
                pd.DataFrame(batch_trades),
                currency,
                start_ts,
                end_ts,
                batch_number,
            )
            total_collected += len(batch_trades)
            batch_trades = []

            # Save checkpoint after successful insert
            _save_checkpoint(checkpoint_path, {
                "last_end_ts": current_end_ts,
                "batch_number": batch_number,
                "total_collected": total_collected,
                "updated_at": datetime.now().isoformat(),
            })

        # Progress logging
        if (datetime.now() - last_log_time).seconds >= PROGRESS_LOG_INTERVAL_SECONDS:
            logger.info(f"Collected {len(all_trades)} trades so far (batch {batch_number})...")
            last_log_time = datetime.now()

    # Insert remaining trades
    if insert_to_db and batch_trades:
        batch_number += 1
        _insert_trades_with_dedup(
            pd.DataFrame(batch_trades),
            currency,
            start_ts,
            end_ts,
            batch_number,
        )
        total_collected += len(batch_trades)

    # Clear checkpoint on successful completion
    _clear_checkpoint(checkpoint_path)

    logger.info(f"Collected {len(all_trades)} total trades in {batch_number} batches")

    if not all_trades:
        return pd.DataFrame()

    return pd.DataFrame(all_trades)


def _insert_trades(df: pd.DataFrame) -> None:
    """Insert trades DataFrame to ClickHouse (legacy, no deduplication)."""
    if df.empty:
        return

    client = get_client()

    # Convert to format expected by ClickHouse
    # Note: clickhouse-connect handles the conversion
    client.insert(
        "deribit.options_trades",
        df.to_dict("records"),
        column_names=list(df.columns),
    )

    logger.info(f"Inserted {len(df)} trades to ClickHouse")


def _insert_trades_with_dedup(
    df: pd.DataFrame,
    currency: str,
    start_ts: int,
    end_ts: int,
    batch: int,
) -> None:
    """
    Insert trades DataFrame to ClickHouse with deduplication token.

    Uses insert_deduplication_token setting to ensure idempotent inserts.
    If the same batch is inserted twice (e.g., after a retry), ClickHouse
    will reject the duplicate.
    """
    if df.empty:
        return

    client = get_client()

    # Generate unique token for this batch
    dedup_token = _generate_deduplication_token(currency, start_ts, end_ts, batch)

    # Insert with deduplication token
    # Note: Requires ReplicatedMergeTree or SharedMergeTree (ClickHouse Cloud)
    client.insert(
        "deribit.options_trades",
        df.to_dict("records"),
        column_names=list(df.columns),
        settings={"insert_deduplication_token": dedup_token},
    )

    logger.info(f"Inserted batch {batch}: {len(df)} trades (dedup_token: {dedup_token[:8]}...)")
