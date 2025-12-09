---
adr: 2025-12-08-clickhouse-data-pipeline-architecture
source: ~/.claude/plans/spicy-conjuring-planet.md
implementation-status: complete
phase: phase-2
last-updated: 2025-12-08
---

# Design Spec: ClickHouse Cloud Data Pipeline Architecture + PoC

**ADR**: [ClickHouse Cloud Data Pipeline Architecture](/docs/adr/2025-12-08-clickhouse-data-pipeline-architecture.md)

## Summary

Document architecture decision for ClickHouse Cloud data ingestion from Deribit API, implement proof-of-concept with actual cost measurement via AWS and ClickHouse Cloud billing APIs. Includes **dual-mode architecture** (local + cloud) for cost-efficient backtesting.

**Key Findings**:

- ClickHouse Cloud **cannot** pull from REST APIs natively - requires intermediary
- **On-demand batch is 83% cheaper** than continuous with NO performance penalty
- **Egress is expensive** ($0.115/GB) while **ingress is FREE** - but **intra-region is FREE**
- AWS Batch + EC2 Spot for backfill (~$1.50) + Lambda for incremental (~$0.18/month)
- **Dual-mode**: Local ClickHouse for backtesting (FREE) + Cloud for production

**Current Configuration**:

- **ClickHouse Cloud Region**: `us-west-2` (AWS Oregon)
- **Host**: `ebmf8f35lu.us-west-2.aws.clickhouse.cloud`
- **Recommendation**: Deploy ALL AWS resources (Lambda, EC2) in `us-west-2` for FREE egress

---

## Implementation Tasks

### Task 1: Add mise Environment Variables

**File**: `.mise.toml`

```toml
[env]
# ClickHouse Cloud Region (for AWS resource deployment)
CLICKHOUSE_CLOUD_REGION = "us-west-2"
AWS_DEFAULT_REGION = "us-west-2"

# Mode selection: "local" or "cloud"
CLICKHOUSE_MODE = "cloud"

# Local ClickHouse (when CLICKHOUSE_MODE=local)
CLICKHOUSE_LOCAL_HOST = "localhost"
CLICKHOUSE_LOCAL_PORT = "9000"
```

### Task 2: Create Dual-Mode Connection Factory

**File**: `src/gapless_deribit_clickhouse/clickhouse/connection.py`

```python
def get_client(mode: str | None = None) -> Client:
    """Get ClickHouse client based on mode (local or cloud)."""
    mode = mode or os.getenv("CLICKHOUSE_MODE", "cloud")

    if mode == "local":
        return clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_LOCAL_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_LOCAL_PORT", "9000")),
            user="default",
            password=""
        )
    else:
        return _get_cloud_client()  # Existing implementation
```

### Task 3: Add Billing Module

**Files**:

- `src/gapless_deribit_clickhouse/billing/__init__.py`
- `src/gapless_deribit_clickhouse/billing/clickhouse_cloud.py`
- `src/gapless_deribit_clickhouse/billing/aws_cost_explorer.py`

### Task 4: Add Cost Measurement Scripts

**Files**:

- `scripts/measure_baseline_costs.py`
- `scripts/monitor_egress.py`
- `scripts/poc_backfill.py`

### Task 5: Add mise Tasks for Dual-Mode Orchestration

**File**: `.mise.toml`

```toml
[tasks.local-init]
description = "Initialize local ClickHouse with same schema as cloud"
env = { CLICKHOUSE_MODE = "local" }
depends = ["_check-local-server"]
run = "uv run python -m gapless_deribit_clickhouse.schema.cli init"

[tasks.local-validate]
description = "Validate local schema matches YAML"
env = { CLICKHOUSE_MODE = "local" }
run = "uv run python -m gapless_deribit_clickhouse.schema.cli validate"

[tasks.cloud-validate]
description = "Validate cloud schema matches YAML"
env = { CLICKHOUSE_MODE = "cloud" }
run = "uv run python -m gapless_deribit_clickhouse.schema.cli validate"

[tasks.schema-align]
description = "Verify local and cloud schemas are aligned"
depends = ["local-validate", "cloud-validate"]
run = "echo '✓ Local and cloud schemas aligned with YAML SSoT'"

[tasks.e2e-validate]
description = "E2E validation: collect real Deribit data to local ClickHouse"
depends = ["local-init", "_check-local-server"]
run = "uv run python scripts/e2e_validate.py"

[tasks.measure-volume]
description = "Measure actual Deribit data volume for 1 day"
run = "uv run python scripts/measure_volume.py"

[tasks._check-local-server]
description = "Verify local ClickHouse is running"
hide = true
run = """
curl -s http://localhost:8123/ping > /dev/null 2>&1 || {
  echo "❌ Local ClickHouse not running. Start with: clickhouse server"
  exit 1
}
echo "✓ Local ClickHouse running"
"""
```

### Task 6: Add Idempotency to collect_trades()

**File**: `src/gapless_deribit_clickhouse/collectors/trades_collector.py`

Changes:

- Add `insert_deduplication_token` per batch
- Add checkpoint file for resumable backfills
- Add progress tracking

---

## Critical Files

| Priority | File                                                            | Change                           |
| -------- | --------------------------------------------------------------- | -------------------------------- |
| 1        | `.mise.toml`                                                    | Add region + mode env vars       |
| 2        | `src/gapless_deribit_clickhouse/clickhouse/connection.py`       | Add dual-mode connection factory |
| 3        | `src/gapless_deribit_clickhouse/billing/__init__.py`            | Billing module init              |
| 4        | `src/gapless_deribit_clickhouse/billing/clickhouse_cloud.py`    | ClickHouse Billing API client    |
| 5        | `src/gapless_deribit_clickhouse/billing/aws_cost_explorer.py`   | AWS Cost Explorer client         |
| 6        | `scripts/measure_baseline_costs.py`                             | Baseline measurement             |
| 7        | `scripts/poc_backfill.py`                                       | Backfill PoC script              |
| 8        | `src/gapless_deribit_clickhouse/collectors/trades_collector.py` | Add idempotency                  |

---

## Verification Checklist

**All validations use REAL data - no mocks or fakes**

### Infrastructure Setup

| Step | Command                          | Validates                           |
| ---- | -------------------------------- | ----------------------------------- |
| 1    | `brew install --cask clickhouse` | Local ClickHouse installed          |
| 2    | `clickhouse server &`            | Local server running                |
| 3    | `curl localhost:8123/ping`       | Local HTTP interface responds "Ok." |
| 4    | `mise run local-init`            | Schema created locally              |

### Data Pipeline Validation (Real Data)

| Step | Command                   | Validates                         |
| ---- | ------------------------- | --------------------------------- |
| 1    | `mise run measure-volume` | Real Deribit API accessible       |
| 2    | `mise run e2e-validate`   | Full pipeline: Deribit → local CH |
| 3    | `mise run local-validate` | Local schema matches YAML SSoT    |
| 4    | `mise run cloud-validate` | Cloud schema matches YAML SSoT    |
| 5    | `mise run schema-align`   | Both environments aligned         |

### Production Readiness

- [ ] Local ClickHouse installed and running
- [ ] `.mise.toml` has region + mode env vars
- [ ] `CLICKHOUSE_CLOUD_REGION=us-west-2` configured
- [ ] `mise run e2e-validate` passes
- [ ] `mise run schema-align` passes
- [ ] Cost baseline documented
