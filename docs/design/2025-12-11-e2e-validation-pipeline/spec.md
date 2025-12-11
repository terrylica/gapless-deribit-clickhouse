---
adr: 2025-12-11-e2e-validation-pipeline
source: ~/.claude/plans/lazy-rolling-naur.md
implementation-status: completed
phase: phase-1
last-updated: 2025-12-11
---

# Design Spec: E2E Validation Pipeline

**ADR**: [E2E Validation Pipeline](/docs/adr/2025-12-11-e2e-validation-pipeline.md)

## Overview

Create a validation module for the `gapless-deribit-clickhouse` pipeline that provides:

1. Infrastructure validation with auto-creation of dictionaries
2. ClickHouse-native data quality metrics
3. CLI output with mode indicator (local/cloud)
4. mise task orchestration

## Success Criteria

- [x] `validation/infrastructure.py` auto-creates `spot_prices_dict` if missing
- [x] `validation/data_quality.py` computes metrics server-side (no pandas)
- [x] `validation/reporter.py` shows `[LOCAL]` or `[CLOUD]` in output
- [x] `mise run validate-pipeline` runs complete validation suite
- [x] Tests pass for all validation modules (31 tests)

---

## Implementation Tasks

### Task 1: Create validation package structure

**Files**:

- `src/gapless_deribit_clickhouse/validation/__init__.py`
- `src/gapless_deribit_clickhouse/validation/infrastructure.py`
- `src/gapless_deribit_clickhouse/validation/data_quality.py`
- `src/gapless_deribit_clickhouse/validation/reporter.py`

### Task 2: Implement infrastructure.py

**Functions**:

```python
def ensure_spot_dictionary(client: Client, auto_create: bool = True) -> bool:
    """Check and optionally create spot_prices_dict."""

def validate_schema_version(client: Client) -> dict:
    """Validate schema has v3.0.0 optimizations (ORDER BY, LowCardinality)."""

def get_mode_indicator() -> str:
    """Return [LOCAL] or [CLOUD] based on CLICKHOUSE_MODE env var."""

def get_connection_info() -> dict:
    """Return connection details for current mode."""
```

**Key Implementation Details**:

- Reuse `SPOT_DICT_DDL` from `spot_provider.py`
- Use `system.columns` to validate schema structure
- Read `CLICKHOUSE_MODE` env var (default: "local")

### Task 3: Implement data_quality.py

**Functions**:

```python
def get_quality_metrics(
    client: Client,
    start: str | None = None,
    end: str | None = None,
    database: str = "deribit",
    table: str = "options_trades",
) -> dict:
    """Get data quality metrics computed server-side."""

def get_gap_analysis(
    client: Client,
    threshold_hours: int = 4,
) -> list[dict]:
    """Find gaps in data larger than threshold."""

def get_coverage_stats(
    client: Client,
    underlying: str = "BTC",
) -> dict:
    """Get coverage statistics (null rates, date range)."""
```

**Key Queries**:

```sql
-- Quality metrics (server-side aggregation)
SELECT
    count() AS total_rows,
    uniqExact(trade_id) AS unique_trades,
    min(timestamp) AS earliest,
    max(timestamp) AS latest,
    dateDiff('day', min(timestamp), max(timestamp)) AS date_span_days,
    countIf(iv IS NULL OR iv = 0) AS null_iv_count,
    countIf(index_price IS NULL OR index_price = 0) AS null_index_count,
    count() / nullIf(dateDiff('hour', min(timestamp), max(timestamp)), 0) AS avg_trades_per_hour
FROM deribit.options_trades

-- Gap analysis
WITH sorted AS (
    SELECT timestamp, lead(timestamp) OVER (ORDER BY timestamp) AS next_ts
    FROM deribit.options_trades
)
SELECT
    timestamp AS gap_start,
    next_ts AS gap_end,
    dateDiff('hour', timestamp, next_ts) AS gap_hours
FROM sorted
WHERE dateDiff('hour', timestamp, next_ts) > {threshold}
ORDER BY gap_hours DESC
```

### Task 4: Implement reporter.py

**Functions**:

```python
def format_validation_report(
    infra_status: dict,
    quality_metrics: dict,
    mode: str,
) -> str:
    """Generate formatted validation report."""

def print_validation_summary(
    client: Client,
    verbose: bool = False,
) -> None:
    """Print validation summary to stdout."""
```

**Output Example** (text format with Unicode borders):

The report shows mode indicator in header, infrastructure status, and data quality metrics.
See `reporter.py` implementation for exact format.

### Task 5: Update mise tasks

**Add to `.mise.toml`**:

```toml
[tasks.validate-infra]
description = "Validate infrastructure (dictionary, schema)"
run = "uv run python -m gapless_deribit_clickhouse.validation.infrastructure"

[tasks.validate-quality]
description = "Generate data quality report"
run = "uv run python -m gapless_deribit_clickhouse.validation.data_quality"

[tasks.validate-report]
description = "Print validation report"
run = "uv run python -m gapless_deribit_clickhouse.validation.reporter"

[tasks.validate-full]
description = "Complete validation suite"
depends = ["validate-infra", "validate-quality", "validate-report"]
```

### Task 6: Add validation tests

**Files**:

- `tests/validation/__init__.py`
- `tests/validation/test_infrastructure.py`
- `tests/validation/test_data_quality.py`
- `tests/validation/test_reporter.py`

**Test Coverage**:

- `test_ensure_spot_dictionary_creates_if_missing()`
- `test_get_mode_indicator_local()`
- `test_get_mode_indicator_cloud()`
- `test_get_quality_metrics_returns_all_fields()`
- `test_format_validation_report_includes_mode()`

---

## Dependencies

No new dependencies required. Uses existing:

- `clickhouse-connect` (already in dependencies)
- `os` (stdlib)
- `typing` (stdlib)

---

## Out of Scope (Phase B/C)

- Contract selector module (`features/contract_selector.py`)
- Moneyness features (`features/moneyness.py`)
- Greeks calculation (`features/greeks.py`)
- alpha-forge plugin integration

These are documented in the global plan and will be separate ADRs.

---

## References

- [E2E Validation Pipeline ADR](/docs/adr/2025-12-11-e2e-validation-pipeline.md)
- [Schema Optimization ADR](/docs/adr/2025-12-10-schema-optimization.md)
- [Global Plan](~/.claude/plans/lazy-rolling-naur.md)
