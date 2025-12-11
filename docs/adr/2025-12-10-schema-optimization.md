---
status: accepted
date: 2025-12-10
decision-maker: Terry Li
consulted:
  [
    Schema-Performance-Agent,
    Query-Benchmark-Agent,
    Migration-Strategy-Agent,
    Data-Volume-Agent,
  ]
research-method: 9-agent-parallel-dctl
clarification-iterations: 3
perspectives: [Performance, DataIntegrity, Migration]
---

# ADR: ClickHouse Schema Optimization for v3.0.0

**Design Spec**: [Implementation Spec](/docs/design/2025-12-10-schema-optimization/spec.md)

## Context and Problem Statement

The `gapless-deribit-clickhouse` pipeline exhibited critical performance issues discovered during end-to-end validation:

1. **Unbounded memory**: `collect_trades()` accumulated all trades in memory during multi-year backfills
2. **O(n²) complexity**: `iv_percentile.py` rolling apply passed Series instead of numpy arrays
3. **Silent failures**: `spot_provider.py` crashed when ClickHouse dictionary didn't exist
4. **Slow time-range queries**: ORDER BY key lacked timestamp, causing 3.6x slower queries
5. **Missing deduplication**: API queries lacked FINAL clause for ReplacingMergeTree

These issues blocked production deployment for backtesting workloads requiring 6+ years of historical data.

### Before/After

**Before (v2.x):**

```
                         ⏮️ Before: v2.x Performance Issues

                                 ╭──────────────────────╮
                                 │     Deribit API      │
                                 ╰──────────────────────╯
                                   │
                                   │
                                   ∨
                                 ┏━━━━━━━━━━━━━━━━━━━━━━┓
                                 ┃ trades_collector.py  ┃
                                 ┗━━━━━━━━━━━━━━━━━━━━━━┛
                                   │
                                   │
                                   ∨
                                 ┌──────────────────────┐
                                 │ [!] list (unbounded) │
                                 └──────────────────────┘
                                   │
                                   │ OOM
                                   ∨
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┓     ╔══════════════════════╗     ┏━━━━━━━━━━━━━━━━━━━━━┓
┃     iv_percentile.py     ┃ <── ║      ClickHouse      ║ ──> ┃  spot_provider.py   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━┛     ╚══════════════════════╝     ┗━━━━━━━━━━━━━━━━━━━━━┛
  │                                │                            │
  │                                │                            │
  ∨                                ∨                            ∨
┌──────────────────────────┐     ┏━━━━━━━━━━━━━━━━━━━━━━┓     ┌─────────────────────┐
│ [!] Series.apply() O(n²) │     ┃        api.py        ┃     │ [x] dictGet() crash │
└──────────────────────────┘     ┗━━━━━━━━━━━━━━━━━━━━━━┛     └─────────────────────┘
                                   │
                                   │
                                   ∨
                                 ┌──────────────────────┐
                                 │  [!] Missing FINAL   │
                                 └──────────────────────┘
```

<details>
<summary>graph-easy source (Before)</summary>

```
graph { label: "⏮️ Before: v2.x Performance Issues"; flow: south; }
[ Deribit API ] { shape: rounded; }
[ trades_collector.py ] { border: bold; }
[ list (unbounded) ] { label: "[!] list (unbounded)"; }
[ ClickHouse ] { border: double; }
[ iv_percentile.py ] { border: bold; }
[ Series.apply() ] { label: "[!] Series.apply() O(n²)"; }
[ spot_provider.py ] { border: bold; }
[ dictGet() crash ] { label: "[x] dictGet() crash"; }
[ api.py ] { border: bold; }
[ Missing FINAL ] { label: "[!] Missing FINAL"; }

[ Deribit API ] -> [ trades_collector.py ]
[ trades_collector.py ] -> [ list (unbounded) ]
[ list (unbounded) ] -- OOM --> [ ClickHouse ]
[ ClickHouse ] -> [ iv_percentile.py ]
[ iv_percentile.py ] -> [ Series.apply() ]
[ ClickHouse ] -> [ spot_provider.py ]
[ spot_provider.py ] -> [ dictGet() crash ]
[ ClickHouse ] -> [ api.py ]
[ api.py ] -> [ Missing FINAL ]
```

</details>

**After (v3.0.0):**

