---
status: accepted
date: 2025-12-08
decision-maker: Terry Li
consulted: [Explore-Agent]
research-method: single-agent
clarification-iterations: 5
perspectives: [UpstreamIntegration, OperationalService, LifecycleMigration]
---

# ADR: ClickHouse Cloud Data Pipeline Architecture with Dual-Mode Support

**Design Spec**: [Implementation Spec](/docs/design/2025-12-08-clickhouse-data-pipeline-architecture/spec.md)

## Context and Problem Statement

The gapless-deribit-clickhouse project needs to ingest historical options trade data from Deribit REST API into ClickHouse Cloud. The key question is whether ClickHouse Cloud can proactively pull data from REST APIs, or if an intermediary is required.

Additionally, development and backtesting workflows incur unnecessary cloud costs when iterating locally. A dual-mode architecture (local ClickHouse for development, cloud for production) would eliminate these costs while maintaining schema alignment.

### Before/After

```
 ⏮️ Before: Cloud-Only Development

        ╭──────────────────╮
        │   Development    │
        ╰──────────────────╯
          │
          │
          ∨
        ┌──────────────────┐
        │ ClickHouse Cloud │
        │ ($31/mo compute) │
        └──────────────────┘
          ∧
          │
          │
        ┌──────────────────┐
        │    Production    │
        └──────────────────┘
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "⏮️ Before: Cloud-Only Development"; flow: south; }
[ Development ] { shape: rounded; }
[ ClickHouse Cloud\n($31/mo compute) ]
[ Production ]
[ Development ] -> [ ClickHouse Cloud\n($31/mo compute) ]
[ Production ] -> [ ClickHouse Cloud\n($31/mo compute) ]
```

</details>

```
          ⏭️ After: Dual-Mode Architecture

                                  ╭──────────────────╮
                                  │   Development    │
                                  ╰──────────────────╯
                                    │
                                    │
                                    ∨
╔══════════════════╗              ┏━━━━━━━━━━━━━━━━━━┓
║ YAML Schema SSoT ║  validates   ┃ Local ClickHouse ┃
║                  ║ ───────────> ┃   ($0 - FREE)    ┃
╚══════════════════╝              ┗━━━━━━━━━━━━━━━━━━┛
  │
  │
  │
  │                               ╭──────────────────╮
  │                               │    Production    │
  │                               ╰──────────────────╯
  │                                 │
  │                                 │
  │                                 ∨
  │                               ┌──────────────────┐
  │                  validates    │ ClickHouse Cloud │
  └─────────────────────────────> │     ($32/mo)     │
                                  └──────────────────┘
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "⏭️ After: Dual-Mode Architecture"; flow: south; }
[ Development ] { shape: rounded; }
[ Local ClickHouse\n($0 - FREE) ] { border: bold; }
[ Production ] { shape: rounded; }
[ ClickHouse Cloud\n($32/mo) ]
[ YAML Schema SSoT ] { border: double; }
[ Development ] -> [ Local ClickHouse\n($0 - FREE) ]
[ Production ] -> [ ClickHouse Cloud\n($32/mo) ]
[ YAML Schema SSoT ] -- validates --> [ Local ClickHouse\n($0 - FREE) ]
[ YAML Schema SSoT ] -- validates --> [ ClickHouse Cloud\n($32/mo) ]
```

</details>

## Research Summary

| Agent Perspective | Key Finding                                                     | Confidence |
| ----------------- | --------------------------------------------------------------- | ---------- |
| Explore (CH docs) | ClickHouse Cloud cannot pull from REST APIs natively            | High       |
| Explore (pricing) | On-demand batch is 83% cheaper than continuous ($32/mo vs $191) | High       |
| Explore (egress)  | Intra-region AWS egress is FREE; public internet is $0.115/GB   | High       |
| Explore (region)  | Current ClickHouse Cloud instance is in us-west-2               | High       |
| Explore (schema)  | Existing YAML schema architecture exceeds most commercial tools | High       |

## Decision Log

