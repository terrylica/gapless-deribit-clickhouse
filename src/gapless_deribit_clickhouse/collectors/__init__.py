"""
Data collectors for gapless-deribit-clickhouse.

ADR: 2025-12-05-trades-only-architecture-pivot
"""

from gapless_deribit_clickhouse.collectors.trades_collector import collect_trades

__all__ = [
    "collect_trades",
]
