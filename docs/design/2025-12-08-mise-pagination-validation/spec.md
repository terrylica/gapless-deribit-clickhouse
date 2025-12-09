---
adr: 2025-12-08-mise-pagination-validation
source: ~/.claude/plans/spicy-conjuring-planet.md
implementation-status: in_progress
phase: phase-1
last-updated: 2025-12-08
---

# Design Spec: Mise Integration for Pagination Validation and ClickHouse Management

**ADR**: [Mise Integration for Pagination Validation and ClickHouse Management](/docs/adr/2025-12-08-mise-pagination-validation.md)

## Summary

Add pagination validation to `trades_collector.py` and maximize mise integration by adding ClickHouse to `[tools]`, environment variables to `[env]`, and quality/development tasks.

## Implementation Tasks

### Task 1: Add Tools to mise.toml

**File**: `.mise.toml`

Add to `[tools]` section:

```toml
[tools]
python = "3"
uv = "latest"
clickhouse = "latest"  # NEW: Replaces Homebrew
node = "latest"        # NEW: For semantic-release
```

### Task 2: Add Environment Variables to mise.toml

**File**: `.mise.toml`

Add to `[env]` section:

```toml
[env]
# Existing vars...

# ClickHouse Server Configuration (local development)
CLICKHOUSE_DATA_DIR = "{{config_root}}/tmp/clickhouse/data"
CLICKHOUSE_LOG_DIR = "{{config_root}}/tmp/clickhouse/logs"
CLICKHOUSE_PID_FILE = "{{config_root}}/tmp/clickhouse/clickhouse.pid"

# Pagination Validation Settings
PAGINATION_GAP_THRESHOLD_MS = "1000"
PAGINATION_LOG_WARNINGS = "true"
```

### Task 3: Add ClickHouse Server Management Tasks

**File**: `.mise.toml`

```toml
[tasks.ch-start]
description = "Start local ClickHouse server"
depends = ["_ch-dirs"]
run = """
if [ -f "$CLICKHOUSE_PID_FILE" ] && kill -0 $(cat "$CLICKHOUSE_PID_FILE") 2>/dev/null; then
  echo "✓ ClickHouse already running (PID $(cat $CLICKHOUSE_PID_FILE))"
else
  clickhouse server --daemon \
    --pid-file="$CLICKHOUSE_PID_FILE" \
    --path="$CLICKHOUSE_DATA_DIR" \
    -- --logger.log="$CLICKHOUSE_LOG_DIR/clickhouse-server.log" \
       --logger.errorlog="$CLICKHOUSE_LOG_DIR/clickhouse-server.err.log"
  sleep 2
  curl -s http://localhost:8123/ping && echo "✓ ClickHouse started"
fi
"""

[tasks.ch-stop]
description = "Stop local ClickHouse server"
run = """
if [ -f "$CLICKHOUSE_PID_FILE" ]; then
  kill $(cat "$CLICKHOUSE_PID_FILE") 2>/dev/null && echo "✓ ClickHouse stopped"
  rm -f "$CLICKHOUSE_PID_FILE"
else
  echo "ClickHouse not running"
fi
"""

[tasks.ch-status]
description = "Check ClickHouse server status"
run = 'curl -s http://localhost:8123/ping && echo "✓ ClickHouse running" || echo "❌ ClickHouse not running"'

[tasks.ch-logs]
description = "Tail ClickHouse server logs"
run = "tail -f $CLICKHOUSE_LOG_DIR/clickhouse-server.log"

[tasks._ch-dirs]
description = "Create ClickHouse data directories"
hide = true
run = 'mkdir -p "$CLICKHOUSE_DATA_DIR" "$CLICKHOUSE_LOG_DIR"'
```

### Task 4: Add Quality Tasks

**File**: `.mise.toml`

```toml
[tasks.type-check]
description = "Run mypy type checking"
run = "uv run mypy src/"

[tasks.lint-all]
description = "Run all linting (ruff + mypy)"
depends = ["lint", "type-check"]
run = "echo '✓ All linting passed'"

[tasks.pre-release]
description = "Pre-release validation (lint + tests + security)"
depends = ["lint-all", "test-unit", "test-contracts", "security"]
run = "echo '✓ Ready for release'"

[tasks.dev]
description = "Start development environment"
depends = ["ch-start", "local-init"]
run = "echo '✓ Development environment ready'"
```

### Task 5: Add Pagination Validation Function

**File**: `src/gapless_deribit_clickhouse/collectors/trades_collector.py`

Add new function:

