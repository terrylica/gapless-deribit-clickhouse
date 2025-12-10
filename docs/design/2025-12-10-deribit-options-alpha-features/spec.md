---
adr: /docs/adr/2025-12-10-deribit-options-alpha-features.md
created: 2025-12-10
status: draft
---

# Design Spec: Deribit Options Alpha Features

**ADR**: [Deribit Options Alpha Features](/docs/adr/2025-12-10-deribit-options-alpha-features.md)

## Overview

Implement ML-ready alpha features from Deribit options trade data for consumption by the `alpha-forge` YAML DSL strategy platform. Phase 1 focuses on IV-based features with 15-minute resampling.

## Technical Decisions

| Decision               | Value                                   | Rationale                                            |
| ---------------------- | --------------------------------------- | ---------------------------------------------------- |
| Resample frequency     | 15-minute                               | Works for 2018-2024 trade density (19-327 trades/hr) |
| EGARCH config          | `vol='EGARCH', p=1, o=1, q=1, dist='t'` | Captures asymmetry + fat tails                       |
| IV Percentile lookback | 90 days                                 | Crypto cycles faster than TradFi                     |
| Risk-free rate         | r = 0.02 (2%)                           | Matches Deribit internal models                      |

## Implementation Tasks

### Task 1: Add mark_price to Schema

**File**: `schema/clickhouse/options_trades.yaml`

Add the `mark_price` field that is available in the Deribit API but not currently collected:

```yaml
mark_price:
  type: ["number", "null"]
  minimum: 0
  description: "Mark price at trade time"
  x-clickhouse:
    type: "Nullable(Float64)"
  x-pandas:
    dtype: "Float64"
```

### Task 2: Update Collector for mark_price

**File**: `src/gapless_deribit_clickhouse/collectors/trades_collector.py`

Update `_trade_to_row()` to extract `mark_price` from API response.

### Task 3: Create Features Module

**Directory**: `src/gapless_deribit_clickhouse/features/`

Create module with the following files:

| File                | Purpose                      |
| ------------------- | ---------------------------- |
| `__init__.py`       | Public API exports           |
| `resampler.py`      | 15-min IV resampling         |
| `iv_percentile.py`  | 90-day rolling IV rank       |
| `term_structure.py` | Near vs far term IV slope    |
| `pcr.py`            | Put-Call Ratio by tenor      |
| `dte_buckets.py`    | DTE aggregations             |
| `egarch.py`         | EGARCH(1,1) volatility model |

### Task 4: Implement Resampler

**File**: `src/gapless_deribit_clickhouse/features/resampler.py`

Resample irregular trade data to 15-minute OHLCV-style IV bars:

```python
def resample_iv(
    df: pd.DataFrame,
    freq: str = "15min",
    agg_cols: dict[str, str] | None = None
) -> pd.DataFrame:
    """
    Resample trade-level IV to regular time series.

    Args:
        df: DataFrame with 'timestamp' and 'iv' columns
        freq: Resample frequency (default: 15min)
        agg_cols: Aggregation mapping (default: OHLC for IV)

    Returns:
        DataFrame with regular timestamps and aggregated IV
    """
```

### Task 5: Implement IV Percentile

**File**: `src/gapless_deribit_clickhouse/features/iv_percentile.py`

90-day rolling IV percentile (IV Rank):

```python
def iv_percentile(
    iv_series: pd.Series,
    lookback_days: int = 90
) -> pd.Series:
    """
    Calculate IV percentile (rank) over rolling window.

    Args:
        iv_series: IV values indexed by timestamp
        lookback_days: Rolling window in days (default: 90)

    Returns:
        Series of percentile values (0-100)
    """
```

### Task 6: Implement Term Structure Slope

**File**: `src/gapless_deribit_clickhouse/features/term_structure.py`

Near-term vs far-term IV differential:

