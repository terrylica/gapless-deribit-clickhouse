# ADR: 2025-12-10-deribit-options-alpha-features
"""
Hybrid spot price provider using ClickHouse dictGet() for efficiency.

Provides spot prices for options analysis using a hybrid approach:
1. Primary: Deribit index_price (canonical for settlement)
2. Fallback: Binance 15-min spot via gapless-crypto-clickhouse

Performance Optimization:
- dictGet() makes ~5 dictionary calls instead of scanning 10M rows
- COMPLEX_KEY_HASHED layout enables O(1) lookups
- coalesce() for hybrid logic computed server-side

Reference: https://clickhouse.com/blog/faster-queries-dictionaries-clickhouse

Prerequisites:
- Run schema/clickhouse/spot_prices_dict.sql to create the dictionary
- gapless-crypto-clickhouse ohlcv table populated with spot data
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from clickhouse_connect.driver import Client

# Mapping from Deribit underlying to Binance symbol
UNDERLYING_TO_SPOT_SYMBOL: dict[str, str] = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}

# SQL query using dictGet() for spot price lookup
SPOT_ENRICHED_QUERY = """
-- Enrich options data with hybrid spot price (dictGet + coalesce)
WITH base AS (
    {inner_query}
)
SELECT
    b.*,
    -- Dictionary lookup for Binance spot (faster than JOIN)
    dictGet(
        'spot_prices_dict',
        'close',
        tuple('{spot_symbol}', toStartOfFifteenMinutes(b.timestamp))
    ) AS binance_spot,
    -- Hybrid: prefer canonical index_price, fallback to Binance
    coalesce(
        b.index_price,
        dictGet(
            'spot_prices_dict',
            'close',
            tuple('{spot_symbol}', toStartOfFifteenMinutes(b.timestamp))
        )
    ) AS spot_price,
    -- Moneyness using hybrid spot
    b.strike / coalesce(
        b.index_price,
        dictGet(
            'spot_prices_dict',
            'close',
            tuple('{spot_symbol}', toStartOfFifteenMinutes(b.timestamp))
        )
    ) AS moneyness
FROM base b
"""

# Fallback query using LEFT JOIN (for when dictionary not available)
# Note: ClickHouse v24.4+ JOINs are 180x improved - production viable
SPOT_ENRICHED_JOIN_FALLBACK = """
-- Enrich options data with hybrid spot price (JOIN fallback)
WITH base AS (
    {inner_query}
)
SELECT
    b.*,
    s.close AS binance_spot,
    coalesce(b.index_price, s.close) AS spot_price,
    b.strike / coalesce(b.index_price, s.close) AS moneyness
FROM base b
LEFT JOIN ohlcv s ON
    s.symbol = '{spot_symbol}' AND
    s.timeframe = '15m' AND
    s.instrument_type = 'spot' AND
    s.timestamp = toStartOfFifteenMinutes(b.timestamp)
"""

# Direct query for options table with spot enrichment
DIRECT_SPOT_QUERY = """
-- Direct spot enrichment for options trades
SELECT
    t.timestamp,
    t.underlying,
    t.instrument_name,
    t.strike,
    t.expiry,
    t.option_type,
    t.iv,
    t.price,
    t.amount,
    t.direction,
    t.index_price,
    -- Dictionary lookup for Binance spot
    dictGet(
        'spot_prices_dict',
        'close',
        tuple('{spot_symbol}', toStartOfFifteenMinutes(t.timestamp))
    ) AS binance_spot,
    -- Hybrid spot price
    coalesce(
        t.index_price,
        dictGet(
            'spot_prices_dict',
            'close',
            tuple('{spot_symbol}', toStartOfFifteenMinutes(t.timestamp))
        )
    ) AS spot_price,
    -- Moneyness
    t.strike / coalesce(
        t.index_price,
        dictGet(
            'spot_prices_dict',
            'close',
            tuple('{spot_symbol}', toStartOfFifteenMinutes(t.timestamp))
        )
    ) AS moneyness
FROM {database}.{table} t
WHERE t.timestamp >= '{start}'
  AND t.timestamp < '{end}'
  AND t.underlying = '{underlying}'
