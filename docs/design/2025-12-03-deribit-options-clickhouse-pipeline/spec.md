---
adr: 2025-12-03-deribit-options-clickhouse-pipeline
source: ~/.claude/plans/partitioned-booping-cerf.md
implementation-status: completed
phase: released
last-updated: 2025-12-03
release: v0.1.0
pypi: https://pypi.org/project/gapless-deribit-clickhouse/
---

# Implementation Spec: Deribit Options ClickHouse Pipeline

**ADR**: [Deribit Options Data Pipeline](/docs/adr/2025-12-03-deribit-options-clickhouse-pipeline.md)

## Summary

Design and implement a PyPI package for Deribit options data pipeline with ClickHouse storage, mirroring the schema-first architecture of `gapless-network-data`.

## Architecture Overview

| Component       | Decision                                   |
| --------------- | ------------------------------------------ |
| Package name    | `gapless-deribit-clickhouse`               |
| Python          | 3.11+                                      |
| Build system    | Hatchling                                  |
| Schema approach | YAML-first (generates types/DDL/docs)      |
| Interface       | Python API only (no CLI)                   |
| Scope           | Pure data layer (no GEX calculation)       |
| Credentials     | Doppler (`gapless-deribit-clickhouse/prd`) |

## Package Structure

```
gapless-deribit-clickhouse/
├── schema/clickhouse/
│   ├── deribit_trades.yaml           # SSoT for trades table
│   ├── deribit_ticker_snapshots.yaml # SSoT for ticker table
│   └── _generated/
│       └── deribit_options.sql       # Generated DDL
├── src/gapless_deribit_clickhouse/
│   ├── __init__.py                   # Public exports
│   ├── api.py                        # fetch_trades(), fetch_ticker_snapshots()
│   ├── probe.py                      # AI discoverability
│   ├── exceptions.py                 # Exception hierarchy
│   ├── collectors/
│   │   ├── trades_collector.py       # Historical backfill
│   │   └── ticker_collector.py       # Forward polling
│   ├── schema/
│   │   ├── loader.py                 # YAML parser
│   │   └── _generated/               # Generated Pydantic/TypedDict
│   ├── clickhouse/
│   │   ├── config.py                 # Credential resolution
│   │   └── connection.py             # Client factory
│   └── utils/
│       └── instrument_parser.py      # Parse BTC-27DEC24-100000-C
├── tests/
├── pyproject.toml
└── README.md
```

## Implementation Tasks

### Phase 1: Foundation

- [ ] **1.1** `pyproject.toml` - Package metadata, dependencies
- [ ] **1.2** `src/gapless_deribit_clickhouse/exceptions.py` - Exception hierarchy
- [ ] **1.3** `schema/clickhouse/deribit_trades.yaml` - Trades schema (SSoT)
- [ ] **1.4** `schema/clickhouse/deribit_ticker_snapshots.yaml` - Ticker schema (SSoT)

### Phase 2: Schema Infrastructure

- [ ] **2.1** `src/gapless_deribit_clickhouse/schema/loader.py` - YAML parser (port from gapless-network-data)
- [ ] **2.2** `src/gapless_deribit_clickhouse/utils/instrument_parser.py` - Parse instrument names (BTC-27DEC24-100000-C)
- [ ] **2.3** Generate Pydantic/TypedDict types from YAML schemas

### Phase 3: ClickHouse Integration

- [ ] **3.1** `src/gapless_deribit_clickhouse/clickhouse/config.py` - Credential resolution (Doppler chain)
- [ ] **3.2** `src/gapless_deribit_clickhouse/clickhouse/connection.py` - Client factory
- [ ] **3.3** Generate DDL from YAML schemas, create tables

### Phase 4: Collectors

- [ ] **4.1** `src/gapless_deribit_clickhouse/collectors/trades_collector.py` - Historical backfill
- [ ] **4.2** `src/gapless_deribit_clickhouse/collectors/ticker_collector.py` - Forward polling

### Phase 5: Public API

- [ ] **5.1** `src/gapless_deribit_clickhouse/api.py` - fetch_trades(), fetch_ticker_snapshots()
- [ ] **5.2** `src/gapless_deribit_clickhouse/probe.py` - AI discoverability
- [ ] **5.3** `src/gapless_deribit_clickhouse/__init__.py` - Public exports

### Phase 6: Tests & Documentation

- [ ] **6.1** `tests/test_instrument_parser.py` - Unit tests for instrument parser
- [ ] **6.2** `tests/test_api.py` - Integration tests for API
- [ ] **6.3** `README.md` - Package documentation

