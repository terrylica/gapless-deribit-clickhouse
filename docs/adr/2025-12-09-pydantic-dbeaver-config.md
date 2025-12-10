---
status: accepted
date: 2025-12-09
decision-maker: Terry Li
consulted: [DBeaver-Config-Agent, macOS-Launch-Agent, Pydantic-SSoT-Agent]
research-method: single-agent
clarification-iterations: 4
perspectives: [DeveloperExperience, Maintainability, Security]
---

# ADR: Pydantic-Based DBeaver Connection Configuration

**Design Spec**: [Implementation Spec](/docs/design/2025-12-09-pydantic-dbeaver-config/spec.md)

## Context and Problem Statement

User misconfigured DBeaver by putting "deribit" in the Username field instead of the Database/Schema field, resulting in authentication failure. This revealed a broader issue: database connection configuration is error-prone and not self-documenting.

The project needs a sophisticated, AI-maintainable system where:

- Connection settings are defined once (Single Source of Truth)
- DBeaver configuration is auto-generated from code
- Credentials are handled securely (gitignored) but conveniently (pre-populated)
- AI coding agents can maintain the system without manual intervention

### Before/After

```
                                 🔄 DBeaver Configuration Flow

┌−−−−−−−−−−−−−−−−−−−−−┐            ┌−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−┐
╎ Before:             ╎            ╎ After:                                                    ╎
╎                     ╎            ╎                                                           ╎
╎ ┌─────────────────┐ ╎            ╎ ┌───────────────┐     ┌───────────┐     ┌───────────────┐ ╎
╎ │  Manual Config  │ ╎  migrate   ╎ │ Pydantic SSoT │     │ Generator │     │ DBeaver JSON  │ ╎
╎ │ [!] Error-prone │ ╎ ─────────> ╎ │ [+] Type-safe │ ──> │  Script   │ ──> │ [OK] Auto-gen │ ╎
╎ └─────────────────┘ ╎            ╎ └───────────────┘     └───────────┘     └───────────────┘ ╎
╎                     ╎            ╎                                                           ╎
└−−−−−−−−−−−−−−−−−−−−−┘            └−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−−┘
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "🔄 DBeaver Configuration Flow"; flow: east; }
( Before:
  [Manual Config] { label: "Manual Config\n[!] Error-prone"; }
)
( After:
  [Pydantic SSoT] { label: "Pydantic SSoT\n[+] Type-safe"; }
  [Generator] { label: "Generator\nScript"; }
  [DBeaver JSON] { label: "DBeaver JSON\n[OK] Auto-gen"; }
)
[Manual Config] -- migrate --> [Pydantic SSoT]
[Pydantic SSoT] -> [Generator] -> [DBeaver JSON]
```

</details>

## Research Summary

| Agent Perspective    | Key Finding                                                     | Confidence |
| -------------------- | --------------------------------------------------------------- | ---------- |
| DBeaver-Config-Agent | DBeaver uses `data-sources.json` for project-level connections  | High       |
| macOS-Launch-Agent   | `open -a DBeaver` loses env vars; direct binary required        | High       |
| Pydantic-SSoT-Agent  | Pydantic models + `model_json_schema()` = code-first validation | High       |

## Decision Log

| Decision Area       | Options Evaluated                     | Chosen                      | Rationale                                       |
| ------------------- | ------------------------------------- | --------------------------- | ----------------------------------------------- |
| SSoT Pattern        | JSON Schema, YAML, Pydantic           | Pydantic                    | Type-safe, generates JSON Schema, Python-native |
| Credential Handling | Prompt always, env vars, pre-populate | Pre-populate + gitignore    | Local has no security concern; cloud reads .env |
| DBeaver Launch      | `open -a`, direct binary, mise task   | mise task + direct binary   | Env var inheritance on macOS                    |
| Dual-Mode Support   | Single config, separate configs       | Single model with mode enum | DRY, validates both at definition time          |

### Trade-offs Accepted

| Trade-off                    | Choice             | Accepted Cost                                      |
| ---------------------------- | ------------------ | -------------------------------------------------- |
| Simplicity vs Sophistication | Pydantic SSoT      | More initial setup, but AI-maintainable long-term  |
| Security vs Convenience      | Pre-populate local | Gitignored file contains plain credentials locally |

