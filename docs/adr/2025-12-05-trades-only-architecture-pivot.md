---
status: implemented
date: 2025-12-05
decision-maker: Terry Li
consulted:
  [
    Deribit-API-Explorer,
    Gapless-Crypto-ClickHouse-Explorer,
    Current-Implementation-Explorer,
  ]
research-method: multi-agent-parallel
clarification-iterations: 3
perspectives: [LifecycleMigration, EcosystemArtifact]
---

# ADR: Trades-Only Architecture Pivot

**Design Spec**: [Implementation Spec](/docs/design/2025-12-05-trades-only-architecture-pivot/spec.md)

## Context and Problem Statement

The `gapless-deribit-clickhouse` package v0.1.0 was designed with a dual-table architecture supporting both trades (historical) and ticker snapshots (OI/Greeks, forward-only). After further requirements analysis, the user determined:

1. **Deribit-official only**: No third-party data providers (e.g., Tardis.dev)
2. **Historical data focus**: Only data that can be backfilled is valuable
3. **Trades only**: OI/Greeks from ticker snapshots cannot be backfilled via official Deribit API

This creates a mismatch: v0.1.0 includes ticker functionality that serves no purpose under the new constraints.

### Before/After

```
 🔄 Architecture Pivot: v0.1.0 → v0.2.0

        ╭─────────────────────╮
        │ v0.1.0: Dual-Table  │
        │  (Trades + Ticker)  │
        ╰─────────────────────╯
          │
          │ remove ticker
          ∨
         ━━━━━━━━━━━━━━━━━━━━━
        ┃ v0.2.0: Trades-Only ┃
        ┃    (Clean Focus)    ┃
         ━━━━━━━━━━━━━━━━━━━━━
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "🔄 Architecture Pivot: v0.1.0 → v0.2.0"; flow: south; }

[before] { label: "v0.1.0: Dual-Table\n(Trades + Ticker)"; shape: rounded; }
[after] { label: "v0.2.0: Trades-Only\n(Clean Focus)"; shape: rounded; border: bold; }

[before] -- remove ticker --> [after]
```

</details>

## Research Summary

| Agent Perspective                  | Key Finding                                                                                                                            | Confidence |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| Deribit-API-Explorer               | Deribit REST provides full historical trades since 2018 via `history.deribit.com`; no historical ticker/OI/Greeks available officially | High       |
| Gapless-Crypto-ClickHouse-Explorer | Binance Vision uses symbol-first ORDER BY for 10-100x query performance; single table with instrument_type column                      | High       |
| Current-Implementation-Explorer    | Ticker is deeply integrated (8+ files); removal is breaking change but clean; v0.1.0 likely has zero ticker API users                  | High       |

## Decision Log

| Decision Area     | Options Evaluated                                        | Chosen            | Rationale                                          |
| ----------------- | -------------------------------------------------------- | ----------------- | -------------------------------------------------- |
| Data source       | Deribit-official, Tardis.dev, Hybrid                     | Deribit-official  | User constraint: no third-party dependencies       |
| Data type         | Trades + Ticker, Trades only                             | Trades only       | OI/Greeks not backfillable via official API        |
| Instruments       | All Deribit, BTC/ETH only                                | BTC/ETH only      | Focus on most liquid underlyings                   |
| Ticker handling   | Keep (Option A), Remove (Option B), Deprecate (Option C) | Remove (Option B) | Clean codebase, semver 0.x allows breaking changes |
| Release version   | v0.2.0, v1.0.0                                           | v0.2.0            | Semver 0.x breaking changes allowed in minor       |
| Real-time capture | WebSocket, REST polling                                  | REST polling      | Sufficient for minutes-to-days horizons            |
| DB cleanup        | Keep table, Drop table                                   | Drop table        | Clean slate, no unused tables                      |

### Trade-offs Accepted