```python
def term_structure_slope(
    df: pd.DataFrame,
    near_dte_max: int = 30,
    far_dte_min: int = 60
) -> pd.Series:
    """
    Calculate term structure slope (IV spread).

    Args:
        df: DataFrame with 'iv' and 'dte' columns
        near_dte_max: Max DTE for near-term bucket
        far_dte_min: Min DTE for far-term bucket

    Returns:
        Series of slope values (near IV - far IV)
    """
```

### Task 7: Implement PCR by Tenor

**File**: `src/gapless_deribit_clickhouse/features/pcr.py`

Put-Call Ratio segmented by expiry tenor:

```python
def pcr_by_tenor(
    df: pd.DataFrame,
    dte_buckets: list[tuple[int, int]] | None = None
) -> pd.DataFrame:
    """
    Calculate Put-Call Ratio by DTE bucket.

    Args:
        df: DataFrame with 'option_type', 'amount', 'dte' columns
        dte_buckets: List of (min_dte, max_dte) tuples
                     Default: [(0,7), (8,14), (15,30), (31,60), (61,90)]

    Returns:
        DataFrame with PCR per bucket per timestamp
    """
```

### Task 8: Implement DTE Bucket Aggregations

**File**: `src/gapless_deribit_clickhouse/features/dte_buckets.py`

Aggregate metrics by days-to-expiry:

```python
def dte_bucket_agg(
    df: pd.DataFrame,
    buckets: list[tuple[int, int]] | None = None,
    metrics: list[str] | None = None
) -> pd.DataFrame:
    """
    Aggregate trade metrics by DTE bucket.

    Args:
        df: DataFrame with trade data
        buckets: DTE bucket definitions
        metrics: Columns to aggregate (default: iv, amount, price)

    Returns:
        DataFrame with aggregated metrics per bucket
    """
```

### Task 9: Implement EGARCH Model

**File**: `src/gapless_deribit_clickhouse/features/egarch.py`

EGARCH(1,1) volatility forecasting on resampled IV:

```python
from arch import arch_model

def fit_egarch(
    iv_series: pd.Series,
    p: int = 1,
    o: int = 1,
    q: int = 1,
    dist: str = "t"
) -> ARCHModelResult:
    """
    Fit EGARCH model to IV series.

    Args:
        iv_series: Resampled IV (must be regular time series)
        p, o, q: EGARCH parameters
        dist: Error distribution ('t' for Student's t)

    Returns:
        Fitted ARCH model result
    """
    model = arch_model(iv_series, vol='EGARCH', p=p, o=o, q=q, dist=dist)
    return model.fit(disp='off')
```

### Task 10: Add mise Tasks

**File**: `.mise.toml`

Add feature-related tasks:

```toml
[tasks.features-generate]
description = "Generate alpha features from options trades"
run = "uv run python -m gapless_deribit_clickhouse.features"

[tasks.features-backfill]
description = "Backfill features for historical data"
run = "uv run python -m gapless_deribit_clickhouse.features --backfill"

[tasks.features-validate]
description = "Validate feature calculations"
run = "uv run pytest tests/features/ -v"
```

## Dependencies

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
features = [
    "arch>=8.0.0",           # EGARCH volatility modeling
    "py-vollib-vectorized",  # Greeks (Phase 2)
]
```

## Testing Strategy

1. **Unit tests**: Each feature function with known inputs/outputs
2. **Contract tests**: Schema validation for feature output
3. **Integration tests**: End-to-end pipeline with sample data

## Success Criteria

- [ ] mark_price field added to schema and collected
- [ ] All 6 feature modules implemented and tested
- [ ] 15-minute resampling works for 2018-2024 data
- [ ] EGARCH model fits successfully on resampled IV
- [ ] mise tasks execute without errors
- [ ] Feature output compatible with alpha-forge consumption

## Future Work (Phase 2)

- Premium-Adjusted Delta for inverse options
- Greeks via py_vollib with r=0.02
- Moneyness features (requires spot price in ClickHouse)
