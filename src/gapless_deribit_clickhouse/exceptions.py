"""
Exception hierarchy for gapless-deribit-clickhouse.

All exceptions propagate up the stack - no silent catches or fallbacks.

ADR: 2025-12-03-deribit-options-clickhouse-pipeline
"""


class GaplessDeribitError(Exception):
    """Base exception for all gapless-deribit-clickhouse errors."""


class ConfigurationError(GaplessDeribitError):
    """Raised when configuration is invalid or missing."""


class CredentialError(ConfigurationError):
    """Raised when credentials cannot be resolved from any source."""


class APIError(GaplessDeribitError):
    """Raised when Deribit API returns an error."""


class RateLimitError(APIError):
    """Raised when Deribit API rate limit is exceeded."""


class ConnectionError(GaplessDeribitError):
    """Raised when connection to ClickHouse fails."""


class QueryError(GaplessDeribitError):
    """Raised when a ClickHouse query fails."""


class SchemaError(GaplessDeribitError):
    """Raised when schema validation or parsing fails."""


class InstrumentParseError(GaplessDeribitError):
    """Raised when instrument name cannot be parsed."""
