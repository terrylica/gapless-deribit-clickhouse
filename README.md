# gapless-deribit-clickhouse

Deribit options data pipeline with ClickHouse storage.

## Features

- **Historical trades**: Backfillable from 2018 via `history.deribit.com`
- **Schema-first**: YAML schemas generate types, DDL, and documentation
- **Python API**: Clean interface for querying options data
- **BTC + ETH options**: Focused on Deribit options trading data

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

# Collect trades to ClickHouse
gdch.collect_trades(
    underlying="BTC",
    start="2024-01-01"
)
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
+---------------------+
| history.deribit.com |
|  /get_last_trades   |
+---------------------+
          |
          v
+---------------------+
|   TradesCollector   |  Historical
|    (Backfill)       |  Backfill
+---------------------+
          |
          v
+=====================+
|       deribit       |
|   .options_trades   |
+=====================+
          |
          v
+---------------------+
|     Python API      |
|   fetch_trades()    |
|  collect_trades()   |
+---------------------+
```

ADR: [2025-12-08-clickhouse-naming-convention](/docs/adr/2025-12-08-clickhouse-naming-convention.md)

## License

MIT
