"""
Shared test fixtures and factories.

Following alpha-forge pattern: factory fixtures eliminate duplication.

ADR: 2025-12-07-schema-first-e2e-validation
"""

import pytest


@pytest.fixture
def skip_without_credentials():
    """Skip test if ClickHouse credentials not configured.

    Consolidated from tests/test_api.py and tests/e2e/conftest.py.
    Single source of truth for credential validation.
    """
    from gapless_deribit_clickhouse.clickhouse.config import get_credentials
    from gapless_deribit_clickhouse.exceptions import CredentialError

    try:
        get_credentials()
    except CredentialError:
        pytest.skip("ClickHouse credentials not configured")


@pytest.fixture
def skip_without_deribit():
    """Skip if Deribit API unreachable.

    Moved from tests/e2e/conftest.py for broader availability.
    """
    import httpx

    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(
                "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time",
                params={
                    "currency": "BTC",
                    "kind": "option",
                    "count": 1,
                    "start_timestamp": 0,
                    "end_timestamp": 1,
                },
            )
            if response.status_code != 200:
                pytest.skip("Deribit API unreachable")
    except Exception:
        pytest.skip("Deribit API connection failed")


@pytest.fixture
def instrument_factory():
    """Factory for creating test instruments."""

    def _create(
        underlying: str = "BTC",
        expiry: str = "27DEC24",
        strike: int = 100000,
        option_type: str = "C",
    ) -> str:
        return f"{underlying}-{expiry}-{strike}-{option_type}"

    return _create


@pytest.fixture
def trade_factory():
    """Factory for creating mock trade dictionaries."""

    def _create(**overrides) -> dict:
        base = {
            "trade_id": "123456",
            "instrument_name": "BTC-27DEC24-100000-C",
            "timestamp": 1704067200000,
            "price": 0.05,
            "amount": 1.0,
            "direction": "buy",
            "iv": 0.65,
            "index_price": 42000.0,
        }
        base.update(overrides)
        return base

    return _create
