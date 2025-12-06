---
adr: 2025-12-05-trades-only-architecture-pivot
source: ~/.claude/plans/cozy-gathering-rabbit.md
implementation-status: completed
phase: phase-3
last-updated: 2025-12-05
---

# Design Spec: Trades-Only Architecture Pivot

**ADR**: [Trades-Only Architecture Pivot](/docs/adr/2025-12-05-trades-only-architecture-pivot.md)

---

## Overview

Surgically remove ticker functionality from `gapless-deribit-clickhouse` to focus on trades-only architecture. Release as v0.2.0 (breaking change under semver 0.x).

## Requirements (Confirmed)

| Requirement     | Value                                                        |
| --------------- | ------------------------------------------------------------ |
| **Data source** | Deribit-official only (no Tardis)                            |
| **Data type**   | Trades only (skip OI/Greeks entirely)                        |
| **Instruments** | BTC + ETH options only                                       |
| **Horizons**    | Minutes to days                                              |
| **Context**     | Complementary to Binance Vision in gapless-crypto-clickhouse |

---

## Implementation Tasks

### Phase 1: Quick Wins

- [x] **1.1** Add mypy strict config to `pyproject.toml`
- [x] **1.2** Implement dynamic `__version__` with importlib.metadata fallback
- [x] **1.3** Add input validation to `api.py` (fail-fast pattern)

### Phase 2: Remove Ticker Code

- [x] **2.1** Delete `schema/clickhouse/deribit_ticker_snapshots.yaml`
- [x] **2.2** Delete `src/gapless_deribit_clickhouse/collectors/ticker_collector.py`
- [x] **2.3** Update `src/gapless_deribit_clickhouse/collectors/__init__.py` (remove ticker imports)
- [x] **2.4** Update `src/gapless_deribit_clickhouse/api.py` (remove `fetch_ticker_snapshots`, `get_active_instruments`)
- [x] **2.5** Update `src/gapless_deribit_clickhouse/__init__.py` (remove ticker exports)
- [x] **2.6** Update `src/gapless_deribit_clickhouse/probe.py` (remove ticker entries)
- [x] **2.7** Update `tests/test_api.py` (remove ticker tests, add validation tests)
- [x] **2.8** Update `README.md` (remove ticker sections)
- [x] **2.9** Update original ADR (`2025-12-03-deribit-options-clickhouse-pipeline.md`) status to superseded

### Phase 3: Verification

- [x] **3.1** Run `uv run pytest` - 24 passed, 1 skipped
- [x] **3.2** Run `uv run mypy src/` - (mypy not in dev deps, skipped)
- [x] **3.3** Run `uv run ruff check` - All checks passed

### Phase 4: Database Cleanup

- [ ] **4.1** Document DROP TABLE command for ticker_snapshots
- [ ] **4.2** User runs DROP after verifying no data needed

---

## Files Modified/Deleted

| File                                                            | Action                                  | Status |
| --------------------------------------------------------------- | --------------------------------------- | ------ |
| `pyproject.toml`                                                | Add mypy config                         | ✅     |
| `src/gapless_deribit_clickhouse/__init__.py`                    | Dynamic version, remove ticker exports  | ✅     |
| `src/gapless_deribit_clickhouse/api.py`                         | Add validation, remove ticker functions | ✅     |
| `schema/clickhouse/deribit_ticker_snapshots.yaml`               | **DELETED**                             | ✅     |
| `src/gapless_deribit_clickhouse/collectors/ticker_collector.py` | **DELETED**                             | ✅     |
| `src/gapless_deribit_clickhouse/collectors/__init__.py`         | Remove ticker imports                   | ✅     |
| `src/gapless_deribit_clickhouse/probe.py`                       | Remove ticker entries                   | ✅     |
| `tests/test_api.py`                                             | Remove ticker tests, add validation     | ✅     |
| `README.md`                                                     | Remove ticker sections                  | ✅     |
| `docs/adr/2025-12-03-deribit-options-clickhouse-pipeline.md`    | Status → superseded                     | ✅     |

---

## Success Criteria

1. ✅ **Clean codebase**: No ticker references remain in source code
2. ✅ **Tests pass**: `uv run pytest` exits with 0 (24 passed, 1 skipped)
3. ✅ **Lint check**: `uv run ruff check` - All checks passed
4. ✅ **API simplicity**: Only `fetch_trades()` and `collect_trades()` in public API
5. ✅ **Documentation**: README reflects trades-only architecture

---

## Confirmed Decisions

| Question         | Answer                                            |
| ---------------- | ------------------------------------------------- |
| Release version  | **v0.2.0** (semver 0.x allows breaking changes)   |
| Real-time trades | **REST polling sufficient** (no WebSocket needed) |
| DB cleanup       | **Yes, drop ticker_snapshots table**              |

---

## Database Cleanup (Post-Release)

After v0.2.0 release, run in ClickHouse:

```sql
DROP TABLE IF EXISTS deribit.ticker_snapshots;
```

---

_Design spec for trades-only architecture pivot (v0.2.0) - COMPLETED_
