"""
ClickHouse credential resolution for gapless-deribit-clickhouse.

Resolution order:
1. .env file (auto-loaded via python-dotenv)
2. Doppler CLI (if configured) - gapless-deribit-clickhouse/prd
3. Environment variables (CLICKHOUSE_HOST_READONLY, etc.)
4. Raise CredentialError with setup instructions

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
"""

from __future__ import annotations

import json
import os
import subprocess

from dotenv import load_dotenv

from gapless_deribit_clickhouse.exceptions import CredentialError

# Doppler project configuration
DOPPLER_PROJECT = "gapless-deribit-clickhouse"
DOPPLER_CONFIG = "prd"

# Environment variable names
ENV_HOST = "CLICKHOUSE_HOST_READONLY"
ENV_USER = "CLICKHOUSE_USER_READONLY"
ENV_PASSWORD = "CLICKHOUSE_PASSWORD_READONLY"

# Connection defaults
DEFAULT_PORT = 8443
DEFAULT_SECURE = True

# Timeout for Doppler CLI (seconds)
DOPPLER_TIMEOUT_SECONDS = 10


def get_credentials() -> tuple[str, str, str]:
    """
    Resolve ClickHouse credentials from multiple sources.

    Resolution order:
    1. .env file (auto-loaded via python-dotenv)
    2. Doppler CLI (if configured) - gapless-deribit-clickhouse/prd
    3. Environment variables (CLICKHOUSE_HOST_READONLY, etc.)
    4. Raise CredentialError with setup instructions

    Returns:
        Tuple of (host, user, password)

    Raises:
        CredentialError: If credentials cannot be resolved
    """
    # Load .env file if present (populates os.environ)
    load_dotenv()

    # Try Doppler first
    try:
        result = subprocess.run(
            [
                "doppler",
                "secrets",
                "get",
                ENV_HOST,
                ENV_USER,
                ENV_PASSWORD,
                "--json",
                "--project",
                DOPPLER_PROJECT,
                "--config",
                DOPPLER_CONFIG,
            ],
            capture_output=True,
            text=True,
            timeout=DOPPLER_TIMEOUT_SECONDS,
        )
        if result.returncode == 0:
            secrets = json.loads(result.stdout)
            return (
                secrets[ENV_HOST]["computed"],
                secrets[ENV_USER]["computed"],
                secrets[ENV_PASSWORD]["computed"],
            )
    except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired, KeyError):
        pass

    # Fall back to env vars
    host = os.environ.get(ENV_HOST)
    user = os.environ.get(ENV_USER)
    password = os.environ.get(ENV_PASSWORD)

    if host and user and password:
        return host, user, password

    # Clear error with setup instructions
    raise CredentialError(
        "ClickHouse credentials not found.\n\n"
        "Option 1: Use .env file (simplest for small teams)\n"
        "  Create .env in your project root with:\n"
        f"    {ENV_HOST}=<host>\n"
        f"    {ENV_USER}=<user>\n"
        f"    {ENV_PASSWORD}=<password>\n\n"
        "Option 2 (Recommended for production): Use Doppler service token\n"
        f"  1. Get token from 1Password: '{DOPPLER_PROJECT} Doppler Service Token'\n"
        "  2. doppler configure set token <token_from_1password>\n"
        f"  3. doppler setup --project {DOPPLER_PROJECT} --config {DOPPLER_CONFIG}\n\n"
        "Option 3: Set environment variables directly\n"
        f"  export {ENV_HOST}=<host>\n"
        f"  export {ENV_USER}=<user>\n"
        f"  export {ENV_PASSWORD}=<password>\n\n"
        "Contact your team lead for credentials."
    )