## Decision Drivers

- **AI Maintainability**: Claude Code must be able to modify and regenerate config
- **Error Prevention**: Eliminate manual configuration mistakes
- **Dual-Mode**: Support both local ClickHouse (HTTP:8123) and Cloud (HTTPS:443)
- **macOS Compatibility**: Env var inheritance requires direct binary execution

## Considered Options

- **Option A**: Manual DBeaver configuration (status quo)
- **Option B**: JSON Schema-first with handwritten config
- **Option C**: Pydantic models as SSoT with generator script <- Selected

## Decision Outcome

Chosen option: **Option C (Pydantic SSoT)**, because it provides:

1. Type-safe connection definitions with validation at definition time
2. Auto-generated JSON Schema for IDE IntelliSense
3. Single source of truth that AI agents can modify programmatically
4. Secure credential handling (pre-populated from .env, gitignored output)

## Synthesis

**Convergent findings**: All perspectives agreed DBeaver project config is the right approach over user-level config.

**Divergent findings**: Security agent preferred credential prompts; DX agent preferred pre-population.

**Resolution**: Differentiate by mode—local has no security concern (default user, no password), cloud pre-populates from .env into gitignored file.

## Consequences

### Positive

- Zero-friction DBeaver setup: `mise run dbeaver-generate && mise run dbeaver`
- AI agents can modify connections by editing Python, then regenerating
- IDE IntelliSense from generated JSON Schema
- Type-safe validation prevents invalid configurations

### Negative

- Generator script must be run after Pydantic model changes
- Gitignored `data-sources.json` means each developer generates locally
- macOS-specific binary path in mise task

## Architecture

```
                        🏗️ Pydantic SSoT Architecture

                                 ╭───────────────────╮
                                 │       .env        │
                                 │    Credentials    │
                                 ╰───────────────────╯
                                   │
                                   │
                                   ∨
┌──────────────────────────┐     ┌───────────────────────────────────────────┐     ┌──────────────────┐
│ data-sources.schema.json │     │                                           │     │    mise tasks    │
│      [+] Committed       │     │        generate_dbeaver_config.py         │     │ dbeaver-generate │
│                          │ <── │                                           │ <── │     dbeaver      │
└──────────────────────────┘     └───────────────────────────────────────────┘     └──────────────────┘
                                   │                         ∧                       │
                                   │                         │                       │
                                   ∨                         │                       │
                                 ┌───────────────────┐     ╔═════════════════╗       │
                                 │ data-sources.json │     ║ connections.py  ║       │
                                 │  [x] Gitignored   │     ║ Pydantic Models ║       │
                                 └───────────────────┘     ╚═════════════════╝       │
                                   │                                                 │
                                   │                                                 │
                                   ∨                                                 │
                                 ╭───────────────────╮                               │
                                 │      DBeaver      │                               │
                                 │   Direct Binary   │ <─────────────────────────────┘
                                 ╰───────────────────╯
```

<details>
<summary>graph-easy source</summary>

```
graph { label: "🏗️ Pydantic SSoT Architecture"; flow: south; }
[.env] { label: ".env\nCredentials"; shape: rounded; }
[Pydantic] { label: "connections.py\nPydantic Models"; border: double; }
[Generator] { label: "generate_dbeaver_config.py"; }
[JSON] { label: "data-sources.json\n[x] Gitignored"; }
[Schema] { label: "data-sources.schema.json\n[+] Committed"; }
[DBeaver] { label: "DBeaver\nDirect Binary"; shape: rounded; }
[mise] { label: "mise tasks\ndbeaver-generate\ndbeaver"; }

[.env] -> [Generator]
[Pydantic] -> [Generator]
[Generator] -> [JSON]
[Generator] -> [Schema]
[mise] -> [Generator]
[mise] -> [DBeaver]
[JSON] -> [DBeaver]
```

</details>

## References

- [ClickHouse Naming Convention ADR](/docs/adr/2025-12-08-clickhouse-naming-convention.md)
- [mise env centralized config ADR](/docs/adr/2025-12-08-mise-env-centralized-config.md)
