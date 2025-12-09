"""
AWS Cost Explorer API client.

Query AWS costs for Lambda, EC2 Spot, and data transfer to monitor
pipeline infrastructure costs.

Requires AWS credentials with ce:GetCostAndUsage permission.

ADR: 2025-12-08-clickhouse-data-pipeline-architecture
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


@dataclass
class AWSCost:
    """AWS cost breakdown by service."""

    lambda_cost: float
    ec2_spot_cost: float
    data_transfer_cost: float
    total_cost: float
    period_start: date
    period_end: date


class AWSCostExplorer:
    """
    Client for AWS Cost Explorer API.

    Requires AWS credentials configured via:
    - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    - AWS credentials file (~/.aws/credentials)
    - IAM role (when running on AWS)

    Required IAM permission: ce:GetCostAndUsage
    """

    def __init__(self, region: str | None = None) -> None:
        """
        Initialize Cost Explorer client.

        Args:
            region: AWS region. Defaults to AWS_DEFAULT_REGION env var or us-west-2.
        """
        import os

        self.region = region or os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
        self._client = None

    @property
    def client(self) -> Any:
        """Lazy-load boto3 Cost Explorer client."""
        if self._client is None:
            import boto3

            self._client = boto3.client("ce", region_name=self.region)
        return self._client

    def get_cost(self, days: int = 7) -> AWSCost:
        """
        Get AWS costs for pipeline-related services.

        Args:
            days: Number of days to query (default: 7)

        Returns:
            AWSCost with breakdown by service

        Raises:
            botocore.exceptions.ClientError: If API request fails
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        response = self.client.get_cost_and_usage(
            TimePeriod={
                "Start": start_date.isoformat(),
                "End": end_date.isoformat(),
            },
            Granularity="DAILY",
            Metrics=["BlendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            Filter={
                "Dimensions": {
                    "Key": "SERVICE",
                    "Values": [
                        "AWS Lambda",
                        "Amazon EC2 Spot",
                        "Amazon Elastic Compute Cloud - Compute",
                        "AWS Data Transfer",
                    ],
                }
            },
        )

        return self._parse_cost_response(response, start_date, end_date)

    def _parse_cost_response(
        self, response: dict[str, Any], start_date: date, end_date: date
    ) -> AWSCost:
        """Parse Cost Explorer response into AWSCost dataclass."""
        # Aggregate costs across all days
        lambda_cost = 0.0
        ec2_spot_cost = 0.0
        data_transfer_cost = 0.0

        for result in response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                service = group["Keys"][0]
                amount = float(group["Metrics"]["BlendedCost"]["Amount"])

                if service == "AWS Lambda":
                    lambda_cost += amount
                elif "Spot" in service or "EC2" in service:
                    ec2_spot_cost += amount
                elif "Transfer" in service:
                    data_transfer_cost += amount

        total_cost = lambda_cost + ec2_spot_cost + data_transfer_cost

        return AWSCost(
            lambda_cost=lambda_cost,
            ec2_spot_cost=ec2_spot_cost,
            data_transfer_cost=data_transfer_cost,
            total_cost=total_cost,
            period_start=start_date,
            period_end=end_date,
        )

    def get_daily_breakdown(self, days: int = 7) -> list[AWSCost]:
        """
        Get daily AWS cost breakdown.

        Args:
            days: Number of days to query (default: 7)

        Returns:
            List of AWSCost, one per day
        """
        results = []
        end_date = date.today()

        for i in range(days):
            day = end_date - timedelta(days=i)
            next_day = day + timedelta(days=1)

            response = self.client.get_cost_and_usage(
                TimePeriod={
                    "Start": day.isoformat(),
                    "End": next_day.isoformat(),
                },
                Granularity="DAILY",
                Metrics=["BlendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                Filter={
                    "Dimensions": {
                        "Key": "SERVICE",
                        "Values": [
                            "AWS Lambda",
                            "Amazon EC2 Spot",
                            "Amazon Elastic Compute Cloud - Compute",
                            "AWS Data Transfer",
                        ],
                    }
                },
            )

            results.append(self._parse_cost_response(response, day, day))

        return list(reversed(results))  # Chronological order
