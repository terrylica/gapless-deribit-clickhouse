---
status: superseded
superseded-by: 2025-12-05-trades-only-architecture-pivot
date: 2025-12-03
decision-maker: Terry Li
consulted:
  [
    Explore-CryptoClickhouse,
    Explore-NetworkData,
    Explore-ADRPatterns,
    Plan-Architecture,
  ]
research-method: 9-agent-parallel-dctl
clarification-iterations: 2
perspectives: [UpstreamIntegration, BoundaryInterface, EcosystemArtifact]
---

# ADR: Deribit Options Data Pipeline with ClickHouse Storage

> **⚠️ SUPERSEDED**: This ADR has been superseded by [2025-12-05-trades-only-architecture-pivot](/docs/adr/2025-12-05-trades-only-architecture-pivot.md). The ticker/OI/Greeks functionality was removed in v0.2.0 in favor of a trades-only architecture.

**Design Spec**: [Implementation Spec](/docs/design/2025-12-03-deribit-options-clickhouse-pipeline/spec.md)

## Context and Problem Statement

We need to build historical GEX (Gamma Exposure) for Bitcoin options. This requires collecting Deribit options data including trades, Open Interest, and Greeks. The challenge is that **Open Interest cannot be reconstructed from trade data** (buy/sell does not equal open/close positions), requiring a dual collection strategy.

The solution must integrate with existing infrastructure patterns from `gapless-network-data` and `gapless-crypto-clickhouse`, providing a consistent API and storage layer for downstream GEX calculations.

### Before/After

```
       🔄 Options Data Pipeline Migration

┌──────────────────┐     ┌─────────────────────┐
│ Manual API Calls │     │ ClickHouse Pipeline │
│   (No History)   │ ──> │    (Trades + OI)    │
└──────────────────┘     └─────────────────────┘
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "🔄 Options Data Pipeline Migration"; flow: east; }
[ Before ] { label: "Manual API Calls\n(No History)"; }
[ After ] { label: "ClickHouse Pipeline\n(Trades + OI)"; }
[ Before ] --> [ After ]
```

</details>

## Research Summary

| Agent Perspective        | Key Finding                                                                                               | Confidence |
| ------------------------ | --------------------------------------------------------------------------------------------------------- | ---------- |
| Explore-CryptoClickhouse | 22x faster bulk downloads via CDN, ReplacingMergeTree for deduplication, Arrow-optimized ingestion        | High       |
| Explore-NetworkData      | YAML-first schema generates types/DDL/docs, credential chain (.env → Doppler → env), half-open timestamps | High       |
| Explore-ADRPatterns      | Schema at `schema/clickhouse/*.yaml` is SSoT, no CLI (Python API only), probe.py for AI discoverability   | High       |
| Plan-Architecture        | Two tables needed: trades (historical) + ticker_snapshots (forward-only OI/Greeks)                        | High       |

## Decision Log

| Decision Area   | Options Evaluated                                                              | Chosen                     | Rationale                                                                      |
| --------------- | ------------------------------------------------------------------------------ | -------------------------- | ------------------------------------------------------------------------------ |
| Package Name    | gapless-dex-clickhouse, gapless-deribit-clickhouse, gapless-options-clickhouse | gapless-deribit-clickhouse | Explicit naming for Deribit exchange, follows existing gapless-\* convention   |
| GEX Scope       | Include in package, Pure data layer, Optional module                           | Pure data layer            | Separation of concerns - data acquisition separate from calculation            |
| CLI Interface   | Python API only, CLI with subcommands, Minimal CLI                             | Python API only            | Simpler package, less maintenance, follows gapless-crypto-clickhouse pattern   |
| Schema Approach | YAML-first (generate), Code-first (implicit)                                   | YAML-first                 | Matches gapless-network-data's latest ADR architecture, single source of truth |

### Trade-offs Accepted

| Trade-off          | Choice                  | Accepted Cost                                               |
| ------------------ | ----------------------- | ----------------------------------------------------------- |
| OI Historical Data | Forward-collection only | Cannot backfill historical Open Interest - must start fresh |
| GEX Calculation    | Separate package        | Consumers need two dependencies for full GEX pipeline       |
| CLI Commands       | None                    | Must write Python scripts for backfill operations           |

## Decision Drivers

