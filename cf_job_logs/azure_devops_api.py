# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause


import logging

import httpx

from cf_job_logs.models import TimelineRecord

logger = logging.getLogger(__name__)


class BuildLogsUnavailableError(Exception):
    """Raised when build logs are not available (e.g., deleted or expired)."""


def fetch_azure_steps(
    http_client: httpx.Client, project_id: str, build_id: str
) -> list[TimelineRecord]:
    """Fetches FailedSteps from Azure DevOps timeline.

    Args:
        http_client: The HTTP client to use for requests.
        project_id: The Azure DevOps project ID.
        build_id: The build ID.

    Returns:
        List of failed steps with their platform information.

    Raises:
        BuildLogsUnavailableError: If the build timeline is not found (404).
    """
    try:
        timeline_resp = http_client.get(
            f"https://dev.azure.com/conda-forge/{project_id}/_apis/build/builds/{build_id}/timeline?api-version=7.1",
            headers={"Accept": "application/json"},
        )
        logger.debug("Fetching timeline from Azure DevOps API: %s", timeline_resp.url)
        timeline_resp.raise_for_status()
        data = timeline_resp.json()
        return [
            TimelineRecord.model_validate(record_data)
            for record_data in data.get("records", [])
        ]
    except httpx.HTTPError as e:
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
            raise BuildLogsUnavailableError(
                "Build logs are not available. They may have been deleted or expired."
            ) from e
        raise RuntimeError(f"Error fetching timeline: {e}") from e
