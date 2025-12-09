"""
ClickHouse Cloud Billing API client.

Query usage costs from ClickHouse Cloud API for cost monitoring and optimization.

API Documentation: https://clickhouse.com/docs/en/cloud/manage/api/api-overview

ADR: 2025-12-08-clickhouse-data-pipeline-architecture
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx

# Environment variable names for API credentials
ENV_API_KEY_ID = "CLICKHOUSE_CLOUD_API_KEY_ID"
ENV_API_KEY_SECRET = "CLICKHOUSE_CLOUD_API_KEY_SECRET"
ENV_ORGANIZATION_ID = "CLICKHOUSE_CLOUD_ORG_ID"

# API base URL
API_BASE_URL = "https://api.clickhouse.cloud/v1"


@dataclass
class UsageCost:
    """ClickHouse Cloud usage cost breakdown."""

    compute_chc: float  # Compute units cost
    storage_chc: float  # Storage cost (compressed SSD)
    egress_chc: float  # Public data transfer cost
    total_chc: float  # Total cost
    period_start: date
    period_end: date

    @property
    def egress_gb_estimate(self) -> float:
        """Estimate egress GB from cost (at $0.115/GB)."""
        return self.egress_chc / 0.115 if self.egress_chc > 0 else 0.0


class ClickHouseCloudBilling:
    """
    Client for ClickHouse Cloud Billing API.

    Requires API credentials from ClickHouse Cloud console:
    Settings → API Keys → Create Key

    Store credentials in environment variables or .env file.
    """

    def __init__(
        self,
        api_key_id: str | None = None,
        api_key_secret: str | None = None,
        organization_id: str | None = None,
    ) -> None:
        """
        Initialize billing client.

        Args:
            api_key_id: ClickHouse Cloud API key ID. Defaults to env var.
            api_key_secret: ClickHouse Cloud API key secret. Defaults to env var.
            organization_id: ClickHouse Cloud organization ID. Defaults to env var.

        Raises:
            ValueError: If credentials are not provided or found in environment.
        """
        self.api_key_id = api_key_id or os.environ.get(ENV_API_KEY_ID)
        self.api_key_secret = api_key_secret or os.environ.get(ENV_API_KEY_SECRET)
        self.organization_id = organization_id or os.environ.get(ENV_ORGANIZATION_ID)

        if not all([self.api_key_id, self.api_key_secret, self.organization_id]):
            missing = []
            if not self.api_key_id:
                missing.append(ENV_API_KEY_ID)
            if not self.api_key_secret:
                missing.append(ENV_API_KEY_SECRET)
            if not self.organization_id:
                missing.append(ENV_ORGANIZATION_ID)
            raise ValueError(
                f"Missing ClickHouse Cloud API credentials: {', '.join(missing)}\n"
                "Get credentials from ClickHouse Cloud console: Settings → API Keys"
            )

    def get_usage_cost(self, days: int = 7) -> UsageCost:
        """
        Get usage costs for the specified period.

        Args:
            days: Number of days to query (default: 7)

        Returns:
            UsageCost with breakdown by category

        Raises:
            httpx.HTTPStatusError: If API request fails
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        url = f"{API_BASE_URL}/organizations/{self.organization_id}/usageCost"
        params = {
            "from_date": start_date.isoformat(),
            "to_date": end_date.isoformat(),
        }

        with httpx.Client() as client:
            response = client.get(
                url,
                params=params,
                auth=(self.api_key_id, self.api_key_secret),
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        return self._parse_usage_cost(data, start_date, end_date)

    def _parse_usage_cost(
        self, data: dict[str, Any], start_date: date, end_date: date
    ) -> UsageCost:
        """Parse API response into UsageCost dataclass."""
        # API returns costs in CHC (ClickHouse Credits) which map to USD
        costs = data.get("costs", {})

        return UsageCost(
            compute_chc=float(costs.get("computeUnitCHC", 0)),
            storage_chc=float(costs.get("storageCompressedSSDCHC", 0)),
            egress_chc=float(costs.get("publicDataTransferCHC", 0)),
            total_chc=float(costs.get("totalCHC", 0)),
            period_start=start_date,
            period_end=end_date,
        )

    def get_daily_breakdown(self, days: int = 7) -> list[UsageCost]:
        """
        Get daily usage cost breakdown.

        Args:
            days: Number of days to query (default: 7)

        Returns:
            List of UsageCost, one per day
        """
        results = []
        end_date = date.today()

        for i in range(days):
            day = end_date - timedelta(days=i)
            url = f"{API_BASE_URL}/organizations/{self.organization_id}/usageCost"
            params = {
                "from_date": day.isoformat(),
                "to_date": day.isoformat(),
            }

            with httpx.Client() as client:
                response = client.get(
                    url,
                    params=params,
                    auth=(self.api_key_id, self.api_key_secret),
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            results.append(self._parse_usage_cost(data, day, day))

        return list(reversed(results))  # Chronological order
