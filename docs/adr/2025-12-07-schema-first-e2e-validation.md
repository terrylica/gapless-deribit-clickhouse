---
status: accepted
date: 2025-12-07
decision-maker: Terry Li
consulted: [Explore-Agent, Plan-Agent]
research-method: single-agent
clarification-iterations: 3
perspectives: [Testing, DeveloperExperience, DataIntegrity]
---

# ADR: Schema-First E2E Validation with Contract Tests

**Design Spec**: [Implementation Spec](/docs/design/2025-12-07-schema-first-e2e-validation/spec.md)

## Context and Problem Statement

The gapless-deribit-clickhouse project has 25 tests but 0% coverage on the collectors module and no validation against real Deribit API data. The current testing approach lacks:

1. **Contract tests** - No architectural invariant validation
2. **E2E roundtrip tests** - No verification of Deribit API → ClickHouse → fetch_trades() flow
3. **Schema validation** - No comparison between YAML schema and live ClickHouse
4. **Unified task runner** - Tests scattered without consistent execution pattern

This ADR establishes a schema-first testing architecture following patterns from gapless-network-data.

### Before/After

**Before**: No schema validation, scattered tests

```
                ⏮️ Before: Testing Gap

┏━━━━━━━━━━━━━┓                          ┌────────────┐
┃ YAML Schema ┃  · · · · no validation · │ ClickHouse │
┗━━━━━━━━━━━━━┛                          └────────────┘

┌───────────────┐     ┌───────────────┐
│  Unit Tests   │     │ 1 Integration │
│   (24 only)   │     │     Test      │
└───────────────┘     └───────────────┘

0 Contract Tests | 0 E2E Tests | No task runner
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "⏮️ Before: Testing Gap"; flow: east; }

[ YAML Schema ] { border: bold; }
[ ClickHouse ]
[ Unit Tests\n(24 only) ]
[ 1 Integration\nTest ]

[ YAML Schema ] ..> [ ClickHouse ]
```

</details>

**After**: Schema-first with contract tests and E2E validation

```
⏭️ After: Schema-First Validation

                                        ┏━━━━━━━━━━━━━━━━┓
                                        ┃  YAML Schema   ┃
                                        ┃     (SSoT)     ┃
                                        ┗━━━━━━━━━━━━━━━━┛
                                          │
                                          │
                                          ∨
                                        ┌────────────────┐
  ┌──────────────────────────────────── │ Schema Loader  │
  │                                     └────────────────┘
  │                                       │
  │                                       │
  ∨                                       ∨
┌──────────────┐     ╭────────────╮     ┌────────────────┐
│ Introspector │ <── │ mise tasks │ ──> │ Contract Tests │
└──────────────┘     ╰────────────╯     └────────────────┘
  │                    │                  │
  │                    │                  │
  │                    ∨                  ∨
  │                  ┌────────────┐     ╔════════════════╗
  │                  │ E2E Tests  │ ──> ║   ClickHouse   ║
  │                  └────────────┘     ╚════════════════╝
  │              validates                ∧
  └───────────────────────────────────────┘
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "⏭️ After: Schema-First Validation"; flow: south; }

[ YAML Schema\n(SSoT) ] { border: bold; }
[ Schema Loader ]
[ Introspector ]
[ ClickHouse ] { border: double; }
[ Contract Tests ]
[ E2E Tests ]
[ mise tasks ] { shape: rounded; }

[ YAML Schema\n(SSoT) ] -> [ Schema Loader ]
[ Schema Loader ] -> [ Introspector ]
[ Schema Loader ] -> [ Contract Tests ]
[ Introspector ] -- validates --> [ ClickHouse ]
[ Contract Tests ] -> [ ClickHouse ]
[ E2E Tests ] -> [ ClickHouse ]
[ mise tasks ] -> [ Contract Tests ]
[ mise tasks ] -> [ E2E Tests ]
[ mise tasks ] -> [ Introspector ]
```

</details>

## Research Summary

| Agent Perspective              | Key Finding                                                  | Confidence |
| ------------------------------ | ------------------------------------------------------------ | ---------- |
| Explore (gapless-network-data) | YAML schema with x-clickhouse/x-pandas extensions works well | High       |
| Explore (alpha-forge)          | Contract tests validate architecture, not behavior           | High       |
| Plan                           | mise tasks provide unified task runner                       | High       |

## Decision Log

| Decision Area   | Options Evaluated                   | Chosen              | Rationale                                   |
| --------------- | ----------------------------------- | ------------------- | ------------------------------------------- |
| Task runner     | Make, just, Taskfile, Earthly, mise | mise tasks          | User constraint: local-first, avoid Earthly |
| Credentials     | Doppler, .env, 1Password            | .env + 1Password    | Simpler for local dev, matches alpha-forge  |
| Schema pattern  | JSON Schema, YAML with extensions   | YAML + x-clickhouse | Matches gapless-network-data proven pattern |
| E2E data source | Mocks, fixtures, real API           | Real Deribit API    | Validates actual production behavior        |

### Trade-offs Accepted