```python
def _validate_page_continuity(
    prev_trades: list[dict[str, Any]],
    curr_trades: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """
    Validate no gaps or duplicates between pagination pages.

    Args:
        prev_trades: Trades from previous page
        curr_trades: Trades from current page

    Returns:
        Tuple of (is_valid, list of warning messages)
    """
    warnings: list[str] = []

    if not prev_trades or not curr_trades:
        return True, warnings

    # Check for timestamp gap
    prev_oldest_ts = min(t["timestamp"] for t in prev_trades)
    curr_newest_ts = max(t["timestamp"] for t in curr_trades)

    # Gap > threshold is suspicious
    gap_threshold = int(os.environ.get("PAGINATION_GAP_THRESHOLD_MS", "1000"))
    gap_ms = prev_oldest_ts - curr_newest_ts
    if gap_ms > gap_threshold:
        warnings.append(f"Gap detected: {gap_ms}ms between pages (threshold: {gap_threshold}ms)")

    # Check for duplicates
    prev_ids = {t["trade_id"] for t in prev_trades}
    curr_ids = {t["trade_id"] for t in curr_trades}
    duplicates = prev_ids & curr_ids
    if duplicates:
        warnings.append(f"Duplicates: {len(duplicates)} trades appear in both pages")

    return len(warnings) == 0, warnings
```

### Task 6: Integrate Validation in Pagination Loop

**File**: `src/gapless_deribit_clickhouse/collectors/trades_collector.py`

Modify `collect_trades()` function:

```python
# Add at start of function
prev_trades: list[dict[str, Any]] = []
pagination_warnings = 0

# Inside while loop, after fetching trades:
trades = result.get("trades", [])
if not trades:
    break

# Validate page continuity
log_warnings = os.environ.get("PAGINATION_LOG_WARNINGS", "true").lower() == "true"
is_valid, warnings = _validate_page_continuity(prev_trades, trades)
if not is_valid and log_warnings:
    for w in warnings:
        logger.warning(f"Pagination issue: {w}")
    pagination_warnings += len(warnings)

prev_trades = trades  # Track for next iteration
```

### Task 7: Add Pagination Metrics to Checkpoint

**File**: `src/gapless_deribit_clickhouse/collectors/trades_collector.py`

Update checkpoint save:

```python
_save_checkpoint(checkpoint_path, {
    "last_end_ts": current_end_ts,
    "batch_number": batch_number,
    "total_collected": total_collected,
    "pagination_warnings": pagination_warnings,  # NEW
    "updated_at": datetime.now().isoformat(),
})
```

### Task 8: Add Unit Tests for Pagination Validation

**File**: `tests/unit/test_pagination_validation.py`

```python
"""Unit tests for pagination validation."""

import pytest
from gapless_deribit_clickhouse.collectors.trades_collector import _validate_page_continuity


class TestValidatePageContinuity:
    """Tests for _validate_page_continuity function."""

    def test_empty_pages_valid(self):
        """Empty pages should be valid."""
        is_valid, warnings = _validate_page_continuity([], [])
        assert is_valid
        assert not warnings

    def test_continuous_pages_valid(self):
        """Continuous pages with no gap should be valid."""
        prev = [{"trade_id": "1", "timestamp": 1000}]
        curr = [{"trade_id": "2", "timestamp": 999}]
        is_valid, warnings = _validate_page_continuity(prev, curr)
        assert is_valid
        assert not warnings

    def test_gap_detected(self):
        """Gap larger than threshold should be detected."""
        prev = [{"trade_id": "1", "timestamp": 5000}]
        curr = [{"trade_id": "2", "timestamp": 1000}]  # 4000ms gap
        is_valid, warnings = _validate_page_continuity(prev, curr)
        assert not is_valid
        assert len(warnings) == 1
        assert "Gap detected" in warnings[0]

    def test_duplicates_detected(self):
        """Duplicate trade_ids should be detected."""
        prev = [{"trade_id": "1", "timestamp": 1000}]
        curr = [{"trade_id": "1", "timestamp": 999}]  # Same trade_id
        is_valid, warnings = _validate_page_continuity(prev, curr)
        assert not is_valid
        assert len(warnings) == 1
        assert "Duplicates" in warnings[0]
```

## Critical Files

| Priority | File                                       | Change                                                                |
| -------- | ------------------------------------------ | --------------------------------------------------------------------- |
| 1        | `.mise.toml`                               | Add clickhouse, node to [tools]; env vars; ch-\* tasks; quality tasks |
| 2        | `src/.../collectors/trades_collector.py`   | Add `_validate_page_continuity()`, integrate in loop                  |
| 3        | `tests/unit/test_pagination_validation.py` | Unit tests for validation                                             |

## Verification

```bash
# 1. Install tools via mise
mise install

# 2. Start local ClickHouse
mise run ch-start

# 3. Verify server running
mise run ch-status

# 4. Run unit tests
mise run test-unit

# 5. Run full development setup
mise run dev

# 6. Run pre-release checks
mise run pre-release
```

## Success Criteria

- [ ] `mise install` installs clickhouse and node
- [ ] `mise run ch-start` starts local ClickHouse
- [ ] `mise run ch-status` shows running status
- [ ] `mise run type-check` passes
- [ ] `mise run lint-all` passes
- [ ] `mise run test-unit` passes (including pagination validation tests)
- [ ] `mise run dev` sets up complete development environment
- [ ] `mise run pre-release` passes all checks