- Mirror `gapless-network-data` schema-first architecture per user requirement
- Deribit Trades API provides historical access since 2018 (no rate limits)
- Ticker API (OI/Greeks) has no historical endpoint - forward-only constraint
- Existing ClickHouse infrastructure on AWS via Doppler credentials
- Downstream GEX calculation requires OI + delta per strike/expiry

## Considered Options

- **Option A**: Single table combining trades + ticker data
  - Rejected: Different collection cadences and constraints

- **Option B**: Include GEX calculation in package
  - Rejected: Violates separation of concerns, downstream package can calculate GEX

- **Option C**: Two-table design with trades (historical) + ticker_snapshots (forward-only) <- Selected
  - Selected: Clean separation matching data source constraints

## Decision Outcome

Chosen option: **Option C (Two-table design)**, because:

1. Trades API supports historical backfill since 2018
2. Ticker API is forward-only (no historical OI available)
3. ReplacingMergeTree with trade_id/timestamp ensures idempotent ingestion
4. YAML-first schema provides single source of truth for types and DDL

## Synthesis

**Convergent findings**: All perspectives agreed on ReplacingMergeTree, Doppler credentials, and schema-first architecture.

**Divergent findings**: gapless-crypto-clickhouse uses code-first schema while gapless-network-data uses YAML-first. User requirement resolved this.

**Resolution**: Follow gapless-network-data pattern (YAML-first) as explicitly requested by user.

## Consequences

### Positive

- Historical trades backfill available from 2018
- Schema-first ensures type safety and DDL consistency
- Pure data layer enables flexible downstream GEX implementations
- Follows established gapless-\* ecosystem patterns

### Negative

- No historical Open Interest data (must collect going forward)
- No CLI commands (requires Python scripts for operations)
- Two tables require coordinated queries for complete options view

## Architecture

```
📊 Deribit Options Data Pipeline

   ┌─────────────────────┐
   │   www.deribit.com   │
   │       /ticker       │
   └─────────────────────┘
     │
     │
     ∨
   ┌─────────────────────┐
   │   TickerCollector   │
   │   (Forward-Only)    │
   └─────────────────────┘
     │
     │
     ∨
   ╔═════════════════════╗
   ║   deribit_options   ║
   ║  .ticker_snapshots  ║
   ╚═════════════════════╝
     │
     │
     ∨
   ╭─────────────────────╮
   │     Python API      │
   │   fetch_trades()    │
   │  fetch_snapshots()  │ <┐
   ╰─────────────────────╯  │
   ┌─────────────────────┐  │
   │ history.deribit.com │  │
   │  /get_last_trades   │  │
   └─────────────────────┘  │
     │                      │
     │                      │
     ∨                      │
   ┌─────────────────────┐  │
   │   TradesCollector   │  │
   │    (Historical)     │  │
   └─────────────────────┘  │
     │                      │
     │                      │
     ∨                      │
   ╔═════════════════════╗  │
   ║   deribit_options   ║  │
   ║       .trades       ║ ─┘
   ╚═════════════════════╝
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "📊 Deribit Options Data Pipeline"; flow: south; }

[ trades_api ] { label: "history.deribit.com\n/get_last_trades"; }
[ ticker_api ] { label: "www.deribit.com\n/ticker"; }

[ trades_collector ] { label: "TradesCollector\n(Historical)"; }
[ ticker_collector ] { label: "TickerCollector\n(Forward-Only)"; }

[ trades_table ] { label: "deribit_options\n.trades"; border: double; }
[ ticker_table ] { label: "deribit_options\n.ticker_snapshots"; border: double; }

[ python_api ] { label: "Python API\nfetch_trades()\nfetch_snapshots()"; shape: rounded; }

[ trades_api ] -> [ trades_collector ]
[ ticker_api ] -> [ ticker_collector ]
[ trades_collector ] -> [ trades_table ]
[ ticker_collector ] -> [ ticker_table ]
[ trades_table ] -> [ python_api ]
[ ticker_table ] -> [ python_api ]
```

</details>

## References

- [gapless-network-data](https://github.com/Eon-Labs/gapless-network-data) (UpstreamIntegration - architecture reference)
- [gapless-crypto-clickhouse](https://github.com/Eon-Labs/gapless-crypto-clickhouse) (UpstreamIntegration - patterns reference)
- [Deribit API Documentation](https://docs.deribit.com/) (UpstreamIntegration - data source)
