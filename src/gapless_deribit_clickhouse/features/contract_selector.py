# ADR: 2025-12-10-deribit-options-alpha-features
"""
Systematic contract selection using ClickHouse native queries.

This module provides contract selection strategies for options analysis:
- Front-month: Nearest expiry contracts per time bucket
- ATM filter: Contracts near spot price (configurable width)
- Liquidity filter: Contracts meeting minimum volume threshold

Performance Optimization:
- Uses argMin(tuple(*), dte) instead of ROW_NUMBER() window functions
- Aggregate functions have lower memory overhead in ClickHouse
- All filtering computed server-side before data transfer

Reference: https://medium.com/insiderengineering/clickhouse-query-optimization-argmax-vs-final
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import pandas as pd
    from clickhouse_connect.driver import Client

from gapless_deribit_clickhouse.features.config import DEFAULT_CONFIG, FeatureConfig

# Contract selection strategies
ContractStrategy = Literal["all", "front_month", "front_atm", "front_atm_liquid"]

# SQL query templates
# Note: Using argMin for front-month selection (more efficient than window functions)

FRONT_MONTH_QUERY = """
-- Front-month selection: nearest expiry per 15-min bucket
-- Uses argMin(tuple(*), dte) aggregate instead of ROW_NUMBER()
SELECT
    toStartOfFifteenMinutes(timestamp) AS ts,
    underlying,
    -- argMin returns the entire row (as tuple) with minimum DTE
    (argMin(
        tuple(
            timestamp,
            instrument_name,
            strike,
            expiry,
            option_type,
            iv,
            price,
            amount,
            direction,
            index_price
        ),
        dateDiff('day', toDate(timestamp), expiry)
    )).*
FROM {database}.{table}
WHERE timestamp >= '{start}'
  AND timestamp < '{end}'
  AND underlying = '{underlying}'
GROUP BY ts, underlying
ORDER BY ts
"""

ATM_FILTER_QUERY = """
-- ATM filter: contracts within configured ATM width of spot
WITH base AS (
    {inner_query}
)
SELECT *
FROM base
WHERE strike / index_price BETWEEN {lower} AND {upper}
"""

LIQUIDITY_FILTER_QUERY = """
-- Liquidity filter: contracts with daily volume above threshold
WITH base AS (
    {inner_query}
),
daily_volume AS (
    SELECT
        instrument_name,
        toDate(ts) AS trade_date,
        sum(amount) AS total_volume
    FROM base
    GROUP BY instrument_name, trade_date
)
SELECT b.*
FROM base b
INNER JOIN daily_volume dv
    ON b.instrument_name = dv.instrument_name
    AND toDate(b.ts) = dv.trade_date
WHERE dv.total_volume >= {min_volume}
"""

# Direct query for "all" strategy (no filtering)
ALL_CONTRACTS_QUERY = """
SELECT
    timestamp,
    underlying,
    instrument_name,
    strike,
    expiry,
    option_type,
    iv,
    price,
    amount,
    direction,
    index_price
FROM {database}.{table}
WHERE timestamp >= '{start}'
  AND timestamp < '{end}'
  AND underlying = '{underlying}'
