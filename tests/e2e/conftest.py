"""
E2E test fixtures.

Provides skip-without-credentials fixtures for tests that require
real ClickHouse or Deribit API connections.

ADR: 2025-12-07-schema-first-e2e-validation
"""

import pytest


@pytest.fixture
def skip_without_credentials():
    """Skip E2E tests if credentials not configured."""
    from gapless_deribit_clickhouse.clickhouse.config import get_credentials
    from gapless_deribit_clickhouse.exceptions import CredentialError

    try:
        get_credentials()
    except CredentialError:
        pytest.skip("ClickHouse credentials not configured")


@pytest.fixture
def skip_without_deribit():
    """Skip if Deribit API unreachable."""
    import httpx

    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(
                "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time",
                params={"currency": "BTC", "kind": "option", "count": 1, "start_timestamp": 0, "end_timestamp": 1},
            )
            if response.status_code != 200:
                pytest.skip("Deribit API unreachable")
    except Exception:
        pytest.skip("Deribit API connection failed")
