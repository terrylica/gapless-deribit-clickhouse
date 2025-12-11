---
status: accepted
date: 2025-12-11
decision-maker: Terry Li
consulted:
  [
    Explore-Mise-Validation-Agent,
    Explore-Data-Pipeline-Agent,
    Explore-ClickHouse-Mode-Agent,
    Alpha-Forge-Research-Agent,
  ]
research-method: 4-agent-parallel
clarification-iterations: 2
perspectives: [Performance, DataIntegrity, Operations, Integration]
---

# ADR: E2E Validation Pipeline for ClickHouse Data Pipeline

**Design Spec**: [Implementation Spec](/docs/design/2025-12-11-e2e-validation-pipeline/spec.md)

## Context and Problem Statement

The `gapless-deribit-clickhouse` v3.0.0 release completed schema optimizations, but the pipeline lacks:

1. **Infrastructure validation** - No automatic dictionary creation for `spot_prices_dict`
2. **Data quality metrics** - No ClickHouse-native coverage, gap, or freshness reporting
3. **Mode visibility** - CLI output doesn't indicate which ClickHouse (local/cloud) is active
4. **Downstream compatibility** - Unclear output format requirements for alpha-forge integration

Users must manually check infrastructure and data quality, with no clear indication of which ClickHouse instance is being used.

### Before/After

**Before (v3.0.0):**

```
                       ⏮️ Before: v3.0.0 Validation Gap

                            ╭──────────────────╮
                            │   Deribit API    │
                            ╰──────────────────╯
                              │
                              │
                              ∨
                            ┏━━━━━━━━━━━━━━━━━━┓
                            ┃ trades_collector ┃
                            ┗━━━━━━━━━━━━━━━━━━┛
                              │
                              │
                              ∨
┏━━━━━━━━━━━━━━━━━━━━━┓     ╔══════════════════╗
┃    spot_provider    ┃ <── ║    ClickHouse    ║
┗━━━━━━━━━━━━━━━━━━━━━┛     ╚══════════════════╝
  │                           │
  │                           │
  ∨                           ∨
┌─────────────────────┐     ┏━━━━━━━━━━━━━━━━━━┓     ┌────────────────────────┐
│ [!] Missing dictGet │     ┃      api.py      ┃ ──> │ [!] No Quality Metrics │
└─────────────────────┘     ┗━━━━━━━━━━━━━━━━━━┛     └────────────────────────┘
                              │
                              │
                              ∨
                            ┌──────────────────┐
                            │ [?] Mode Unknown │
                            └──────────────────┘
```

<details>
<summary>graph-easy source (Before)</summary>

```
graph { label: "⏮️ Before: v3.0.0 Validation Gap"; flow: south; }
[ Deribit API ] { shape: rounded; }
[ trades_collector ] { border: bold; }
[ ClickHouse ] { border: double; }
[ spot_provider ] { border: bold; }
[ api.py ] { border: bold; }
[ Missing dictGet ] { label: "[!] Missing dictGet"; }
[ No Quality Metrics ] { label: "[!] No Quality Metrics"; }
[ Mode Unknown ] { label: "[?] Mode Unknown"; }

[ Deribit API ] -> [ trades_collector ]
[ trades_collector ] -> [ ClickHouse ]
[ ClickHouse ] -> [ spot_provider ]
[ spot_provider ] -> [ Missing dictGet ]
[ ClickHouse ] -> [ api.py ]
[ api.py ] -> [ No Quality Metrics ]
[ api.py ] -> [ Mode Unknown ]
```

</details>

**After (v3.1.0):**

```
                      ⏭️ After: v3.1.0 Validation Pipeline

                             ╭───────────────────────╮
                             │      Deribit API      │
                             ╰───────────────────────╯
                               │
                               │
                               ∨
                             ┏━━━━━━━━━━━━━━━━━━━━━━━┓
                             ┃   trades_collector    ┃
                             ┗━━━━━━━━━━━━━━━━━━━━━━━┛
                               │
                               │
                               ∨
                             ╔═══════════════════════╗
                             ║      ClickHouse       ║
                             ╚═══════════════════════╝
                               │
                               │
                               ∨
┌──────────────────────┐     ┏━━━━━━━━━━━━━━━━━━━━━━━┓     ┌─────────────────────┐
│ [+] data_quality.py  │ <── ┃    [+] validation/    ┃ ──> │   [+] reporter.py   │
└──────────────────────┘     ┗━━━━━━━━━━━━━━━━━━━━━━━┛     └─────────────────────┘
  │                            │                             │
  │                            │                             │
  ∨                            ∨                             ∨
┌──────────────────────┐     ┌───────────────────────┐     ┌─────────────────────┐
│ [OK] quality metrics │     │ [+] infrastructure.py │     │ [OK] mode indicator │
└──────────────────────┘     └───────────────────────┘     └─────────────────────┘
                               │
                               │
                               ∨
                             ┌───────────────────────┐
                             │ [OK] auto-create dict │
                             └───────────────────────┘
```

