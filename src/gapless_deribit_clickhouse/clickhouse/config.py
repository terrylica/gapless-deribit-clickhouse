"""
ClickHouse credential resolution for gapless-deribit-clickhouse.

Resolution order:
1. .env file (auto-loaded via python-dotenv)
2. Environment variables (CLICKHOUSE_HOST_READONLY, etc.)
3. Raise CredentialError with setup instructions

ADR: 2025-12-07-schema-first-e2e-validation
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from gapless_deribit_clickhouse.exceptions import CredentialError

# Environment variable names
ENV_HOST = "CLICKHOUSE_HOST_READONLY"
ENV_USER = "CLICKHOUSE_USER_READONLY"
ENV_PASSWORD = "CLICKHOUSE_PASSWORD_READONLY"

# Connection defaults
# Note: Port 443 used instead of 8443 for network compatibility
DEFAULT_PORT = 443
DEFAULT_SECURE = True


def get_credentials() -> tuple[str, str, str]:
    """
    Resolve ClickHouse credentials from .env or environment variables.

    Resolution order:
    1. .env file (auto-loaded via python-dotenv)
    2. Environment variables (CLICKHOUSE_HOST_READONLY, etc.)
    3. Raise CredentialError with setup instructions

    Returns:
        Tuple of (host, user, password)

    Raises:
        CredentialError: If credentials cannot be resolved
    """
    # Load .env file if present (populates os.environ)
    # override=True ensures .env takes precedence over existing env vars
    load_dotenv(override=True)

    # Read from env vars (populated by .env or set directly)
    host = os.environ.get(ENV_HOST)
    user = os.environ.get(ENV_USER)
    password = os.environ.get(ENV_PASSWORD)

    if host and user and password:
        return host, user, password

    # Clear error with setup instructions
    raise CredentialError(
        "ClickHouse credentials not found.\n\n"
        "Setup: Copy .env.example to .env and fill in credentials from 1Password:\n"
        "  cp .env.example .env\n\n"
        f"Required variables:\n"
        f"  {ENV_HOST}=<host>\n"
        f"  {ENV_USER}=<user>\n"
        f"  {ENV_PASSWORD}=<password>\n\n"
        "Get credentials from 1Password: 'gapless-deribit-clickhouse'"
    )
