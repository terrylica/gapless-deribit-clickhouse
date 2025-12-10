---
status: accepted
date: 2025-12-10
decision-maker: Terry Li
consulted:
  [
    Package-Validation-Agent,
    Options-Alpha-Research-Agent,
    Inverse-Options-Research-Agent,
    Data-Availability-Agent,
  ]
research-method: 9-agent-parallel-dctl
clarification-iterations: 5
perspectives:
  [
    DataEngineering,
    QuantitativeFinance,
    MLFeatureEngineering,
    SystemArchitecture,
  ]
---

# ADR: Deribit Options Alpha Features for Binance Futures Trading

**Design Spec**: [Implementation Spec](/docs/design/2025-12-10-deribit-options-alpha-features/spec.md)

## Context and Problem Statement

The `gapless-deribit-clickhouse` project collects Deribit options trade data (2018-present) with fields including IV, price, amount, direction, index_price, strike, expiry, and option_type. This data has high alpha potential for predicting Binance Futures price movements, but currently exists as raw trade records without derived features.

The problem: How do we transform raw options trade data into ML-ready alpha features that can be consumed by the `alpha-forge` YAML DSL strategy platform?

### Before/After

**Before**: Raw trade data with no derived features

```
  ⏮️ Before: Raw Trade Data

╭────────────────────────────╮
│        Deribit API         │
╰────────────────────────────╯
  │
  │
  ∨
┌────────────────────────────┐
│ gapless-deribit-clickhouse │
└────────────────────────────┘
  │
  │
  ∨
┌────────────────────────────┐
│         ClickHouse         │
│       options_trades       │
└────────────────────────────┘
  │
  │
  ∨
┌⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯┐
⋮         Raw trades         ⋮
⋮       (no features)        ⋮
└⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯⋯┘
```

<details>
<summary>graph-easy source (Before)</summary>

```
graph { label: "⏮️ Before: Raw Trade Data"; flow: south; }
[Deribit API] { shape: rounded; }
[gapless-deribit-clickhouse]
[ClickHouse\noptions_trades]
[Raw trades\n(no features)] { border: dotted; }

[Deribit API] -> [gapless-deribit-clickhouse]
[gapless-deribit-clickhouse] -> [ClickHouse\noptions_trades]
[ClickHouse\noptions_trades] -> [Raw trades\n(no features)]
```

</details>

**After**: ML-ready alpha features via feature engine

```
⏭️ After: ML-Ready Alpha Features

   ╭────────────────────────────╮
   │        Deribit API         │
   ╰────────────────────────────╯
     │
     │
     ∨
   ┌────────────────────────────┐
   │ gapless-deribit-clickhouse │
   └────────────────────────────┘
     │
     │
     ∨
   ┌────────────────────────────┐
   │         ClickHouse         │
   │       options_trades       │
   └────────────────────────────┘
     │
     │
     ∨
   ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
   ┃      features/ module      ┃
   ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
     │
     │
     ∨
   ┌────────────────────────────┐
   │      15-min Resampler      │
   └────────────────────────────┘
     │
     │
     ∨
   ╭────────────────────────────╮
   │        alpha-forge         │
   │          YAML DSL          │
   ╰────────────────────────────╯
```

<details>
<summary>graph-easy source (After)</summary>

```
graph { label: "⏭️ After: ML-Ready Alpha Features"; flow: south; }
[Deribit API] { shape: rounded; }
[gapless-deribit-clickhouse]
[ClickHouse\noptions_trades]
[features/ module] { border: bold; }
[15-min Resampler]
[alpha-forge\nYAML DSL] { shape: rounded; }

[Deribit API] -> [gapless-deribit-clickhouse]
[gapless-deribit-clickhouse] -> [ClickHouse\noptions_trades]
[ClickHouse\noptions_trades] -> [features/ module]
[features/ module] -> [15-min Resampler]
[15-min Resampler] -> [alpha-forge\nYAML DSL]
```

</details>

## Research Summary

| Agent Perspective        | Key Finding                                                                                                | Confidence |
| ------------------------ | ---------------------------------------------------------------------------------------------------------- | ---------- |
| Package-Validation       | py_vollib works for Greeks; arch v8.0.0 EGARCH requires regular time series                                | High       |
| Options-Alpha-Research   | PCR is lagging (not predictive); IV percentile and term structure have alpha                               | High       |
| Inverse-Options-Research | Premium-Adjusted Delta reduces error from 5-20% to 2-5% for Deribit inverse options                        | High       |
| Data-Availability        | All critical fields (iv, index_price) have 0% null rate since 2018; mark_price available but not collected | High       |

### Data Availability Validation

All critical fields have been consistently available since July 2018 with 0% null rate:

| API Field     | 2018-2024 | In Schema? | Status            |
| ------------- | --------- | ---------- | ----------------- |
| `iv`          | 0% null   | Yes        | Collected         |
| `index_price` | 0% null   | Yes        | Collected         |
| `mark_price`  | 0% null   | **No**     | **ADD TO SCHEMA** |

### Trade Frequency Analysis

| Period   | Trades/Hour | Feasible Resample |
| -------- | ----------- | ----------------- |
| Dec 2024 | 327         | 1-minute          |
| Jan 2021 | 42          | 5-minute          |
| Jan 2020 | 19          | 15-minute minimum |

## Decision Log

