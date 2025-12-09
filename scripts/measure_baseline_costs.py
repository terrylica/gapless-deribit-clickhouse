#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
#     "boto3>=1.35",
# ]
# ///
"""
Measure baseline ClickHouse Cloud and AWS costs before PoC.

Records 7-day baseline costs from both billing APIs for comparison
after running cost experiments.

Usage:
    uv run scripts/measure_baseline_costs.py
    uv run scripts/measure_baseline_costs.py --days 14

ADR: 2025-12-08-clickhouse-data-pipeline-architecture
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def measure_clickhouse_costs(days: int) -> dict | None:
    """Query ClickHouse Cloud billing API."""
    try:
        from gapless_deribit_clickhouse.billing import ClickHouseCloudBilling

        client = ClickHouseCloudBilling()
        usage = client.get_usage_cost(days=days)

        return {
            "compute_chc": usage.compute_chc,
            "storage_chc": usage.storage_chc,
            "egress_chc": usage.egress_chc,
            "total_chc": usage.total_chc,
            "egress_gb_estimate": usage.egress_gb_estimate,
            "period_start": usage.period_start.isoformat(),
            "period_end": usage.period_end.isoformat(),
        }
    except ValueError as e:
        print(f"ClickHouse Cloud API not configured: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ClickHouse Cloud API error: {e}", file=sys.stderr)
        return None


def measure_aws_costs(days: int) -> dict | None:
    """Query AWS Cost Explorer API."""
    try:
        from gapless_deribit_clickhouse.billing import AWSCostExplorer

        client = AWSCostExplorer()
        cost = client.get_cost(days=days)

        return {
            "lambda_cost": cost.lambda_cost,
            "ec2_spot_cost": cost.ec2_spot_cost,
            "data_transfer_cost": cost.data_transfer_cost,
            "total_cost": cost.total_cost,
            "period_start": cost.period_start.isoformat(),
            "period_end": cost.period_end.isoformat(),
        }
    except ImportError:
        print("boto3 not installed. Run: uv add boto3", file=sys.stderr)
        return None
    except Exception as e:
        print(f"AWS Cost Explorer error: {e}", file=sys.stderr)
        return None


def main() -> int:
    """Measure and record baseline costs."""
    parser = argparse.ArgumentParser(description="Measure baseline costs")
    parser.add_argument("--days", type=int, default=7, help="Days to query (default: 7)")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tmp/baseline_costs.json"),
        help="Output file (default: tmp/baseline_costs.json)",
    )
    args = parser.parse_args()

    print(f"Measuring {args.days}-day baseline costs...")

    baseline = {
        "measured_at": datetime.now().isoformat(),
        "period_days": args.days,
        "clickhouse": measure_clickhouse_costs(args.days),
        "aws": measure_aws_costs(args.days),
    }

    # Print summary
    print("\n=== Baseline Cost Summary ===")

    if baseline["clickhouse"]:
        ch = baseline["clickhouse"]
        print(f"\nClickHouse Cloud ({args.days} days):")
        print(f"  Compute:  ${ch['compute_chc']:.2f}")
        print(f"  Storage:  ${ch['storage_chc']:.2f}")
        print(f"  Egress:   ${ch['egress_chc']:.2f} (~{ch['egress_gb_estimate']:.2f} GB)")
        print(f"  Total:    ${ch['total_chc']:.2f}")
    else:
        print("\nClickHouse Cloud: Not configured")

    if baseline["aws"]:
        aws = baseline["aws"]
        print(f"\nAWS ({args.days} days):")
        print(f"  Lambda:        ${aws['lambda_cost']:.2f}")
        print(f"  EC2 Spot:      ${aws['ec2_spot_cost']:.2f}")
        print(f"  Data Transfer: ${aws['data_transfer_cost']:.2f}")
        print(f"  Total:         ${aws['total_cost']:.2f}")
    else:
        print("\nAWS: Not configured")

    # Save to file
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(baseline, indent=2))
    print(f"\nBaseline saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