```
                         ⏭️ After: v3.0.0 Optimized Pipeline

                             ╭────────────────────────╮
                             │      Deribit API       │
                             ╰────────────────────────╯
                               │
                               │
                               ∨
                             ┏━━━━━━━━━━━━━━━━━━━━━━━━┓
                             ┃  trades_collector.py   ┃
                             ┗━━━━━━━━━━━━━━━━━━━━━━━━┛
                               │
                               │
                               ∨
                             ┌────────────────────────┐
                             │ [+] deque(maxlen=100k) │
                             └────────────────────────┘
                               │
                               │ bounded
                               ∨
┏━━━━━━━━━━━━━━━━━━━━━━┓     ╔════════════════════════╗     ┏━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                      ┃     ║   [+] ClickHouse v3    ║     ┃                        ┃
┃   iv_percentile.py   ┃     ║  ORDER BY +timestamp   ║     ┃    spot_provider.py    ┃
┃                      ┃     ║     LowCardinality     ║     ┃                        ┃
┃                      ┃ <── ║         Codecs         ║ ──> ┃                        ┃
┗━━━━━━━━━━━━━━━━━━━━━━┛     ╚════════════════════════╝     ┗━━━━━━━━━━━━━━━━━━━━━━━━┛
  │                            │                              │
  │                            │                              │
  ∨                            ∨                              ∨
┌──────────────────────┐     ┏━━━━━━━━━━━━━━━━━━━━━━━━┓     ┌────────────────────────┐
│ [+] raw=True (numpy) │     ┃         api.py         ┃     │ [+] auto-fallback JOIN │
└──────────────────────┘     ┗━━━━━━━━━━━━━━━━━━━━━━━━┛     └────────────────────────┘
                               │
                               │
                               ∨
                             ┌────────────────────────┐
                             │    [+] FINAL clause    │
                             └────────────────────────┘
```

<details>
<summary>graph-easy source (After)</summary>

```
graph { label: "⏭️ After: v3.0.0 Optimized Pipeline"; flow: south; }
[ Deribit API ] { shape: rounded; }
[ trades_collector.py ] { border: bold; }
[ deque(maxlen) ] { label: "[+] deque(maxlen=100k)"; }
[ ClickHouse v3 ] { label: "[+] ClickHouse v3\nORDER BY +timestamp\nLowCardinality\nCodecs"; border: double; }
[ iv_percentile.py ] { border: bold; }
[ raw=True ] { label: "[+] raw=True (numpy)"; }
[ spot_provider.py ] { border: bold; }
[ auto-fallback ] { label: "[+] auto-fallback JOIN"; }
[ api.py ] { border: bold; }
[ FINAL clause ] { label: "[+] FINAL clause"; }

[ Deribit API ] -> [ trades_collector.py ]
[ trades_collector.py ] -> [ deque(maxlen) ]
[ deque(maxlen) ] -- bounded --> [ ClickHouse v3 ]
[ ClickHouse v3 ] -> [ iv_percentile.py ]
[ iv_percentile.py ] -> [ raw=True ]
[ ClickHouse v3 ] -> [ spot_provider.py ]
[ spot_provider.py ] -> [ auto-fallback ]
[ ClickHouse v3 ] -> [ api.py ]
[ api.py ] -> [ FINAL clause ]
```

</details>

## Research Summary

Four sub-agents conducted parallel research on schema performance:

| Agent Perspective  | Key Finding                                           | Confidence |
| ------------------ | ----------------------------------------------------- | ---------- |
| Schema-Performance | timestamp in ORDER BY improves time-range queries 10x | High       |
| Query-Benchmark    | Current schema: 3.6x slower for time-range vs expiry  | High       |
| Migration-Strategy | Shadow Table + MV + EXCHANGE safest for production    | High       |
| Data-Volume        | 7,110 rows current; full backfill ~12h                | High       |

### Schema Performance Testing Results

| Query Pattern                   | Without timestamp | With timestamp | Improvement |
| ------------------------------- | ----------------- | -------------- | ----------- |
| `WHERE timestamp BETWEEN ...`   | Full scan         | Index seek     | 10-100x     |
| `WHERE expiry = '2024-12-27'`   | Index seek        | Index seek     | No change   |
| `ORDER BY timestamp DESC LIMIT` | Sort required     | Pre-sorted     | 5-10x       |

### LowCardinality Benefits

| Column      | Cardinality  | Storage Savings |
| ----------- | ------------ | --------------- |
| direction   | 2 (buy/sell) | ~30%            |
| underlying  | 2 (BTC/ETH)  | ~30%            |
| option_type | 2 (C/P)      | ~30%            |

### Compression Codec Benefits

| Codec              | Data Type        | Compression Ratio |
| ------------------ | ---------------- | ----------------- |
| DoubleDelta + ZSTD | Timestamps       | 60-80%            |
| Gorilla + ZSTD     | Float64 (prices) | 40-60%            |

## Decision Log

| Decision Area      | Options Evaluated                     | Chosen          | Rationale                                |
| ------------------ | ------------------------------------- | --------------- | ---------------------------------------- |
| Migration strategy | ALTER, Shadow+EXCHANGE, DROP+Recreate | DROP + Recreate | Clean slate, small dataset (7k rows)     |
| ORDER BY           | Keep current, Add timestamp           | Add timestamp   | 10-100x faster time-range queries        |
| LowCardinality     | Skip, Add to low-card columns         | Add             | 30% storage savings, no downsides        |
| Compression codecs | Skip, Add DoubleDelta/Gorilla         | Add             | 40-80% compression for timestamps/floats |
| Memory management  | Keep list, Use deque                  | deque(maxlen)   | Bounded memory prevents OOM              |
| Rolling apply      | Keep Series, Use raw=True             | raw=True        | 100x faster with numpy arrays            |

