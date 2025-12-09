#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
#     "pandas>=2.0",
# ]
# ///
"""
PoC: Backfill historical Deribit data and measure actual costs.

Tests the data pipeline with a small time window to measure real costs
before committing to full historical backfill (2018-2025).

Usage:
    uv run scripts/poc_backfill.py --month 2024-12
    uv run scripts/poc_backfill.py --start 2024-12-01 --end 2024-12-07

ADR: 2025-12-08-clickhouse-data-pipeline-architecture
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime


def run_backfill(start_date: str, end_date: str, dry_run: bool = False) -> dict:
    """
    Run backfill for specified date range.

    Returns:
        Dict with row count, duration, and data size metrics.
    """
    from gapless_deribit_clickhouse import collect_trades

    print(f"Backfilling: {start_date} to {end_date}")

    if dry_run:
        print("DRY RUN - collecting without insertion")

    start_time = datetime.now()

    df = collect_trades(
        currency="BTC",
        start_date=start_date,
        end_date=end_date,
        insert_to_db=not dry_run,
    )

    duration = (datetime.now() - start_time).total_seconds()

    return {
        "rows": len(df),
        "duration_seconds": duration,
        "bytes_raw": df.memory_usage(deep=True).sum(),
        "start_date": start_date,
        "end_date": end_date,
        "inserted": not dry_run,
    }


def main() -> int:
    """Run PoC backfill and report metrics."""
    parser = argparse.ArgumentParser(description="PoC backfill with cost measurement")
    parser.add_argument(
        "--month",
        type=str,
        help="Month to backfill (YYYY-MM format)",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect data without inserting to database",
    )
    args = parser.parse_args()

    # Resolve date range
    if args.month:
        year, month = args.month.split("-")
        start_date = f"{year}-{month}-01"
        # Calculate last day of month
        if int(month) == 12:
            end_date = f"{int(year) + 1}-01-01"
        else:
            end_date = f"{year}-{int(month) + 1:02d}-01"
    elif args.start and args.end:
        start_date = args.start
        end_date = args.end
    else:
        print("Error: Specify --month or both --start and --end", file=sys.stderr)
        return 1

    print("=== PoC Backfill ===")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE (inserting to DB)'}")
    print()

    try:
        metrics = run_backfill(start_date, end_date, dry_run=args.dry_run)
    except Exception as e:
        print(f"Backfill failed: {e}", file=sys.stderr)
        return 1

    # Report metrics
    print("\n=== Results ===")
    print(f"Rows collected:    {metrics['rows']:,}")
    print(f"Duration:          {metrics['duration_seconds']:.1f} seconds")
    print(f"Raw size:          {metrics['bytes_raw'] / 1e6:.2f} MB")
    print(f"Rows/second:       {metrics['rows'] / metrics['duration_seconds']:.0f}")
    print(f"Inserted to DB:    {'Yes' if metrics['inserted'] else 'No (dry run)'}")

    # Project full backfill costs
    days_in_range = 30  # Approximate month
    full_backfill_months = 84  # 2018-01 to 2025-01

    print("\n=== Projections (84 months: 2018-2025) ===")
    print(f"Estimated rows:    {metrics['rows'] * full_backfill_months:,}")
    print(f"Estimated size:    {metrics['bytes_raw'] * full_backfill_months / 1e9:.2f} GB (raw)")
    print(f"Estimated time:    {metrics['duration_seconds'] * full_backfill_months / 3600:.1f} hours")

    print("\n=== Next Steps ===")
    print("1. Wait 24 hours for billing APIs to update")
    print("2. Run: uv run scripts/measure_baseline_costs.py")
    print("3. Compare with pre-backfill baseline")

    return 0


if __name__ == "__main__":
    sys.exit(main())
