#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
# ]
# ///
"""
Monitor ClickHouse Cloud egress costs.

Checks daily egress and alerts if threshold exceeded.
Critical for cost optimization - egress is $0.115/GB on public internet.

Usage:
    uv run scripts/monitor_egress.py
    uv run scripts/monitor_egress.py --threshold 10  # Alert if > 10 GB

ADR: 2025-12-08-clickhouse-data-pipeline-architecture
"""

from __future__ import annotations

import argparse
import sys


def check_egress(threshold_gb: float = 10.0) -> tuple[bool, float, float]:
    """
    Check egress against threshold.

    Returns:
        Tuple of (alert_triggered, egress_gb, cost_usd)
    """
    from gapless_deribit_clickhouse.billing import ClickHouseCloudBilling

    client = ClickHouseCloudBilling()
    usage = client.get_usage_cost(days=1)

    egress_gb = usage.egress_gb_estimate
    cost_usd = usage.egress_chc

    alert = egress_gb > threshold_gb
    return alert, egress_gb, cost_usd


def main() -> int:
    """Monitor egress and report status."""
    parser = argparse.ArgumentParser(description="Monitor egress costs")
    parser.add_argument(
        "--threshold",
        type=float,
        default=10.0,
        help="Alert threshold in GB (default: 10)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only output on alert",
    )
    args = parser.parse_args()

    try:
        alert, egress_gb, cost_usd = check_egress(args.threshold)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"API error: {e}", file=sys.stderr)
        return 1

    if alert:
        print(f"ALERT: High egress detected!")
        print(f"  Egress: {egress_gb:.2f} GB (threshold: {args.threshold} GB)")
        print(f"  Cost:   ${cost_usd:.2f}")
        print()
        print("Optimization tips:")
        print("  1. Deploy consumers in us-west-2 (same region = FREE)")
        print("  2. Enable ZSTD compression in clickhouse-connect")
        print("  3. Aggregate in ClickHouse, not client-side")
        print("  4. Use efficient formats (Parquet, Native) not JSON/CSV")
        return 2  # Alert exit code

    if not args.quiet:
        print(f"Egress OK: {egress_gb:.2f} GB (${cost_usd:.2f})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
