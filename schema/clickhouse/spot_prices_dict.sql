-- ADR: 2025-12-10-deribit-options-alpha-features
-- ClickHouse Dictionary for spot price lookups
--
-- Purpose: Enable efficient dictGet() lookups instead of JOINs for spot prices
-- Source: gapless-crypto-clickhouse ohlcv table (15-min spot bars)
--
-- Performance: ~5 dictionary calls vs scanning 10M rows with JOIN
-- Reference: https://clickhouse.com/blog/faster-queries-dictionaries-clickhouse
--
-- Note: Run this DDL once to create the dictionary. The dictionary
-- auto-refreshes based on LIFETIME settings (1-2 hours for spot prices).

CREATE DICTIONARY IF NOT EXISTS spot_prices_dict (
    -- LowCardinality for symbol: <10k unique symbols (BTC, ETH, etc.)
    symbol LowCardinality(String),
    ts DateTime,
    close Float64
)
PRIMARY KEY symbol, ts
SOURCE(CLICKHOUSE(
    -- Query from gapless-crypto-clickhouse ohlcv table
    -- Resamples to 15-min bars to match options IV resampling frequency
    TABLE 'ohlcv'
    QUERY "SELECT
        symbol,
        toStartOfFifteenMinutes(timestamp) AS ts,
        argMax(close, timestamp) AS close
    FROM ohlcv
    WHERE timeframe = '15m'
      AND instrument_type = 'spot'
    GROUP BY symbol, ts"
))
-- COMPLEX_KEY_HASHED: Required for composite key (symbol, ts)
-- Estimated size: ~2M rows/year × 6 years = ~12M (within HASHED limits)
LAYOUT(COMPLEX_KEY_HASHED())
-- 1-2 hour refresh for spot price updates
-- MIN 3600 = 1 hour minimum between refreshes
-- MAX 7200 = 2 hour maximum between refreshes
LIFETIME(MIN 3600 MAX 7200);

-- Usage example:
-- SELECT
--     t.*,
--     dictGet('spot_prices_dict', 'close',
--             tuple('BTCUSDT', toStartOfFifteenMinutes(t.timestamp))) AS binance_spot
-- FROM options_trades t
-- WHERE timestamp >= '2024-01-01';
