# ADR: 2025-12-11-e2e-validation-pipeline
"""Tests for validation infrastructure module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


class TestGetModeIndicator:
    """Test get_mode_indicator() function."""

    def test_default_mode_is_local(self):
        """Default mode should be local when env var not set."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            get_mode_indicator,
        )

        with patch.dict(os.environ, {}, clear=True):
            result = get_mode_indicator()
            assert "[LOCAL]" in result

    def test_cloud_mode_indicator(self):
        """Cloud mode should show [CLOUD] prefix."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            get_mode_indicator,
        )

        with patch.dict(
            os.environ,
            {
                "CLICKHOUSE_MODE": "cloud",
                "CLICKHOUSE_HOST_CLOUD": "test.clickhouse.cloud",
            },
        ):
            result = get_mode_indicator()
            assert "[CLOUD]" in result
            assert "test.clickhouse.cloud" in result

    def test_local_mode_indicator(self):
        """Local mode should show [LOCAL] prefix."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            get_mode_indicator,
        )

        with patch.dict(
            os.environ,
            {
                "CLICKHOUSE_MODE": "local",
                "CLICKHOUSE_HOST_LOCAL": "localhost",
            },
        ):
            result = get_mode_indicator()
            assert "[LOCAL]" in result
            assert "localhost" in result


class TestGetConnectionInfo:
    """Test get_connection_info() function."""

    def test_local_connection_info(self):
        """Local mode should return HTTP port 8123."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            get_connection_info,
        )

        with patch.dict(os.environ, {"CLICKHOUSE_MODE": "local"}):
            info = get_connection_info()
            assert info["mode"] == "local"
            assert info["port"] == 8123
            assert info["secure"] is False

    def test_cloud_connection_info(self):
        """Cloud mode should return HTTPS port 443."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            get_connection_info,
        )

        with patch.dict(
            os.environ,
            {
                "CLICKHOUSE_MODE": "cloud",
                "CLICKHOUSE_HOST_CLOUD": "test.clickhouse.cloud",
            },
        ):
            info = get_connection_info()
            assert info["mode"] == "cloud"
            assert info["port"] == 443
            assert info["secure"] is True
            assert info["host"] == "test.clickhouse.cloud"


class TestCheckSpotDictionaryExists:
    """Test check_spot_dictionary_exists() function."""

    def test_returns_true_when_exists(self):
        """Should return True when dictionary exists."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            check_spot_dictionary_exists,
        )

        mock_client = MagicMock()
        mock_client.query.return_value.result_rows = [(1,)]

        result = check_spot_dictionary_exists(mock_client)
        assert result is True

    def test_returns_false_when_not_exists(self):
        """Should return False when dictionary doesn't exist."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            check_spot_dictionary_exists,
        )

        mock_client = MagicMock()
        mock_client.query.return_value.result_rows = [(0,)]

        result = check_spot_dictionary_exists(mock_client)
        assert result is False


class TestEnsureSpotDictionary:
    """Test ensure_spot_dictionary() function."""

    def test_returns_true_when_exists(self):
        """Should return True without creating when dictionary exists."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            ensure_spot_dictionary,
        )

        mock_client = MagicMock()
        mock_client.query.return_value.result_rows = [(1,)]

        result = ensure_spot_dictionary(mock_client, auto_create=True)
        assert result is True
        mock_client.command.assert_not_called()

    def test_creates_when_missing_and_auto_create(self):
        """Should create dictionary when missing and auto_create=True."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            ensure_spot_dictionary,
        )

        mock_client = MagicMock()
        mock_client.query.return_value.result_rows = [(0,)]

        result = ensure_spot_dictionary(mock_client, auto_create=True)
        assert result is True
        mock_client.command.assert_called_once()

    def test_raises_when_missing_and_no_auto_create(self):
        """Should raise RuntimeError when missing and auto_create=False."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            ensure_spot_dictionary,
        )

        mock_client = MagicMock()
        mock_client.query.return_value.result_rows = [(0,)]

        with pytest.raises(RuntimeError, match="spot_prices_dict not found"):
            ensure_spot_dictionary(mock_client, auto_create=False)


class TestValidateSchemaVersion:
    """Test validate_schema_version() function."""

    def test_raises_when_table_not_exists(self):
        """Should raise RuntimeError when table doesn't exist."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            validate_schema_version,
        )

        mock_client = MagicMock()
        mock_client.query.return_value.result_rows = [(0,)]

        with pytest.raises(RuntimeError, match="does not exist"):
            validate_schema_version(mock_client)

    def test_valid_schema_returns_valid_true(self):
        """Should return valid=True for v3.0.0 compliant schema."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            validate_schema_version,
        )

        mock_client = MagicMock()

        # Mock table exists check
        table_check_result = MagicMock()
        table_check_result.result_rows = [(1,)]

        # Mock sorting key check
        sorting_key_result = MagicMock()
        sorting_key_result.result_rows = [
            ("underlying, expiry, strike, option_type, timestamp",)
        ]

        # Mock low cardinality columns
        low_card_result = MagicMock()
        low_card_result.result_rows = [
            ("direction",),
            ("underlying",),
            ("option_type",),
        ]

        mock_client.query.side_effect = [
            table_check_result,
            sorting_key_result,
            low_card_result,
        ]

        result = validate_schema_version(mock_client)
        assert result["valid"] is True
        assert result["table_exists"] is True
        assert "timestamp" in result["order_by_columns"]
        assert "direction" in result["low_cardinality_columns"]

    def test_invalid_schema_missing_timestamp(self):
        """Should report error when timestamp not in ORDER BY."""
        from gapless_deribit_clickhouse.validation.infrastructure import (
            validate_schema_version,
        )

        mock_client = MagicMock()

        table_check_result = MagicMock()
        table_check_result.result_rows = [(1,)]

        # Missing timestamp in ORDER BY
        sorting_key_result = MagicMock()
        sorting_key_result.result_rows = [("underlying, expiry, strike",)]

        low_card_result = MagicMock()
        low_card_result.result_rows = [
            ("direction",),
            ("underlying",),
            ("option_type",),
        ]

        mock_client.query.side_effect = [
            table_check_result,
            sorting_key_result,
            low_card_result,
        ]

        result = validate_schema_version(mock_client)
        assert result["valid"] is False
        assert any("timestamp" in e for e in result["errors"])
