"""Unit tests for pagination validation.

ADR: 2025-12-08-mise-pagination-validation
"""

from gapless_deribit_clickhouse.collectors.trades_collector import _validate_page_continuity


class TestValidatePageContinuity:
    """Tests for _validate_page_continuity function."""

    def test_empty_pages_valid(self):
        """Empty pages should be valid."""
        is_valid, warnings = _validate_page_continuity([], [])
        assert is_valid
        assert not warnings

    def test_empty_prev_page_valid(self):
        """Empty previous page should be valid (first page)."""
        curr = [{"trade_id": "1", "timestamp": 1000}]
        is_valid, warnings = _validate_page_continuity([], curr)
        assert is_valid
        assert not warnings

    def test_empty_curr_page_valid(self):
        """Empty current page should be valid (last page)."""
        prev = [{"trade_id": "1", "timestamp": 1000}]
        is_valid, warnings = _validate_page_continuity(prev, [])
        assert is_valid
        assert not warnings

    def test_continuous_pages_valid(self):
        """Continuous pages with no gap should be valid."""
        prev = [{"trade_id": "1", "timestamp": 1000}]
        curr = [{"trade_id": "2", "timestamp": 999}]
        is_valid, warnings = _validate_page_continuity(prev, curr)
        assert is_valid
        assert not warnings

    def test_small_gap_valid(self):
        """Gap smaller than threshold should be valid."""
        prev = [{"trade_id": "1", "timestamp": 2000}]
        curr = [{"trade_id": "2", "timestamp": 1500}]  # 500ms gap < 1000ms threshold
        is_valid, warnings = _validate_page_continuity(prev, curr)
        assert is_valid
        assert not warnings

    def test_gap_detected(self):
        """Gap larger than threshold should be detected."""
        prev = [{"trade_id": "1", "timestamp": 5000}]
        curr = [{"trade_id": "2", "timestamp": 1000}]  # 4000ms gap
        is_valid, warnings = _validate_page_continuity(prev, curr)
        assert not is_valid
        assert len(warnings) == 1
        assert "Gap detected" in warnings[0]
        assert "4000ms" in warnings[0]

    def test_custom_threshold(self, monkeypatch):
        """Custom threshold from environment should be respected."""
        monkeypatch.setenv("PAGINATION_GAP_THRESHOLD_MS", "5000")
        prev = [{"trade_id": "1", "timestamp": 5000}]
        curr = [{"trade_id": "2", "timestamp": 1000}]  # 4000ms gap < 5000ms threshold
        is_valid, warnings = _validate_page_continuity(prev, curr)
        assert is_valid
        assert not warnings

    def test_duplicates_detected(self):
        """Duplicate trade_ids should be detected."""
        prev = [{"trade_id": "1", "timestamp": 1000}]
        curr = [{"trade_id": "1", "timestamp": 999}]  # Same trade_id
        is_valid, warnings = _validate_page_continuity(prev, curr)
        assert not is_valid
        assert len(warnings) == 1
        assert "Duplicates" in warnings[0]

    def test_multiple_duplicates(self):
        """Multiple duplicate trade_ids should be counted."""
        prev = [
            {"trade_id": "1", "timestamp": 1000},
            {"trade_id": "2", "timestamp": 1001},
            {"trade_id": "3", "timestamp": 1002},
        ]
        curr = [
            {"trade_id": "1", "timestamp": 999},  # Duplicate
            {"trade_id": "2", "timestamp": 998},  # Duplicate
            {"trade_id": "4", "timestamp": 997},
        ]
        is_valid, warnings = _validate_page_continuity(prev, curr)
        assert not is_valid
        assert len(warnings) == 1
        assert "2 trades" in warnings[0]

    def test_gap_and_duplicates_both_detected(self):
        """Both gap and duplicates should be detected together."""
        prev = [{"trade_id": "1", "timestamp": 5000}]
        curr = [{"trade_id": "1", "timestamp": 1000}]  # 4000ms gap + duplicate
        is_valid, warnings = _validate_page_continuity(prev, curr)
        assert not is_valid
        assert len(warnings) == 2
        assert any("Gap detected" in w for w in warnings)
        assert any("Duplicates" in w for w in warnings)

    def test_multiple_trades_uses_min_max(self):
        """Should use min timestamp from prev and max from curr."""
        prev = [
            {"trade_id": "1", "timestamp": 3000},
            {"trade_id": "2", "timestamp": 2000},  # Min = 2000
            {"trade_id": "3", "timestamp": 2500},
        ]
        curr = [
            {"trade_id": "4", "timestamp": 1500},
            {"trade_id": "5", "timestamp": 1800},  # Max = 1800
            {"trade_id": "6", "timestamp": 1600},
        ]
        # Gap = 2000 - 1800 = 200ms (valid)
        is_valid, warnings = _validate_page_continuity(prev, curr)
        assert is_valid
        assert not warnings