| Decision Area       | Options Evaluated                 | Chosen           | Rationale                                  |
| ------------------- | --------------------------------- | ---------------- | ------------------------------------------ |
| Ingestion method    | ClickHouse pull, AWS intermediary | AWS intermediary | ClickHouse cannot pull from REST APIs      |
| Compute pattern     | Continuous 24/7, On-demand batch  | On-demand batch  | 83% cost savings, no performance penalty   |
| AWS resources       | Lambda, EC2 Spot, Batch           | Lambda + Batch   | Lambda for incremental, Batch for backfill |
| Egress optimization | Public, Intra-region              | Intra-region     | Deploy in us-west-2 for FREE egress        |
| Development mode    | Cloud only, Dual-mode             | Dual-mode        | Local for dev ($0), Cloud for production   |
| Checkpoint          | DynamoDB, Local JSON file         | Local JSON file  | Simpler, no additional infrastructure      |

### Trade-offs Accepted

| Trade-off              | Choice                | Accepted Cost                              |
| ---------------------- | --------------------- | ------------------------------------------ |
| Simplicity vs features | Local JSON checkpoint | No distributed checkpoint, manual recovery |
| Cost vs latency        | On-demand batch       | 20-30 second cold start after idle         |

## Decision Drivers

- ClickHouse Cloud cannot pull from REST APIs (Deribit) natively
- Cost optimization is critical ($32/mo target vs $191/mo continuous)
- Development iteration should be FREE (local mode)
- Existing YAML schema architecture should be leveraged
- All AWS resources must deploy in us-west-2 for FREE egress

## Considered Options

- **Option A**: Continuous 24/7 ingestion with ClickPipes
- **Option B**: AWS Lambda + Batch intermediary with on-demand pattern
- **Option C**: Local-only architecture (no cloud)

## Decision Outcome

Chosen option: **Option B**, because:

1. ClickHouse Cloud cannot pull from REST APIs - intermediary required
2. On-demand batch pattern saves 83% on costs
3. Dual-mode architecture eliminates development costs entirely
4. Existing schema infrastructure can validate both environments
5. us-west-2 deployment ensures FREE intra-region egress

## Synthesis

**Convergent findings**: All research confirmed ClickHouse cannot pull from REST APIs and that on-demand batch is significantly cheaper.

**Divergent findings**: Initial plan mentioned ClickPipes which is irrelevant for REST API sources.

**Resolution**: Removed all ClickPipes references, focused on AWS Lambda/Batch as the only viable intermediary.

## Consequences

### Positive

- 83% cost savings ($32/mo vs $191/mo)
- FREE development/backtesting with local ClickHouse
- Schema alignment validation between environments
- FREE egress for AWS us-west-2 resources

### Negative

- Requires local ClickHouse installation for development
- Cold start of 20-30 seconds after idle periods
- Manual checkpoint recovery if backfill fails

## Architecture

```
                        🏗️ Data Pipeline Architecture

╭─────────────╮         ┌─────────────────┐                ╔══════════════════╗
│ Deribit API │  REST   │   AWS Lambda    │  FREE egress   ║ ClickHouse Cloud ║
│             │ ──────> │    us-west-2    │ ─────────────> ║    us-west-2     ║
╰─────────────╯         └─────────────────┘                ╚══════════════════╝
                          │
                          │ state
                          ∨
                        ┌─────────────────┐
                        │ JSON Checkpoint │
                        └─────────────────┘
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "🏗️ Data Pipeline Architecture"; flow: east; }
[ Deribit API ] { shape: rounded; }
[ AWS Lambda\nus-west-2 ]
[ ClickHouse Cloud\nus-west-2 ] { border: double; }
[ JSON Checkpoint ]
[ Deribit API ] -- REST --> [ AWS Lambda\nus-west-2 ]
[ AWS Lambda\nus-west-2 ] -- FREE egress --> [ ClickHouse Cloud\nus-west-2 ]
[ AWS Lambda\nus-west-2 ] -- state --> [ JSON Checkpoint ]
```

</details>

## References

- [Schema-First E2E Validation ADR](/docs/adr/2025-12-07-schema-first-e2e-validation.md)
- [ClickHouse Cloud Pricing](https://clickhouse.com/pricing)
- [AWS Data Transfer Pricing](https://aws.amazon.com/ec2/pricing/on-demand/#Data_Transfer)
