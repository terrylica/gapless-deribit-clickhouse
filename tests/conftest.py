"""
Shared test fixtures and factories.

Following alpha-forge pattern: factory fixtures eliminate duplication.

ADR: 2025-12-07-schema-first-e2e-validation
"""

import pytest


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
