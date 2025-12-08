---
status: accepted
date: 2025-12-08
decision-maker: Terry Li
consulted:
  [
    CurrentSchemaAnalysis,
    ClickHouseBestPractices,
    CryptoDataPatterns,
    GaplessNetworkDataComparison,
    MiseTaskFeatures,
    MiseWorkspaceAnalysis,
    MiseEnvResearch,
  ]
research-method: 9-agent-parallel-dctl
clarification-iterations: 5
perspectives:
  [NamingConvention, SchemaDesign, DeveloperExperience, Extensibility]
---

# ADR: ClickHouse Naming Convention for Deribit Options Data

**Design Spec**: [Implementation Spec](/docs/design/2025-12-08-clickhouse-naming-convention/spec.md)

## Context and Problem Statement

The current ClickHouse database naming (`deribit_options.trades`) is not representative enough:

1. **Database name is too narrow**: `deribit_options` combines exchange and market type, limiting future expansion
2. **Naming is inconsistent**: Schema file (`deribit_trades.yaml`) vs database (`deribit_options`) vs table (`trades`) don't align
3. **Not self-documenting**: Table name `trades` alone doesn't indicate it's Deribit options data

The project needs a consistent naming convention that is self-documenting, ergonomic for queries, extensible for future data types, and aligned with the schema-first architecture.

### Before/After

**Before: `deribit_options.trades`**

```
⏮️ Before: deribit_options.trades

┌─────────────────────┐     ┌─────────────────┐     ┌────────┐
│     Schema File     │     │    Database     │     │ Table  │
│ deribit_trades.yaml │ ──> │ deribit_options │ ──> │ trades │
└─────────────────────┘     └─────────────────┘     └────────┘
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "⏮️ Before: deribit_options.trades"; flow: east; }
[ Schema File\nderibit_trades.yaml ] -> [ Database\nderibit_options ] -> [ Table\ntrades ]
```

</details>

**After: `deribit.options_trades`**

```
⏭️ After: deribit.options_trades

┌─────────────────────┐     ┌──────────┐     ┌────────────────┐
│     Schema File     │     │ Database │     │     Table      │
│ options_trades.yaml │ ──> │ deribit  │ ──> │ options_trades │
└─────────────────────┘     └──────────┘     └────────────────┘
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "⏭️ After: deribit.options_trades"; flow: east; }
[ Schema File\noptions_trades.yaml ] -> [ Database\nderibit ] -> [ Table\noptions_trades ]
```

</details>

## Research Summary

| Agent Perspective            | Key Finding                                                                          | Confidence |
| ---------------------------- | ------------------------------------------------------------------------------------ | ---------- |
| CurrentSchemaAnalysis        | Current schema is internally consistent (all snake_case), but naming pattern unclear | High       |
| ClickHouseBestPractices      | snake_case is dominant; official docs have minimal naming guidance                   | High       |
| CryptoDataPatterns           | Three patterns: column-based exchange ID, table-per-exchange, database-per-exchange  | High       |
| GaplessNetworkDataComparison | Current project evolved patterns well with better extensibility                      | High       |
| MiseTaskFeatures             | `depends_post`, `usage` args, `hide=true` are valuable unused features               | High       |
| MiseWorkspaceAnalysis        | gapless-deribit-clickhouse is already the most sophisticated mise user in workspace  | High       |
| MiseEnvResearch              | `_.file = '.env'` enables SSoT with backward compatibility                           | High       |

## Decision Log

| Decision Area      | Options Evaluated                                                                                                  | Chosen                | Rationale                                                                         |
| ------------------ | ------------------------------------------------------------------------------------------------------------------ | --------------------- | --------------------------------------------------------------------------------- |
| Naming pattern     | A: deribit.options_trades, B: deribit_options.trades, C: options.deribit_trades, D: default.deribit_options_trades | A                     | database=exchange allows extensibility; table=market_datatype is self-documenting |
| Schema file naming | Keep deribit_trades.yaml, Rename to options_trades.yaml                                                            | Rename                | File name should match table name exactly for schema-first alignment              |
| Migration strategy | Copy data, Direct rename, Delete and recreate                                                                      | Delete and recreate   | User confirmed OK to backfill from Deribit API; simplest approach                 |
| mise task features | Basic tasks, Add depends_post, Add task arguments, Add hidden helpers                                              | All advanced features | Holistically achieve all purposes: validation, flexibility, clean output          |

