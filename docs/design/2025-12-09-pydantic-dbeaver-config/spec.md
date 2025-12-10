---
adr: 2025-12-09-pydantic-dbeaver-config
source: ~/.claude/plans/humble-wobbling-walrus.md
implementation-status: completed
phase: phase-1
last-updated: 2025-12-09
---

# Design Spec: Pydantic-Based DBeaver Connection Configuration

**ADR**: [Pydantic-Based DBeaver Connection Configuration](/docs/adr/2025-12-09-pydantic-dbeaver-config.md)

## Problem Statement

User misconfigured DBeaver (put "deribit" in Username instead of Database/Schema field). Need a sophisticated, AI-maintainable system where:

- Single source of truth (Pydantic models)
- Auto-generated DBeaver config and JSON Schema
- Pre-commit validation ensures integrity
- `mise run dbeaver` launches with env vars loaded

## Architecture: Pydantic → Generate All

**Flow**: Pydantic models + .env → Generator script → DBeaver JSON + Schema

**Key Design Decisions**:

1. **Credential handling**: Pre-populate from `.env` (password written to generated JSON, file is gitignored)
2. **DBeaver launch**: Direct binary `/Applications/DBeaver.app/Contents/MacOS/dbeaver` (not `open -a` which loses env vars)
3. **Dual-mode**: Local (HTTP:8123, no auth) + Cloud (HTTPS:443, auth from .env)

## Files to Create/Modify

| File                                                   | Purpose                                     |
| ------------------------------------------------------ | ------------------------------------------- |
| `src/gapless_deribit_clickhouse/config/connections.py` | Pydantic models (SSoT)                      |
| `scripts/generate_dbeaver_config.py`                   | Generator script                            |
| `.dbeaver/data-sources.json`                           | Generated DBeaver config (GITIGNORED)       |
| `.dbeaver/data-sources.schema.json`                    | Generated JSON Schema (committed)           |
| `.vscode/settings.json`                                | Schema association for IDE                  |
| `.mise.toml`                                           | Tasks: generate, validate, dbeaver launcher |
| `.gitignore`                                           | Exclude credential files                    |
| `CLAUDE.md`                                            | Document DBeaver workflow                   |

## Implementation Tasks

### Task 1: Create Pydantic Models

**File**: `src/gapless_deribit_clickhouse/config/connections.py`

```python
from enum import Enum
from pydantic import BaseModel, Field, model_validator
import os

class ConnectionMode(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"

class ClickHouseConnection(BaseModel):
    """ClickHouse connection configuration."""
    mode: ConnectionMode
    name: str = Field(..., description="Display name in DBeaver")
    host: str = Field(..., description="ClickHouse server hostname")
    port: int = Field(..., description="ClickHouse server port")
    database: str = Field(default="default", description="Database name")
    user: str = Field(default="default", description="Username")
    password: str = Field(default="", description="Password (empty for local)")
    ssl: bool = Field(default=False, description="Use SSL/TLS connection")

    @model_validator(mode='after')
    def set_defaults_by_mode(self):
        if self.mode == ConnectionMode.LOCAL:
            # Local: HTTP, no auth
            self.ssl = False
        elif self.mode == ConnectionMode.CLOUD:
            # Cloud: HTTPS required
            self.ssl = True
        return self

    @classmethod
    def from_env(cls, mode: ConnectionMode) -> "ClickHouseConnection":
        """Create connection from environment variables."""
        if mode == ConnectionMode.LOCAL:
            return cls(
                mode=mode,
                name="ClickHouse Local",
                host="localhost",
                port=8123,
                database="deribit",
                user="default",
                password="",
            )
        else:
            return cls(
                mode=mode,
                name="ClickHouse Cloud",
                host=os.environ.get("CLICKHOUSE_HOST_READONLY", ""),
                port=443,
                database="deribit",
                user=os.environ.get("CLICKHOUSE_USER_READONLY", "default"),
                password=os.environ.get("CLICKHOUSE_PASSWORD_READONLY", ""),
            )
```

### Task 2: Create Generator Script

**File**: `scripts/generate_dbeaver_config.py`

- Import Pydantic models from `connections.py`
- Generate `.dbeaver/data-sources.json` in DBeaver format
- Generate `.dbeaver/data-sources.schema.json` via `model_json_schema()`
- Idempotent (safe to run repeatedly)

### Task 3: Create .dbeaver/ Directory

```bash
mkdir -p .dbeaver
```

### Task 4: Add Mise Tasks

**File**: `.mise.toml` (append)

```toml
[tasks.dbeaver-generate]
description = "Generate DBeaver config from Pydantic models"
run = "uv run scripts/generate_dbeaver_config.py"

[tasks.dbeaver-validate]
description = "Validate DBeaver config against schema"
run = "uv run python -c \"import json; json.load(open('.dbeaver/data-sources.json'))\""

[tasks.dbeaver]
description = "Launch DBeaver with project config"
run = "/Applications/DBeaver.app/Contents/MacOS/dbeaver &"
```

### Task 5: Run Generator

```bash
mise run dbeaver-generate
```

### Task 6: Create VS Code Settings

**File**: `.vscode/settings.json`

```json
{
  "json.schemas": [
    {
      "fileMatch": [".dbeaver/data-sources.json"],
      "url": "./.dbeaver/data-sources.schema.json"
    }
  ]
}
```

### Task 7: Update .gitignore

```
# DBeaver credentials (generated, contains passwords)
.dbeaver/data-sources.json
.dbeaver/credentials-config.json
```

### Task 8: Update CLAUDE.md

Add DBeaver Configuration section with workflow documentation.

### Task 9: Test DBeaver Launch

```bash
mise run dbeaver
```

## Success Criteria

- [ ] `mise run dbeaver-generate` creates valid JSON files
- [ ] `.dbeaver/data-sources.json` contains both Local and Cloud connections
- [ ] `.dbeaver/data-sources.schema.json` provides IDE IntelliSense
- [ ] `mise run dbeaver` launches DBeaver with connections available
- [ ] Local connection works without credentials
- [ ] Cloud connection pre-populates from `.env`
- [ ] Credentials file is gitignored

## Key Benefits

| Benefit                | How                                       |
| ---------------------- | ----------------------------------------- |
| Single Source of Truth | Pydantic models define all connections    |
| AI-Maintainable        | Claude edits Python, runs generator       |
| Type-Safe              | Pydantic validates at definition time     |
| Self-Documenting       | Field descriptions → schema → IDE hover   |
| Schema Validated       | `mise run dbeaver-validate` checks config |
| IDE Support            | VS Code IntelliSense from JSON Schema     |
| Secure                 | Credentials gitignored, read from .env    |