### Trade-offs Accepted

| Trade-off            | Choice          | Accepted Cost                |
| -------------------- | --------------- | ---------------------------- |
| Migration downtime   | DROP + Recreate | ~12h backfill required       |
| Breaking API changes | v3.0.0          | Users must handle new params |
| ORDER BY change      | Add timestamp   | Existing table incompatible  |

## Decision Drivers

- Production deployment blocked by OOM on 6-year backfills
- 3.6x query performance gap for time-range queries
- Silent failures in spot price enrichment pipeline
- Duplicate rows in API results without FINAL clause

## Considered Options

- **Option A**: Incremental fixes only (memory, IV percentile)
  - Pros: No migration required
  - Cons: Still slow queries, no compression benefits

- **Option B**: ALTER TABLE for schema changes
  - Pros: No data loss
  - Cons: Cannot change ORDER BY; complex migration

- **Option C**: DROP + Recreate + Backfill <- Selected
  - Pros: Clean slate, full optimizations, simple
  - Cons: 12h downtime for backfill

## Decision Outcome

Chosen option: **Option C (DROP + Recreate + Backfill)**, because:

1. Dataset is small (7,110 rows) - full backfill is feasible (~12h)
2. ORDER BY changes require table recreation anyway
3. Clean slate eliminates migration complexity
4. All optimizations can be applied at once

## Synthesis

**Convergent findings**: All agents agreed that timestamp in ORDER BY is critical for time-range query performance.

**Divergent findings**: Migration strategy varied between agents:

- Schema-Performance: Favored ALTER TABLE
- Migration-Strategy: Favored Shadow + EXCHANGE
- Data-Volume: Noted small dataset makes DROP viable

**Resolution**: User chose DROP + Recreate given small dataset size and clean-slate benefits.

## Consequences

### Positive

- 10-100x faster time-range queries via timestamp in ORDER BY
- Bounded memory prevents OOM on large backfills
- 100x faster IV percentile calculation
- 30-80% storage reduction from LowCardinality and codecs
- Deduplicated results via FINAL clause
- Automatic dictionary fallback prevents silent failures

### Negative

- Breaking changes require v3.0.0 major version bump
- ~12h backfill downtime required
- Users must update code for new API parameters

## Architecture

```
🏗️ v3.0.0 Data Pipeline Architecture

╭─────────────╮     ┏━━━━━━━━━━━━━━━━━━┓     ┌───────────┐     ╔═══════════════╗            ┏━━━━━━━━━━━━━━━━━━┓     ╭───────────╮
│ Deribit API │     ┃ trades_collector ┃     │   deque   │     ║  ClickHouse   ║  FINAL     ┃      api.py      ┃     │ DataFrame │
│             │ ──> ┃                  ┃ ──> │ (bounded) │ ──> ║               ║ ─────────> ┃                  ┃ ──> │           │
╰─────────────╯     ┗━━━━━━━━━━━━━━━━━━┛     └───────────┘     ╚═══════════════╝            ┗━━━━━━━━━━━━━━━━━━┛     ╰───────────╯
                                                                 │
                                                                 │
                                                                 ∨
                                                               ┏━━━━━━━━━━━━━━━┓  dictGet   ┌──────────────────┐
                                                               ┃ spot_provider ┃ ─────────> │ spot_prices_dict │
                                                               ┗━━━━━━━━━━━━━━━┛            └──────────────────┘
                                                                 │
                                                                 │ fallback
                                                                 ∨
                                                               ┌───────────────┐
                                                               │     ohlcv     │
                                                               │  (fallback)   │
                                                               └───────────────┘
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "🏗️ v3.0.0 Data Pipeline Architecture"; flow: east; }
[ Deribit API ] { shape: rounded; }
[ trades_collector ] { border: bold; }
[ deque ] { label: "deque\n(bounded)"; }
[ ClickHouse ] { border: double; }
[ api.py ] { border: bold; }
[ DataFrame ] { shape: rounded; }
[ spot_provider ] { border: bold; }
[ Dictionary ] { label: "spot_prices_dict"; }
[ ohlcv ] { label: "ohlcv\n(fallback)"; }

[ Deribit API ] -> [ trades_collector ]
[ trades_collector ] -> [ deque ]
[ deque ] -> [ ClickHouse ]
[ ClickHouse ] -- FINAL --> [ api.py ]
[ api.py ] -> [ DataFrame ]
[ ClickHouse ] -> [ spot_provider ]
[ spot_provider ] -- dictGet --> [ Dictionary ]
[ spot_provider ] -- fallback --> [ ohlcv ]
```

</details>

## References

- [ClickHouse Data Pipeline Architecture](/docs/adr/2025-12-08-clickhouse-data-pipeline-architecture.md)
- [Deribit Options Alpha Features](/docs/adr/2025-12-10-deribit-options-alpha-features.md)
- [ClickHouse Query Optimization Guide](https://clickhouse.com/docs/optimize/query-optimization)
- [Dictionaries to Accelerate Queries](https://clickhouse.com/blog/faster-queries-dictionaries-clickhouse)
