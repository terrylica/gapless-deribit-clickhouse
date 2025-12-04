# gapless-deribit-clickhouse

Deribit options data pipeline with ClickHouse storage.

## Features

- **Historical trades**: Backfillable from 2018 via `history.deribit.com`
- **Ticker snapshots**: Point-in-time OI + Greeks (forward-only collection)
- **Schema-first**: YAML schemas generate types, DDL, and documentation
- **Python API**: Clean interface for querying options data

## Installation

```bash
pip install gapless-deribit-clickhouse
```

## Quick Start

```python
import gapless_deribit_clickhouse as gdch

# Fetch historical trades
df = gdch.fetch_trades(
    underlying="BTC",
    start="2024-01-01",
    end="2024-01-31",
    option_type="C"  # Calls only
)

# Fetch ticker snapshots (OI + Greeks)
df = gdch.fetch_ticker_snapshots(
    underlying="BTC",
    start="2024-12-01"
)

# Get active instruments
instruments = gdch.get_active_instruments(underlying="BTC")
```

## Data Sources

### Trades Table

| Field           | Type       | Description                 |
| --------------- | ---------- | --------------------------- |
| trade_id        | String     | Unique trade identifier     |
| instrument_name | String     | e.g., BTC-27DEC24-100000-C  |
| timestamp       | DateTime64 | Trade time (ms precision)   |
| price           | Float64    | Trade price in USD          |
| amount          | Float64    | Contract amount             |
| direction       | String     | buy or sell                 |
| iv              | Float64    | Implied volatility          |
| underlying      | String     | BTC or ETH (derived)        |
| expiry          | Date       | Option expiration (derived) |
| strike          | Float64    | Strike price (derived)      |
| option_type     | String     | C or P (derived)            |

### Ticker Snapshots Table

| Field           | Type       | Description                  |
| --------------- | ---------- | ---------------------------- |
| instrument_name | String     | e.g., BTC-27DEC24-100000-C   |
| timestamp       | DateTime64 | Snapshot time (ms precision) |
| open_interest   | Float64    | Current OI in contracts      |
| delta           | Float64    | Option delta (-1 to 1)       |
| gamma           | Float64    | Option gamma                 |
| vega            | Float64    | Option vega                  |
| theta           | Float64    | Option theta                 |
| mark_iv         | Float64    | Mark implied volatility      |

**IMPORTANT**: Open Interest cannot be reconstructed from trades. The ticker_snapshots table requires forward-only collection.

## Instrument Name Format

```
{UNDERLYING}-{DDMMMYY}-{STRIKE}-{TYPE}
```

Examples:

- `BTC-27DEC24-100000-C` - BTC call, $100k strike, expires Dec 27 2024
- `ETH-28MAR25-5000-P` - ETH put, $5k strike, expires Mar 28 2025

## Configuration

### Credentials

Set ClickHouse credentials via one of:

1. **Environment variables**:

   ```bash
   export CLICKHOUSE_HOST_READONLY=<host>
   export CLICKHOUSE_USER_READONLY=<user>
   export CLICKHOUSE_PASSWORD_READONLY=<password>
   ```

2. **`.env` file** in project root

3. **Doppler** (recommended for production):
   ```bash
   doppler setup --project gapless-deribit-clickhouse --config prd
   ```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check src/
```

## Architecture

```
📊 Deribit Options Data Pipeline

   ┌─────────────────────┐
   │ history.deribit.com │  ─┐
   │  /get_last_trades   │   │
   └─────────────────────┘   │
             │               │
             ∨               │
   ┌─────────────────────┐   │
   │   TradesCollector   │   │  Historical
   │    (Historical)     │   │  Backfill
   └─────────────────────┘   │
             │               │
             ∨               │
   ╔═════════════════════╗   │
   ║ deribit_options     ║ <─┘
   ║      .trades        ║
   ╚═════════════════════╝
             │
             ∨
   ╭─────────────────────╮
   │     Python API      │
   │   fetch_trades()    │
   │  fetch_snapshots()  │
   ╰─────────────────────╯
             ∧
             │
   ╔═════════════════════╗
   ║ deribit_options     ║ <─┐
   ║ .ticker_snapshots   ║   │
   ╚═════════════════════╝   │
             ∧               │
             │               │
   ┌─────────────────────┐   │
   │   TickerCollector   │   │  Forward-Only
   │   (Forward-Only)    │   │  Collection
   └─────────────────────┘   │
             ∧               │
             │               │
   ┌─────────────────────┐   │
   │   www.deribit.com   │  ─┘
   │       /ticker       │
   └─────────────────────┘
```

## License

MIT
