---
adr: 2025-12-08-clickhouse-naming-convention
source: ~/.claude/plans/spicy-conjuring-planet.md
implementation-status: complete
phase: phase-2
last-updated: 2025-12-08
---

# Design Spec: ClickHouse Naming Convention

**ADR**: [ClickHouse Naming Convention ADR](/docs/adr/2025-12-08-clickhouse-naming-convention.md)

## Summary

Rename database and table from `deribit_options.trades` to `deribit.options_trades` following a consistent naming pattern where database=exchange and table=market_datatype.

**Current State:**

- Database: `deribit_options` | Table: `trades` | Schema file: `deribit_trades.yaml`

**Target State:**

- Database: `deribit` | Table: `options_trades` | Schema file: `options_trades.yaml`

**Migration Strategy:** Delete legacy, create anew, backfill from Deribit API.

---

## Goals Achieved

| Goal                   | How Achieved                                                           |
| ---------------------- | ---------------------------------------------------------------------- |
| Self-documenting       | `options_trades` immediately indicates options trade data              |
| Query ergonomics       | `FROM deribit.options_trades` - natural, reasonable length             |
| Extensibility          | Pattern supports `deribit.options_orderbook`, `deribit.futures_trades` |
| Schema-first alignment | File `options_trades.yaml` matches table `options_trades` exactly      |

---

## Implementation Tasks

### Step 1: Schema File Changes

- [ ] **Rename file**: `schema/clickhouse/deribit_trades.yaml` → `options_trades.yaml`
- [ ] **Update schema content** in `options_trades.yaml`:
  - Line 2: Comment → `deribit.options_trades`
  - Line 8: `$id` → `https://gapless-deribit-clickhouse/schema/deribit/options_trades`
  - Line 18: `database` → `deribit`
  - Line 19: `table` → `options_trades`

### Step 2: Python Code Changes

| File                                                                | Change                                                                   |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `src/gapless_deribit_clickhouse/schema/loader.py`                   | Change `load_schema("deribit_trades")` → `load_schema("options_trades")` |
| `src/gapless_deribit_clickhouse/api.py:162`                         | Change `FROM deribit_options.trades` → `FROM deribit.options_trades`     |
| `src/gapless_deribit_clickhouse/collectors/trades_collector.py:203` | Change INSERT target to `deribit.options_trades`                         |
| `src/gapless_deribit_clickhouse/probe.py:58`                        | Change table reference to `deribit.options_trades`                       |
| `src/gapless_deribit_clickhouse/schema/cli.py:33,53`                | Change `load_schema("deribit_trades")` → `load_schema("options_trades")` |
| `src/gapless_deribit_clickhouse/schema/introspector.py:11`          | Change `load_schema("deribit_trades")` → `load_schema("options_trades")` |

### Step 3: Test Updates

| File                                       | Changes                                                                                     |
| ------------------------------------------ | ------------------------------------------------------------------------------------------- |
| `tests/contracts/test_schema_contracts.py` | All `load_schema("deribit_trades")` → `"options_trades"`, assertion `database == "deribit"` |
| `tests/e2e/test_full_roundtrip.py`         | All schema references → `"options_trades"`                                                  |

### Step 4: mise Tasks (Advanced Features)

**Enhanced [env] section (SSoT for configuration):**

```toml
[env]
_.python.venv = { path = ".venv", create = true }
_.file = '.env'  # Load ClickHouse credentials from .env

# Schema-first configuration (SSoT)
CLICKHOUSE_DATABASE = "deribit"
CLICKHOUSE_TABLE = "options_trades"
```

**Hidden helper tasks (internal utilities):**

```toml
[tasks._check-credentials]
description = "Verify ClickHouse credentials are set"
hide = true
run = """
if [ -z "$CLICKHOUSE_HOST_READONLY" ]; then
  echo "❌ CLICKHOUSE_HOST_READONLY not set. Copy .env.example to .env"
  exit 1
fi
echo "✓ Credentials configured"
"""

[tasks._confirm-destructive]
description = "Confirm destructive operation"
hide = true
run = """
echo "⚠️  This will DROP existing data. Press Enter to continue or Ctrl+C to cancel..."
read
"""
```

**New tasks with `depends_post` and task arguments:**

```toml
[tasks.db-init]
description = "Create ClickHouse database and table from schema"
depends = ["_check-credentials"]
depends_post = ["schema-validate"]
usage = 'opt \"--schema\" default=\"options_trades\" help=\"Schema name to initialize\"'
run = "uv run python -m gapless_deribit_clickhouse.schema.cli init --schema ${usage_schema}"

[tasks.db-drop]
description = "Drop legacy database (destructive!)"
depends = ["_check-credentials", "_confirm-destructive"]
run = "uv run python -m gapless_deribit_clickhouse.schema.cli drop-legacy"

[tasks.db-migrate]
description = "Full migration: drop legacy + create new + validate"
depends = ["db-drop", "db-init"]
depends_post = ["test-e2e"]
run = "echo '✓ Migration complete'"

[tasks.schema-validate]
description = "Validate YAML schema vs live ClickHouse"
depends = ["_check-credentials"]
usage = 'opt \"--schema\" default=\"options_trades\" help=\"Schema name to validate\"'
run = "uv run python -m gapless_deribit_clickhouse.schema.cli validate --schema ${usage_schema}"
```

### Step 5: CLI Commands

Add to `src/gapless_deribit_clickhouse/schema/cli.py`:

- `init`: CREATE DATABASE + CREATE TABLE from YAML x-clickhouse metadata
- `drop-legacy`: DROP TABLE deribit_options.trades + DROP DATABASE deribit_options

### Step 6: Documentation Updates

| File        | Update                                                |
| ----------- | ----------------------------------------------------- |
| `CLAUDE.md` | Update schema loader example to `options_trades`      |
| `README.md` | Update architecture diagram: `deribit.options_trades` |

---

## Verification Checklist (All via mise Tasks)

All verification uses real credentials against live ClickHouse:

```bash
# Single-command migration with automatic validation chain:
mise run lint          # Code quality check
mise run db-migrate    # Full migration: drop → init → validate → test-e2e

# Or step-by-step if preferred:
mise run db-drop       # Remove legacy deribit_options.trades
mise run db-init       # Create new deribit.options_trades (auto-validates)
mise run test-e2e      # Full roundtrip with live data
```

- [ ] `mise run lint` passes
- [ ] `mise run db-migrate` completes successfully (includes schema-validate + test-e2e)
- [ ] `mise run schema-diff` shows no drift
- [ ] `fetch_trades(limit=1)` returns data after backfill

---

## mise Features Used (Best Practices)

| Feature           | Usage                                        | Benefit                           |
| ----------------- | -------------------------------------------- | --------------------------------- |
| `_.file = '.env'` | Load ClickHouse credentials                  | SSoT with existing .env workflow  |
| `depends_post`    | Auto-validate after db-init                  | Guarantees migration success      |
| Task chaining     | db-migrate orchestrates all                  | Single command for full migration |
| [env] SSoT        | CLICKHOUSE_DATABASE/TABLE                    | Configuration as code             |
| `hide = true`     | `_check-credentials`, `_confirm-destructive` | Clean `mise tasks ls` output      |
| `usage` args      | `--schema` option with defaults              | Flexible, parameterized tasks     |
| `_` prefix        | Internal helper tasks                        | Convention for hidden utilities   |

---

## Success Criteria

- [ ] All Python code references updated
- [ ] Schema file renamed and content updated
- [ ] mise tasks added with advanced features
- [ ] CLI commands implemented
- [ ] Tests pass with new schema name
- [ ] Documentation updated