ORDER BY timestamp
"""


def build_contract_selection_query(
    strategy: ContractStrategy = "front_atm_liquid",
    start: str = "2024-01-01",
    end: str = "2024-12-31",
    underlying: str = "BTC",
    database: str = "deribit",
    table: str = "options_trades",
    config: FeatureConfig = DEFAULT_CONFIG,
) -> str:
    """
    Build ClickHouse SQL query for contract selection.

    Strategies (in order of restrictiveness):
    - "all": No filtering, all contracts
    - "front_month": Nearest expiry per 15-min bucket
    - "front_atm": Front month + ATM (within +/- atm_width of spot)
    - "front_atm_liquid": Front month + ATM + min daily volume (DEFAULT)

    Args:
        strategy: Selection strategy
        start: Start date (inclusive), format 'YYYY-MM-DD'
        end: End date (exclusive), format 'YYYY-MM-DD'
        underlying: Underlying asset ('BTC' or 'ETH')
        database: ClickHouse database name
        table: ClickHouse table name
        config: FeatureConfig for ATM width and volume thresholds

    Returns:
        SQL query string to execute against ClickHouse

    Example:
        >>> query = build_contract_selection_query(
        ...     strategy="front_atm",
        ...     start="2024-01-01",
        ...     end="2024-06-01",
        ...     underlying="BTC",
        ... )
        >>> # Execute: client.query(query)
    """
    if strategy == "all":
        return ALL_CONTRACTS_QUERY.format(
            database=database,
            table=table,
            start=start,
            end=end,
            underlying=underlying,
        )

    # Start with front-month selection
    query = FRONT_MONTH_QUERY.format(
        database=database,
        table=table,
        start=start,
        end=end,
        underlying=underlying,
    )

    # Add ATM filter if requested
    if "atm" in strategy:
        lower = 1.0 - config.atm_width
        upper = 1.0 + config.atm_width
        query = ATM_FILTER_QUERY.format(
            inner_query=query,
            lower=lower,
            upper=upper,
        )

    # Add liquidity filter if requested
    if "liquid" in strategy:
        query = LIQUIDITY_FILTER_QUERY.format(
            inner_query=query,
            min_volume=config.min_volume,
        )

    return query


def select_contracts(
    client: Client,
    strategy: ContractStrategy = "front_atm_liquid",
    start: str = "2024-01-01",
    end: str = "2024-12-31",
    underlying: str = "BTC",
    database: str = "deribit",
    table: str = "options_trades",
    config: FeatureConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """
    Execute contract selection query and return DataFrame.

    This is the main entry point for contract selection. It builds the
    appropriate SQL query based on strategy and executes it against
    ClickHouse, returning a pandas DataFrame.

    Args:
        client: ClickHouse client instance
        strategy: Selection strategy (see build_contract_selection_query)
        start: Start date (inclusive)
        end: End date (exclusive)
        underlying: Underlying asset ('BTC' or 'ETH')
        database: ClickHouse database name
        table: ClickHouse table name
        config: FeatureConfig for thresholds

    Returns:
        DataFrame with selected contracts

    Raises:
        ClickHouseError: If query execution fails

    Example:
        >>> from clickhouse_connect import get_client
        >>> client = get_client(host='localhost', port=8123)
        >>> df = select_contracts(
        ...     client,
        ...     strategy="front_atm_liquid",
        ...     start="2024-01-01",
        ...     end="2024-03-01",
        ...     underlying="BTC",
        ... )
        >>> print(f"Selected {len(df)} contracts")
    """
    import pandas as pd

    query = build_contract_selection_query(
        strategy=strategy,
        start=start,
        end=end,
        underlying=underlying,
        database=database,
        table=table,
        config=config,
    )

    # Execute query and convert to DataFrame
    result = client.query(query)

    # Build DataFrame from result
    df = pd.DataFrame(
        result.result_rows,
        columns=result.column_names,
    )

    return df


def get_contract_stats(
    client: Client,
    start: str = "2024-01-01",
    end: str = "2024-12-31",
    underlying: str = "BTC",
    database: str = "deribit",
    table: str = "options_trades",
) -> dict[str, int]:
    """
    Get contract count statistics for each selection strategy.

    Useful for understanding data density and filter effects.

    Args:
        client: ClickHouse client instance
        start: Start date (inclusive)
        end: End date (exclusive)
        underlying: Underlying asset
        database: ClickHouse database name
        table: ClickHouse table name

    Returns:
        Dict mapping strategy name to contract count
    """
    stats: dict[str, int] = {}

    for strategy in ["all", "front_month", "front_atm", "front_atm_liquid"]:
        query = build_contract_selection_query(
            strategy=strategy,  # type: ignore[arg-type]
            start=start,
            end=end,
            underlying=underlying,
            database=database,
            table=table,
        )
        count_query = f"SELECT count() FROM ({query})"
        result = client.query(count_query)
        stats[strategy] = result.result_rows[0][0]

    return stats