### Trade-offs Accepted

| Trade-off                          | Choice                | Accepted Cost                                                 |
| ---------------------------------- | --------------------- | ------------------------------------------------------------- |
| Brevity vs Clarity                 | Clarity               | Longer table name (`options_trades`) vs shorter (`trades`)    |
| Database per exchange vs Single DB | Database per exchange | Need to specify database in queries: `deribit.options_trades` |

## Decision Drivers

- Self-documenting names that immediately convey data content
- Query ergonomics for SQL development
- Extensibility for future data types (orderbook, futures, funding)
- Schema-first alignment where file names match table names

## Considered Options

- **Option A**: `deribit.options_trades` - Database=exchange, table=market_datatype (Selected)
- **Option B**: `deribit_options.trades` - Current pattern, database=exchange+market, table=datatype
- **Option C**: `options.deribit_trades` - Database=market, table=exchange_datatype
- **Option D**: `default.deribit_options_trades` - Single database, fully qualified table name

## Decision Outcome

Chosen option: **Option A** (`deribit.options_trades`), because:

1. **Self-documenting**: `options_trades` immediately indicates options trade data
2. **Query ergonomics**: `FROM deribit.options_trades` is natural and reasonable length
3. **Extensibility**: Pattern supports `deribit.options_orderbook`, `deribit.futures_trades`
4. **Schema-first alignment**: File `options_trades.yaml` matches table `options_trades` exactly

## Synthesis

**Convergent findings**: All agent perspectives agreed that snake_case is the standard, and schema-file-to-table alignment is important for the schema-first architecture.

**Divergent findings**: Industry has multiple database organization patterns (single DB, DB per exchange, DB per market). No single "correct" answer.

**Resolution**: User chose database-per-exchange pattern (`deribit` database) as it provides clear namespace isolation while remaining practical for single-exchange focus.

## Consequences

### Positive

- Clear, self-documenting table names
- Consistent naming across schema file, database, and table
- Extensible pattern for future data types
- Better developer experience with intuitive queries
- Advanced mise tasks with automatic validation

### Negative

- Breaking change requiring migration
- Need to update all code references (6 Python files, 2 test files)
- Existing data loss (acceptable per user - will backfill from API)

## Architecture

```
🏗️ Schema-First Architecture with mise Tasks

          ╭────────────────────────╮
          │  mise run db-migrate   │
          ╰────────────────────────╯
            │
            │
            ∨
          ┌────────────────────────┐
          │        db-drop         │
          └────────────────────────┘
            │
            │
            ∨
          ┌────────────────────────┐
          │        db-init         │
          └────────────────────────┘
            │
            │
            ∨
          ┌────────────────────────┐
          │    schema-validate     │
          └────────────────────────┘
            │
            │
            ∨
          ┌────────────────────────┐
          │        test-e2e        │
          └────────────────────────┘
          ╔════════════════════════╗
          ║  options_trades.yaml   ║
          ║         (SSoT)         ║
          ╚════════════════════════╝
            │
            │
            ∨
          ┌────────────────────────┐
          │  Python Schema Loader  │
          └────────────────────────┘
            │
            │
            ∨
          ┌────────────────────────┐
          │   ClickHouse Client    │
          └────────────────────────┘
            │
            │
            ∨
          ┌────────────────────────┐
          │ deribit.options_trades │
          └────────────────────────┘
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "🏗️ Schema-First Architecture with mise Tasks"; flow: south; }
[ options_trades.yaml\n(SSoT) ] { border: double; }
[ options_trades.yaml\n(SSoT) ] -> [ Python Schema Loader ]
[ Python Schema Loader ] -> [ ClickHouse Client ]
[ ClickHouse Client ] -> [ deribit.options_trades ]
[ mise run db-migrate ] { shape: rounded; }
[ mise run db-migrate ] -> [ db-drop ] -> [ db-init ]
[ db-init ] -> [ schema-validate ]
[ schema-validate ] -> [ test-e2e ]
```

</details>

## References

- [Schema-First E2E Validation ADR](/docs/adr/2025-12-07-schema-first-e2e-validation.md)
- [Trades-Only Architecture ADR](/docs/adr/2025-12-05-trades-only-architecture-pivot.md)
- [mise documentation](https://mise.jdx.dev/)