| Decision Area          | Options Evaluated                           | Chosen              | Rationale                                     |
| ---------------------- | ------------------------------------------- | ------------------- | --------------------------------------------- |
| Resample Frequency     | 1-min, 5-min, 15-min                        | 15-minute           | Works for all years (2018-2024 trade density) |
| Volatility Model       | GARCH, GJR-GARCH, EGARCH                    | EGARCH(1,1)         | Captures asymmetry + fat tails in crypto      |
| IV Percentile Lookback | 30d, 60d, 90d, 252d                         | 90 days             | Crypto cycles faster than TradFi              |
| Risk-free Rate         | 0%, 2%, 5%                                  | r = 0.02 (2%)       | Matches Deribit internal models               |
| Greeks Implementation  | Phase 1, Phase 2, Skip                      | Deferred to Phase 2 | Waiting for spot price in ClickHouse          |
| PCR Usage              | Predictive signal, Sentiment gauge, Exclude | Sentiment gauge     | Research shows PCR is lagging indicator       |

### Trade-offs Accepted

| Trade-off                        | Choice         | Accepted Cost                              |
| -------------------------------- | -------------- | ------------------------------------------ |
| Resample granularity vs coverage | 15-min         | Lose intraday microstructure for 2020 data |
| Greeks now vs later              | Defer          | No delta/gamma features until Phase 2      |
| PCR as signal                    | Sentiment only | Not used for directional prediction        |

## Decision Drivers

- **Data consistency**: Features must work across entire 2018-2024 dataset
- **arch package constraint**: Requires regular time series (no irregular trade timestamps)
- **Alpha-forge integration**: Features consumed via YAML DSL
- **Incremental delivery**: Phase 1 IV-only, Phase 2 adds Greeks when spot available

## Considered Options

- **Option A**: Real-time feature computation from raw trades
  - Pros: Maximum granularity, no data loss
  - Cons: arch can't handle irregular timestamps, inconsistent across years

- **Option B**: 15-minute IV resampling with EGARCH volatility model
  - Pros: Works 2018-2024, arch-compatible, proven in research
  - Cons: Loses some microstructure detail

- **Option C**: Daily aggregations only
  - Pros: Simplest implementation, always sufficient data
  - Cons: Loses intraday alpha, too coarse for trading signals

## Decision Outcome

Chosen option: **Option B** (15-minute IV resampling with EGARCH), because:

1. Research validated 15-min works across all historical periods (19-327 trades/hour)
2. EGARCH(1,1) with Student's t distribution outperforms symmetric GARCH for crypto
3. Maintains sufficient granularity for alpha-forge strategy signals
4. Compatible with arch package requirements for regular time series

## Synthesis

**Convergent findings**: All agents agreed on EGARCH superiority for crypto, 15-min as safe resample frequency, and mark_price collection gap.

**Divergent findings**: Package-Validation agent initially suggested 5-min; Data-Availability agent's trade frequency analysis showed 15-min necessary for 2020 coverage.

**Resolution**: User chose conservative 15-min to ensure full historical backtesting capability.

## Consequences

### Positive

- ML-ready features for alpha-forge consumption
- Full 2018-2024 backtesting support
- EGARCH captures crypto-specific volatility dynamics
- Modular feature engine enables incremental enhancement

### Negative

- 15-min granularity loses some microstructure signals
- Greeks deferred until spot price available in ClickHouse
- Requires mark_price schema addition and potential re-backfill

## Architecture

```
🏗️ Alpha Feature Architecture

┌────────────────┐     ┏━━━━━━━━━━━┓     ╔══════════╗     ╭─────────────╮
│   ClickHouse   │     ┃ Resampler ┃     ║ Features ║     │ alpha-forge │
│ options_trades │ ──> ┃  15-min   ┃ ──> ║          ║ ──> │             │
└────────────────┘     ┗━━━━━━━━━━━┛     ╚══════════╝     ╰─────────────╯
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "🏗️ Alpha Feature Architecture"; flow: east; }

[ClickHouse\noptions_trades]
[Resampler\n15-min] { border: bold; }
[Features] { border: double; }
[alpha-forge] { shape: rounded; }

[ClickHouse\noptions_trades] -> [Resampler\n15-min]
[Resampler\n15-min] -> [Features]
[Features] -> [alpha-forge]
```

</details>

### Feature Components

| Component          | Description               | Output               |
| ------------------ | ------------------------- | -------------------- |
| **Resampler**      | 15-minute IV aggregation  | Regular time series  |
| **IV Percentile**  | 90-day rolling rank       | 0-100 percentile     |
| **Term Structure** | Near vs far IV slope      | Spread value         |
| **PCR**            | Put-Call Ratio by tenor   | Ratio per DTE bucket |
| **DTE Buckets**    | 0-7d, 8-14d, 15-30d, 31+d | Aggregated metrics   |
| **EGARCH(1,1)**    | Volatility forecast       | Conditional variance |

## Implementation Phases

### Phase 1: IV-Only Features (Current Scope)

1. Add `mark_price` to schema YAML
2. Create `features/` module with resampler
3. Implement IV Percentile (90-day rolling)
4. Implement Term Structure Slope
5. Implement PCR by Expiry Tenor
6. Implement DTE Bucket Aggregations
7. Implement EGARCH(1,1) on resampled IV
8. Add mise tasks for features

### Phase 2: Greeks & Spot Integration (Future)

- Premium-Adjusted Delta: `inverse_delta = bs_delta - (option_price / spot_price)`
- Additional Greeks (Gamma, Vega) via py_vollib with r=0.02
- Moneyness Features using spot price

### Phase 3: alpha-forge Integration (Future)

- Create alpha-forge plugin structure
- Define YAML DSL feature references
- Implement feature fetcher for ClickHouse queries

## References

- [Trades-Only Architecture Pivot ADR](/docs/adr/2025-12-05-trades-only-architecture-pivot.md)
- [Carol Alexander et al. 2023 - Inverse Options](https://arxiv.org/pdf/2107.12041)
- [arch package documentation](https://arch.readthedocs.io/)
- [py-vollib-vectorized](https://pypi.org/project/py-vollib-vectorized/)
