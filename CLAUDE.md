# gapless-deribit-clickhouse Project Memory

## Preferred Tools

| Category               | Tool                         | Avoid                         |
| ---------------------- | ---------------------------- | ----------------------------- |
| **Task runner**        | `mise tasks` (`.mise.toml`)  | Make, just, Taskfile, Earthly |
| **Python**             | `uv` (management, execution) | pip, conda, poetry            |
| **Version management** | `mise` for tool versions     | asdf, nvm, pyenv              |
| **Static analysis**    | Semgrep, Gitleaks            | ESLint (for Python)           |
| **Containers**         | Local-first (avoid)          | Docker Compose, Earthly       |
| **CI/CD**              | Local-first                  | GitHub Actions for tests      |

## Schema-First Architecture

**Pattern**: YAML schema is Single Source of Truth (SSoT) - following gapless-network-data.

### YAML Schema with Extensions

```yaml
# schema/clickhouse/*.yaml
$schema: "https://json-schema.org/draft/2020-12/schema"
properties:
  field_name:
    type: string
    x-clickhouse: # ClickHouse-specific metadata
      type: "DateTime64(3)"
      not_null: true
    x-pandas: # DataFrame type hints
      dtype: "datetime64[ns, UTC]"
```

### Schema Loader Pattern

```python
# Load YAML -> typed Schema object
from gapless_deribit_clickhouse.schema.loader import load_schema
schema = load_schema("options_trades")
# Access: schema.columns, schema.clickhouse, schema.required_columns
```

### Schema Validation (Introspector)

```bash
mise run schema-validate  # Compare YAML vs live ClickHouse
```

## Contract Tests (Architectural Invariants)

**Location**: `tests/contracts/`

**Purpose**: Validate structural consistency, NOT data behavior.

Key contract tests:

- `test_yaml_schema_exists()` - Schema file must exist
- `test_required_fields_not_nullable()` - Required fields = NOT NULL
- `test_parse_format_roundtrip()` - Instrument parsing invariant
- `test_api_function_exports()` - Public API contract
- `test_exception_exports()` - Exception hierarchy contract

**Rule**: Contract tests are deletion-proof. They validate architecture, not features.

## Credentials

**Pattern**: `.env` + 1Password (never commit secrets)

```bash
# .env.example (template)
CLICKHOUSE_HOST_READONLY=
CLICKHOUSE_USER_READONLY=
CLICKHOUSE_PASSWORD_READONLY=
```

**Avoid**: Doppler for this project (simplified to .env)

## mise Tasks

```toml
# .mise.toml
[tasks.test-unit]      # No credentials needed
[tasks.test-contracts] # Schema + API contracts
[tasks.test-e2e]       # Real Deribit API
[tasks.schema-validate] # YAML vs live ClickHouse
[tasks.lint]           # ruff check
[tasks.security]       # semgrep + gitleaks
```

## ITP Workflow Integration

For significant changes, use the `/itp:itp` slash command:

```
/itp:itp [name] [-b branch] [-r release] [-p pypi]
```

**Phases**:

1. **Preflight**: ADR + design spec creation
2. **Phase 1**: Implementation (uses TodoWrite checklist)
3. **Phase 2**: Push to GitHub, format markdown
4. **Phase 3**: Release (if -r flag)

**Key files created by ITP**:

- `docs/adr/YYYY-MM-DD-slug.md` - ADR with MADR 4.0 frontmatter
- `docs/design/YYYY-MM-DD-slug/spec.md` - Design spec with tasks

## References

- **ADR**: [ClickHouse Naming Convention](/docs/adr/2025-12-08-clickhouse-naming-convention.md)
- **Pattern source**: gapless-network-data schema loader
- **Contract tests pattern**: alpha-forge