| Trade-off                        | Choice          | Accepted Cost                             |
| -------------------------------- | --------------- | ----------------------------------------- |
| OI/Greeks vs simplicity          | Simplicity      | Cannot capture forward OI data            |
| WebSocket vs REST                | REST polling    | Higher latency (minutes vs real-time)     |
| Breaking change vs compatibility | Breaking change | v0.1.0 ticker users (if any) must migrate |

## Decision Drivers

- User requires Deribit-official data sources only (no Tardis)
- Historical backfillability is the primary value criterion
- Minutes-to-days analysis horizons (not HFT)
- Complementary to existing Binance Vision pipeline in `gapless-crypto-clickhouse`
- Code cleanliness over backwards compatibility at v0.x stage

## Considered Options

- **Option A: Keep Dual-Table, Focus Development on Trades** — Leave ticker code in place but don't maintain it. Pros: No breaking change. Cons: Dead code, confusing for users.
- **Option B: Clean Removal of Ticker (v0.2.0 Breaking Change)** — Surgically remove all ticker functionality. Pros: Clean codebase. Cons: Breaking change, 8+ files to modify. ← Selected
- **Option C: Deprecate Ticker, Remove in v1.0.0** — Add deprecation warnings, remove later. Pros: Graceful transition. Cons: Maintains two states, delays cleanup.

## Decision Outcome

Chosen option: **Option B: Clean Removal of Ticker**, because:

1. User explicitly chose "trades-only focus" — no ambiguity
2. v0.1.0 just released — likely zero users of ticker API
3. Clean codebase enables faster iteration on trades layer
4. Semver 0.x allows breaking changes in minor versions
5. One-time cleanup effort vs ongoing maintenance of dead code

## Synthesis

**Convergent findings**: All perspectives agreed that ticker data without historical backfill has limited value under Deribit-official-only constraint.

**Divergent findings**: Initial planning assumed OI could be captured forward-only; user clarified this is not valuable without historical context.

**Resolution**: User explicitly chose trades-only focus in AskUserQuestion round 2.

## Consequences

### Positive

- Clean, focused codebase with single data layer (trades)
- Reduced maintenance burden (8 fewer files)
- Clear API surface: `fetch_trades()` and `collect_trades()`
- Aligns with user's "historical data priority" requirement

### Negative

- Cannot capture forward OI/Greeks data
- v0.1.0 ticker API users (if any) must remove usage
- `deribit.ticker_snapshots` table in ClickHouse becomes orphaned (requires DROP)

## Architecture

```
🏗️ Trades-Only Architecture

   ╭─────────────────────╮
   │       Deribit       │
   │ history.deribit.com │
   ╰─────────────────────╯
     │
     │ historical trades
     ∨
   ┌─────────────────────┐
   │ trades_collector.py │
   │   (REST polling)    │
   └─────────────────────┘
     │
     │ insert
     ∨
   ╔═════════════════════╗
   ║     ClickHouse      ║
   ║   deribit.trades    ║
   ╚═════════════════════╝
     │
     │ query
     ∨
   ┌─────────────────────┐
   │     Python API      │
   │   fetch_trades()    │
   └─────────────────────┘
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "🏗️ Trades-Only Architecture"; flow: south; }

[deribit] { label: "Deribit\nhistory.deribit.com"; shape: rounded; }
[collector] { label: "trades_collector.py\n(REST polling)"; }
[clickhouse] { label: "ClickHouse\nderibit.trades"; border: double; }
[api] { label: "Python API\nfetch_trades()"; }

[deribit] -- historical trades --> [collector]
[collector] -- insert --> [clickhouse]
[clickhouse] -- query --> [api]
```

</details>

## References

- [v0.1.0 Implementation ADR](/docs/adr/2025-12-03-deribit-options-clickhouse-pipeline.md)
- [Global Plan](/Users/terryli/.claude/plans/cozy-gathering-rabbit.md) (ephemeral)
- [gapless-crypto-clickhouse](https://github.com/terrylica/gapless-crypto-clickhouse) (Binance Vision patterns)