| Trade-off         | Choice      | Accepted Cost                              |
| ----------------- | ----------- | ------------------------------------------ |
| Doppler vs .env   | .env        | Lose centralized secrets, gain simplicity  |
| Container testing | Local-first | Lose isolation, gain speed                 |
| CI/CD testing     | Local-first | Lose automation, follow project philosophy |

## Decision Drivers

- Project constraint: local-first tooling (no Earthly, no CI/CD testing)
- Need for real data validation, not just mocked tests
- Schema drift between YAML and live ClickHouse causes silent bugs
- Following proven patterns from gapless-network-data

## Considered Options

- **Option A**: Add more unit tests with mocked data
- **Option B**: Full containerized E2E with Earthly
- **Option C**: Schema-first architecture with contract tests and real API E2E ← Selected

## Decision Outcome

Chosen option: **Option C**, because it validates real production behavior while respecting local-first constraints. Schema-first approach ensures YAML schema remains Single Source of Truth.

## Synthesis

**Convergent findings**: All perspectives agreed on need for schema validation and real data testing.

**Divergent findings**: gapless-network-data uses complex introspector; alpha-forge uses simpler patterns.

**Resolution**: Adopt schema-first pattern but keep introspector minimal for this project's scope.

## Consequences

### Positive

- Schema drift detected automatically
- Contract tests protect architectural invariants
- E2E tests validate real Deribit API behavior
- mise tasks provide consistent developer experience

### Negative

- E2E tests require credentials (skip-without-credentials pattern)
- Schema loader adds maintenance overhead
- .env approach less secure than Doppler for team settings

## Architecture

```
                          🏗️ Schema-First E2E Validation Architecture


       ┌────────────────────────────────────────────────────────────────────┐
       │                                                                    │
     ┌───────────────────┐              ┏━━━━━━━━━━━━━━━━━━━━━━━┓           │
     │   Schema Loader   │              ┃      YAML Schema      ┃           │
     │    (loader.py)    │ <─────────── ┃ (deribit_trades.yaml) ┃           │
     └───────────────────┘              ┗━━━━━━━━━━━━━━━━━━━━━━━┛           │
       │                                                                    │
       │                                                                    │
       ∨                                                                    ∨
     ┌───────────────────┐              ╭───────────────────────╮         ┌────────────────────┐
     │   Introspector    │              │      mise tasks       │         │   Contract Tests   │
     │ (introspector.py) │ <─────────── │                       │ ──────> │ (tests/contracts/) │
     └───────────────────┘              ╰───────────────────────╯         └────────────────────┘
       │                                  │                                 │
       │ validates                        │                                 │
       ∨                                  ∨                                 │
     ╔═══════════════════╗              ┌───────────────────────┐           │
     ║    ClickHouse     ║  roundtrip   │       E2E Tests       │           │
  ┌> ║  (live database)  ║ <─────────── │     (tests/e2e/)      │           │
  │  ╚═══════════════════╝              └───────────────────────┘           │
  │    │                                  │                                 │
  │    │                                  │                                 │
  │    ∨                                  │                                 │
  │  ┌───────────────────┐                │                       test      │
  │  │  fetch_trades()   │ <──────────────┼─────────────────────────────────┘
  │  └───────────────────┘                │
  │                                       │
  │                                       │ roundtrip
  │                                       ∨
  │                                     ╭───────────────────────╮
  │                                     │      Deribit API      │
  └──────────────────────────────────── │ (history.deribit.com) │
                                        ╰───────────────────────╯
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "🏗️ Schema-First E2E Validation Architecture"; flow: south; }

[ Deribit API\n(history.deribit.com) ] { shape: rounded; }
[ ClickHouse\n(live database) ] { border: double; }
[ YAML Schema\n(deribit_trades.yaml) ] { border: bold; }
[ Schema Loader ] { label: "Schema Loader\n(loader.py)"; }
[ Introspector ] { label: "Introspector\n(introspector.py)"; }
[ Contract Tests ] { label: "Contract Tests\n(tests/contracts/)"; }
[ E2E Tests ] { label: "E2E Tests\n(tests/e2e/)"; }
[ fetch_trades() ]
[ mise tasks ] { shape: rounded; }

[ Deribit API\n(history.deribit.com) ] -> [ ClickHouse\n(live database) ]
[ ClickHouse\n(live database) ] -> [ fetch_trades() ]
[ YAML Schema\n(deribit_trades.yaml) ] -> [ Schema Loader ]
[ Schema Loader ] -> [ Contract Tests ]
[ Schema Loader ] -> [ Introspector ]
[ Introspector ] -- validates --> [ ClickHouse\n(live database) ]
[ Contract Tests ] -- test --> [ fetch_trades() ]
[ E2E Tests ] -- roundtrip --> [ Deribit API\n(history.deribit.com) ]
[ E2E Tests ] -- roundtrip --> [ ClickHouse\n(live database) ]
[ mise tasks ] -> [ Contract Tests ]
[ mise tasks ] -> [ E2E Tests ]
[ mise tasks ] -> [ Introspector ]
```

</details>

## References

- [Trades-Only Architecture ADR](/docs/adr/2025-12-05-trades-only-architecture-pivot.md)
- Pattern source: gapless-network-data schema loader
- Pattern source: alpha-forge contract tests
