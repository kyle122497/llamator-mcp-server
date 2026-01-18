from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LlamatorRunToolResponse(BaseModel):
    """
    MCP tool response for LLAMATOR run operations.

    This schema is used by MCP tools to provide a stable, machine-readable
    contract for the tools endpoint.

    :param job_id: Job identifier.
    :param aggregated: Aggregated metrics by attacks.
    :param artifacts_download_url: Presigned download URL for the artifacts archive (if available).
    :param error_notice: A user-facing error message (if any).
    """

    model_config = ConfigDict(frozen=True)

    job_id: str = Field(min_length=1, max_length=200, description="Job identifier.")
    aggregated: dict[str, dict[str, int]] = Field(description="Aggregated metrics by attacks.")
    artifacts_download_url: str | None = Field(
        default=None,
        description="Presigned download URL for the artifacts archive (if available).",
    )
    error_notice: str | None = Field(
        default=None,
        description="A user-facing error message (if any).",
    )