<details>
<summary>graph-easy source (After)</summary>

```
graph { label: "⏭️ After: v3.1.0 Validation Pipeline"; flow: south; }
[ Deribit API ] { shape: rounded; }
[ trades_collector ] { border: bold; }
[ ClickHouse ] { border: double; }
[ validation ] { label: "[+] validation/"; border: bold; }
[ infra check ] { label: "[+] infrastructure.py"; }
[ quality check ] { label: "[+] data_quality.py"; }
[ reporter ] { label: "[+] reporter.py"; }
[ auto-create dict ] { label: "[OK] auto-create dict"; }
[ metrics ] { label: "[OK] quality metrics"; }
[ mode indicator ] { label: "[OK] mode indicator"; }

[ Deribit API ] -> [ trades_collector ]
[ trades_collector ] -> [ ClickHouse ]
[ ClickHouse ] -> [ validation ]
[ validation ] -> [ infra check ]
[ validation ] -> [ quality check ]
[ validation ] -> [ reporter ]
[ infra check ] -> [ auto-create dict ]
[ quality check ] -> [ metrics ]
[ reporter ] -> [ mode indicator ]
```

</details>

## Research Summary

Four agents conducted parallel research:

| Agent Perspective    | Key Finding                                          | Confidence |
| -------------------- | ---------------------------------------------------- | ---------- |
| Mise-Validation      | 44 tasks in 9 categories, mode switching via env var | High       |
| Data-Pipeline        | Server-side SQL optimizations available              | High       |
| ClickHouse-Mode      | Dual-mode works, needs visibility in output          | High       |
| Alpha-Forge-Research | panel_df format required, existing template exists   | High       |

### Existing Mise Task Categories

| Category | Tasks | Purpose               |
| -------- | ----- | --------------------- |
| test     | 7     | Unit, contracts, E2E  |
| validate | 6     | Schema, data quality  |
| db       | 10    | Init, drop, migrate   |
| collect  | 3     | Trades collection     |
| query    | 4     | Sample queries        |
| dbeaver  | 2     | DBeaver integration   |
| schema   | 4     | Schema validation     |
| e2e      | 5     | End-to-end validation |
| local    | 3     | Local ClickHouse ops  |

### Alpha-Forge Integration Research

| Requirement       | Finding                                                |
| ----------------- | ------------------------------------------------------ |
| Output format     | `panel_df` (pandas DataFrame in long format)           |
| Arrow needed?     | **NO** - standard pandas DataFrames                    |
| Caching           | Handled by orchestrator (ADR-018), NOT in data plugins |
| Existing template | `pypi_gapless_crypto_clickhouse_binance_spot.py`       |
| Entry point       | `[project.entry-points."alpha_forge.capabilities"]`    |

## Decision Log

| Decision Area       | Options Evaluated                | Chosen            | Rationale                             |
| ------------------- | -------------------------------- | ----------------- | ------------------------------------- |
| Validation location | Python module vs mise tasks only | Python module     | Reusable, testable, composable        |
| Quality metrics     | Client-side pandas vs server SQL | Server-side SQL   | 10-100x faster, reduces data transfer |
| Mode indicator      | Env var only vs CLI output       | CLI output        | Better UX, clear feedback             |
| Dict auto-creation  | Manual DDL vs auto-create        | Auto-create       | Reduces user friction                 |
| Output format       | Arrow vs pandas                  | pandas (panel_df) | alpha-forge requirement               |

### Trade-offs Accepted

| Trade-off          | Choice           | Accepted Cost                       |
| ------------------ | ---------------- | ----------------------------------- |
| Module complexity  | New validation/  | More files to maintain              |
| Auto-creation risk | Auto-create dict | May mask missing DDL in production  |
| Breaking changes   | v3.1.0           | Users update validation invocations |