## ClickHouse Tables

### `deribit_options.trades`

| Field           | Type       | Description                     |
| --------------- | ---------- | ------------------------------- |
| trade_id        | String     | Unique trade identifier         |
| instrument_name | String     | e.g., BTC-27DEC24-100000-C      |
| timestamp       | DateTime64 | Trade timestamp (ms precision)  |
| price           | Float64    | Trade price in USD              |
| amount          | Float64    | Contract amount                 |
| direction       | String     | 'buy' or 'sell'                 |
| iv              | Float64    | Implied volatility at trade     |
| index_price     | Float64    | Underlying index price at trade |
| underlying      | String     | Derived: BTC/ETH                |
| expiry          | Date       | Derived: option expiration      |
| strike          | Float64    | Derived: strike price           |
| option_type     | String     | Derived: 'C' or 'P'             |

**Engine**: `ReplacingMergeTree()`
**ORDER BY**: `(underlying, expiry, strike, option_type, trade_id)`
**PARTITION BY**: `toYYYYMM(timestamp)`

### `deribit_options.ticker_snapshots`

| Field           | Type       | Description                       |
| --------------- | ---------- | --------------------------------- |
| instrument_name | String     | e.g., BTC-27DEC24-100000-C        |
| timestamp       | DateTime64 | Snapshot timestamp (ms precision) |
| open_interest   | Float64    | Current open interest             |
| delta           | Float64    | Option delta                      |
| gamma           | Float64    | Option gamma                      |
| vega            | Float64    | Option vega                       |
| theta           | Float64    | Option theta                      |
| mark_iv         | Float64    | Mark implied volatility           |
| underlying      | String     | Derived: BTC/ETH                  |
| expiry          | Date       | Derived: option expiration        |
| strike          | Float64    | Derived: strike price             |
| option_type     | String     | Derived: 'C' or 'P'               |

**Engine**: `ReplacingMergeTree()`
**ORDER BY**: `(underlying, expiry, strike, option_type, timestamp)`
**PARTITION BY**: `toYYYYMM(timestamp)`

## API Endpoints

### Trades (Historical Backfill)

- **URL**: `https://history.deribit.com/api/v2/public/get_last_trades_by_currency`
- **Method**: Cursor-based pagination with `end_timestamp`
- **Rate limit**: None documented (~0.3s avg response)
- **Backfill depth**: Since 2018
- **Idempotency**: ReplacingMergeTree handles duplicates

### Ticker (Forward-Only)

- **URL**: `https://www.deribit.com/api/v2/public/ticker`
- **Method**: Periodic polling (every 5 minutes)
- **Rate limit**: 10 req/sec
- **Historical**: NOT AVAILABLE - must collect going forward

## Dependencies

```toml
dependencies = [
    "httpx>=0.28.0",
    "pandas>=2.0.0",
    "pydantic>=2.0.0",
    "tenacity>=9.0.0",
    "clickhouse-connect>=0.10.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0.0",
]
```

## Doppler Configuration

- **Project**: `gapless-deribit-clickhouse`
- **Config**: `prd`
- **Secrets**:
  - `CLICKHOUSE_HOST_READONLY`
  - `CLICKHOUSE_USER_READONLY`
  - `CLICKHOUSE_PASSWORD_READONLY`

## Critical Reference Files

| Purpose              | Reference Path                                                                      |
| -------------------- | ----------------------------------------------------------------------------------- |
| YAML schema pattern  | `/Users/terryli/eon/gapless-network-data/schema/clickhouse/ethereum_mainnet.yaml`   |
| Schema loader        | `/Users/terryli/eon/gapless-network-data/src/gapless_network_data/schema/loader.py` |
| API with credentials | `/Users/terryli/eon/gapless-network-data/src/gapless_network_data/api.py`           |
| Probe module         | `/Users/terryli/eon/gapless-network-data/src/gapless_network_data/probe.py`         |

## Success Criteria

- [ ] Package installable via `pip install gapless-deribit-clickhouse`
- [ ] `fetch_trades()` returns pandas DataFrame with historical trades
- [ ] `fetch_ticker_snapshots()` returns pandas DataFrame with OI/Greeks
- [ ] Schema YAML files are single source of truth for types and DDL
- [ ] All code references ADR ID in file headers
- [ ] Unit tests pass for instrument parser
- [ ] Integration tests pass for API queries
