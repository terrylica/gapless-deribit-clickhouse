---
adr: 2025-12-07-schema-first-e2e-validation
source: ~/.claude/plans/cozy-gathering-rabbit.md
implementation-status: in_progress
phase: phase-1
last-updated: 2025-12-07
---

# Schema-First E2E Validation - Implementation Spec

**ADR**: [Schema-First E2E Validation ADR](/docs/adr/2025-12-07-schema-first-e2e-validation.md)

## Overview

Add comprehensive real data validation with schema-first architecture, contract tests, and full roundtrip E2E testing following patterns from gapless-network-data.

## Confirmed Decisions

| Decision            | Value                                          |
| ------------------- | ---------------------------------------------- |
| **Task runner**     | `mise tasks` only (in `.mise.toml`)            |
| **Credentials**     | 1Password → `.env` (remove Doppler references) |
| **Contract tests**  | Yes, create `tests/contracts/`                 |
| **E2E data source** | Real Deribit API (history.deribit.com)         |
| **Static checks**   | Add Semgrep + Gitleaks                         |
| **Containers**      | None (local-first)                             |

## Implementation Tasks

### Phase 0: Project Memory

- [ ] Create `CLAUDE.md` with best practices + ITP workflow reference

### Phase 1: Dev Environment Setup

- [ ] Create `.mise.toml` with tasks (test-unit, test-e2e, test-contracts, lint, security)
- [ ] Create `.env.example` with credential template
- [ ] Update `pyproject.toml` with pytest markers (slow, e2e, contracts)

### Phase 2: Credentials Simplification

- [ ] Update `src/gapless_deribit_clickhouse/clickhouse/config.py` (remove Doppler)
- [ ] Verify .env loading works

### Phase 3: Schema-First Architecture

- [ ] Enhance `schema/clickhouse/deribit_trades.yaml` with x-clickhouse, x-pandas extensions
- [ ] Create `src/gapless_deribit_clickhouse/schema/loader.py`
- [ ] Create `src/gapless_deribit_clickhouse/schema/introspector.py`
- [ ] Add mise tasks for schema commands (schema-validate, schema-diff)
- [ ] Create `tests/contracts/test_schema_contracts.py`

### Phase 4: E2E Tests

- [ ] Create `tests/conftest.py` (shared fixtures + factories)
- [ ] Create `tests/e2e/conftest.py` (skip-without-credentials fixtures)
- [ ] Create `tests/e2e/test_full_roundtrip.py`

### Phase 5: Static Analysis

- [ ] Create `.pre-commit-config.yaml` (Semgrep + Gitleaks)
- [ ] Run `mise run security` to verify

## Files to Create/Modify

| File                                                    | Action | Purpose                          |
| ------------------------------------------------------- | ------ | -------------------------------- |
| `CLAUDE.md`                                             | CREATE | Project memory                   |
| `.mise.toml`                                            | CREATE | Task runner config               |
| `.env.example`                                          | CREATE | Credential template              |
| `.pre-commit-config.yaml`                               | CREATE | Semgrep + Gitleaks hooks         |
| `pyproject.toml`                                        | MODIFY | Add pytest markers               |
| `schema/clickhouse/deribit_trades.yaml`                 | MODIFY | Add x-clickhouse, x-pandas       |
| `src/gapless_deribit_clickhouse/schema/__init__.py`     | CREATE | Package init                     |
| `src/gapless_deribit_clickhouse/schema/loader.py`       | CREATE | Parse YAML → Schema object       |
| `src/gapless_deribit_clickhouse/schema/introspector.py` | CREATE | Validate YAML vs live ClickHouse |
| `src/gapless_deribit_clickhouse/clickhouse/config.py`   | MODIFY | Remove Doppler, simplify to .env |
| `tests/conftest.py`                                     | CREATE | Shared fixtures + factories      |
| `tests/contracts/__init__.py`                           | CREATE | Package init                     |
| `tests/contracts/test_schema_contracts.py`              | CREATE | Schema + API + parsing tests     |
| `tests/e2e/__init__.py`                                 | CREATE | Package init                     |
| `tests/e2e/conftest.py`                                 | CREATE | E2E fixtures                     |
| `tests/e2e/test_full_roundtrip.py`                      | CREATE | Real Deribit API tests           |

## Validation Checklist

After implementation, verify:

- [ ] `mise run test-unit` passes (no credentials needed)
- [ ] `mise run test-contracts` passes
- [ ] `mise run test-e2e` passes (with credentials)
- [ ] `mise run security` reports no issues
- [ ] `.env.example` documents all required credentials
- [ ] No Doppler references remain in codebase
- [ ] Contract tests cover schema invariants
- [ ] E2E tests use real Deribit API data

## Success Criteria

1. Schema drift between YAML and live ClickHouse is detectable
2. Contract tests protect architectural invariants
3. E2E tests validate real Deribit API behavior
4. mise tasks provide consistent developer experience
5. All tests can run locally without containers