## Decision Drivers

- Pipeline lacks observability into data quality
- Mode switching works but is invisible to users
- alpha-forge integration requires specific output format
- E2E validation should be comprehensive and automated

## Considered Options

- **Option A**: Enhance existing mise tasks only
  - Pros: No new modules, simple
  - Cons: Not reusable, hard to test

- **Option B**: Create validation Python module + mise tasks <- Selected
  - Pros: Reusable, testable, composable
  - Cons: More complexity

- **Option C**: External validation service
  - Pros: Decoupled
  - Cons: Over-engineered for this use case

## Decision Outcome

Chosen option: **Option B (Python module + mise tasks)**, because:

1. Validation logic is reusable across CLI, tests, and future alpha-forge plugins
2. ClickHouse-native SQL metrics are testable in isolation
3. Mode indicator improves operational visibility
4. Auto-creation reduces friction while maintaining DDL as source of truth

## Architecture

```
🏗️ E2E Validation Pipeline Architecture

╭─────────────╮     ┏━━━━━━━━━━━━━━━━━━┓     ╔═══════════════╗     ┏━━━━━━━━━━━━━┓     ┏━━━━━━━━━━━━━┓
│ Deribit API │     ┃ trades_collector ┃     ║  ClickHouse   ║     ┃ validation/ ┃     ┃ mise tasks  ┃
│             │ ──> ┃                  ┃ ──> ║ (Local/Cloud) ║ ──> ┃   module    ┃ ──> ┃ orchestrate ┃
╰─────────────╯     ┗━━━━━━━━━━━━━━━━━━┛     ╚═══════════════╝     ┗━━━━━━━━━━━━━┛     ┗━━━━━━━━━━━━━┛
                                               │
                                               │ panel_df
                                               ∨
                                             ╭───────────────╮
                                             │  alpha-forge  │
                                             │ (downstream)  │
                                             ╰───────────────╯
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "🏗️ E2E Validation Pipeline Architecture"; flow: east; }
[ Deribit API ] { shape: rounded; }
[ trades_collector ] { border: bold; }
[ ClickHouse ] { label: "ClickHouse\n(Local/Cloud)"; border: double; }
[ validation ] { label: "validation/\nmodule"; border: bold; }
[ mise tasks ] { label: "mise tasks\norchestrate"; border: bold; }
[ alpha-forge ] { label: "alpha-forge\n(downstream)"; shape: rounded; }

[ Deribit API ] -> [ trades_collector ]
[ trades_collector ] -> [ ClickHouse ]
[ ClickHouse ] -> [ validation ]
[ validation ] -> [ mise tasks ]
[ ClickHouse ] -- panel_df --> [ alpha-forge ]
```

</details>

## Implementation

### New Module Structure

```
src/gapless_deribit_clickhouse/
└── validation/
    ├── __init__.py           # Package exports
    ├── infrastructure.py     # Dict auto-create, schema validation
    ├── data_quality.py       # ClickHouse-native quality metrics
    └── reporter.py           # CLI output with mode indicator
```

### New Mise Tasks

```toml
[tasks.validate-infra]
description = "Validate infrastructure (dictionary, schema)"
run = "uv run python -m gapless_deribit_clickhouse.validation.infrastructure"

[tasks.validate-quality]
description = "Generate data quality report"
run = "uv run python -m gapless_deribit_clickhouse.validation.data_quality"

[tasks.validate-full]
description = "Complete validation suite"
depends = ["validate-infra", "validate-quality"]
run = "echo 'Validation complete'"
```

## Consequences

### Positive

- Comprehensive data quality visibility via ClickHouse-native metrics
- Clear mode indication in all CLI output
- Auto-creation reduces dictionary setup friction
- Reusable validation module for tests and plugins
- alpha-forge compatibility via panel_df format

### Negative

- New module adds maintenance overhead
- Auto-creation may mask infrastructure issues in CI/CD

## References

- [Schema Optimization ADR](/docs/adr/2025-12-10-schema-optimization.md)
- [Deribit Options Alpha Features ADR](/docs/adr/2025-12-10-deribit-options-alpha-features.md)
- [ClickHouse Query Optimization](https://clickhouse.com/docs/optimize/query-optimization)
- alpha-forge Plugin Architecture: `~/eon/alpha-forge/packages/alpha-forge-core/`