ORDER BY t.timestamp
"""


def build_spot_enriched_query(
    inner_query: str | None = None,
    underlying: str = "BTC",
    start: str | None = None,
    end: str | None = None,
    database: str = "deribit",
    table: str = "options_trades",
    use_dict: bool = True,
) -> str:
    """
    Build ClickHouse query that enriches options with spot prices.

    The query adds three columns to the result:
    - binance_spot: Spot price from Binance via gapless-crypto-clickhouse
    - spot_price: Hybrid (index_price with Binance fallback)
    - moneyness: strike / spot_price

    Args:
        inner_query: Base query (from contract_selector). If None, query
                    options_trades directly using start/end/underlying.
        underlying: Options underlying ('BTC' or 'ETH')
        start: Start date (required if inner_query is None)
        end: End date (required if inner_query is None)
        database: ClickHouse database name
        table: ClickHouse table name
        use_dict: If True, use dictGet() (faster). If False, use JOIN fallback.

    Returns:
        SQL query with spot_price, moneyness columns added

    Raises:
        ValueError: If inner_query is None but start/end not provided

    Example:
        >>> from gapless_deribit_clickhouse.features.contract_selector import (
        ...     build_contract_selection_query
        ... )
        >>> base_query = build_contract_selection_query(strategy="front_atm")
        >>> enriched_query = build_spot_enriched_query(inner_query=base_query)
    """
    spot_symbol = UNDERLYING_TO_SPOT_SYMBOL.get(underlying, f"{underlying}USDT")

    if inner_query is not None:
        # Wrap existing query with spot enrichment
        template = SPOT_ENRICHED_QUERY if use_dict else SPOT_ENRICHED_JOIN_FALLBACK
        return template.format(
            inner_query=inner_query,
            spot_symbol=spot_symbol,
        )
    else:
        # Direct query against options table
        if start is None or end is None:
            raise ValueError("start and end are required when inner_query is None")

        return DIRECT_SPOT_QUERY.format(
            database=database,
            table=table,
            start=start,
            end=end,
            underlying=underlying,
            spot_symbol=spot_symbol,
        )


def enrich_with_spot(
    client: Client,
    inner_query: str | None = None,
    underlying: str = "BTC",
    start: str | None = None,
    end: str | None = None,
    database: str = "deribit",
    table: str = "options_trades",
    use_dict: bool = True,
) -> pd.DataFrame:
    """
    Execute spot-enriched query and return DataFrame.

    This function enriches options data with spot prices using the
    hybrid approach (Deribit index_price + Binance fallback).

    Args:
        client: ClickHouse client instance
        inner_query: Base query (from contract_selector)
        underlying: Options underlying ('BTC' or 'ETH')
        start: Start date (required if inner_query is None)
        end: End date (required if inner_query is None)
        database: ClickHouse database name
        table: ClickHouse table name
        use_dict: If True, use dictGet() (faster)

    Returns:
        DataFrame with spot_price and moneyness columns added

    Example:
        >>> from clickhouse_connect import get_client
        >>> from gapless_deribit_clickhouse.features.contract_selector import (
        ...     build_contract_selection_query
        ... )
        >>> client = get_client(host='localhost', port=8123)
        >>> base_query = build_contract_selection_query(
        ...     strategy="front_atm",
        ...     start="2024-01-01",
        ...     end="2024-03-01",
        ... )
        >>> df = enrich_with_spot(client, inner_query=base_query)
        >>> print(df[["timestamp", "spot_price", "moneyness"]].head())
    """
    import pandas as pd

    query = build_spot_enriched_query(
        inner_query=inner_query,
        underlying=underlying,
        start=start,
        end=end,
        database=database,
        table=table,
        use_dict=use_dict,
    )

    result = client.query(query)

    df = pd.DataFrame(
        result.result_rows,
        columns=result.column_names,
    )

    return df


def check_spot_dictionary_exists(client: Client) -> bool:
    """
    Check if the spot_prices_dict dictionary exists in ClickHouse.

    Args:
        client: ClickHouse client instance

    Returns:
        True if dictionary exists, False otherwise
    """
    query = """
    SELECT count() > 0
    FROM system.dictionaries
    WHERE name = 'spot_prices_dict'
    """
    result = client.query(query)
    return bool(result.result_rows[0][0])


def get_spot_coverage(
    client: Client,
    underlying: str = "BTC",
    start: str = "2024-01-01",
    end: str = "2024-12-31",
) -> dict[str, float]:
    """
    Get spot price coverage statistics.

    Returns coverage rates for index_price vs Binance fallback.

    Args:
        client: ClickHouse client instance
        underlying: Underlying asset
        start: Start date
        end: End date

    Returns:
        Dict with coverage statistics:
        - index_price_rate: Fraction of rows with index_price
        - binance_fallback_rate: Fraction of rows using Binance fallback
        - total_coverage: Fraction of rows with any spot price
    """
    spot_symbol = UNDERLYING_TO_SPOT_SYMBOL.get(underlying, f"{underlying}USDT")

    query = f"""
    SELECT
        countIf(index_price IS NOT NULL AND index_price > 0) / count() AS index_rate,
        countIf(
            (index_price IS NULL OR index_price = 0)
            AND dictGet('spot_prices_dict', 'close',
                       tuple('{spot_symbol}', toStartOfFifteenMinutes(timestamp))) > 0
        ) / count() AS fallback_rate,
        countIf(
            coalesce(index_price,
                     dictGet('spot_prices_dict', 'close',
                            tuple('{spot_symbol}', toStartOfFifteenMinutes(timestamp)))) > 0
        ) / count() AS total_rate
    FROM deribit.options_trades
    WHERE timestamp >= '{start}'
      AND timestamp < '{end}'
      AND underlying = '{underlying}'
    """

    result = client.query(query)
    row = result.result_rows[0]

    return {
        "index_price_rate": float(row[0]),
        "binance_fallback_rate": float(row[1]),
        "total_coverage": float(row[2]),
    }
