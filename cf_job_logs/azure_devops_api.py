# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause


import asyncio
import logging
import re
from dataclasses import dataclass

import httpx

from cf_job_logs.models import TimelineRecord, TimelineResponse

logger = logging.getLogger(__name__)


class BuildLogsUnavailableError(Exception):
    """Raised when build logs are not available (e.g., deleted or expired)."""


@dataclass
class FailedStepWithPlatform:
    """A failed build step for a specific platform."""

    task_name: str
    platform: str
    record: "TimelineRecord"


@dataclass
class FailedStepWithLog:
    """A failed step with its fetched log content."""

    step: FailedStepWithPlatform
    sanitized_log_content: str


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
        timeline = TimelineResponse.model_validate(timeline_resp.json())
        return timeline.records
    except httpx.HTTPError as e:
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
            raise BuildLogsUnavailableError(
                "Build logs are not available. They may have been deleted or expired."
            ) from e
        raise RuntimeError(f"Error fetching timeline: {e}") from e


def get_failed_steps_with_platform(
    all_records: list[TimelineRecord],
) -> list[FailedStepWithPlatform]:
    """Extract failed steps with their platforms from timeline records.

    Args:
        all_records: All timeline records from Azure DevOps.

    Returns:
        List of failed steps with platform information.
    """
    record_name_by_id = {record.id: record.name for record in all_records}

    return [
        FailedStepWithPlatform(
            task_name=record.name,
            platform=record_name_by_id.get(record.parent_id, "Unknown Platform")
            if record.parent_id
            else "Unknown Platform",
            record=record,
        )
        for record in all_records
        if record.log and record.result == "failed" and record.type == "Task"
    ]


def sanitize_log_text(log_text: str) -> str:
    """Remove timestamps from each line of the log text and filter out Azure DevOps
    directives.

    Args:
        log_text: The original log text.
    Returns:
        The log text with timestamps removed and Azure directives filtered out.
    """

    # Skip to relevant build output if possible
    if "rattler-build build" in log_text:
        start_log_idx = log_text.index("rattler-build build")
        log_text = log_text[start_log_idx:]
    elif "conda-build /home/conda/recipe_root" in log_text:
        start_log_idx = log_text.index("conda-build /home/conda/recipe_root")
        log_text = log_text[start_log_idx:]

    lines = log_text.splitlines()
    cleaned_lines = []

    for line in lines:
        # Remove timestamp prefixes
        cleaned = " ".join(line.split()[1:])

        # Filter out "copying ... -> ..." and "creating <path>" lines from build output
        # These are setuptools/distutils verbose output lines that add noise
        if re.match(r"^(│ │ )?copying\s+\S+\s+->\s+\S+", cleaned):
            continue
        if re.match(r"^(│ │ )?creating\s+\S+", cleaned):
            continue

        cleaned_lines.append(cleaned)

    return "\n".join(cleaned_lines)


async def fetch_log_async(client: httpx.AsyncClient, log_url: str) -> str:
    """Fetch log content from an Azure DevOps log URL asynchronously.

    Args:
        client: The async HTTP client to use for the request.
        log_url: The Azure DevOps log URL.
            Example: https://dev.azure.com/conda-forge/84710dde-1620-425b-80d0-4cf5baca359d/_apis/build/builds/1381444/logs/27

    Returns:
        The log content as a string with timestamps removed.

    Raises:
        httpx.HTTPError: If the HTTP request fails.
    """
    log_resp = await client.get(log_url, headers={"Accept": "text/plain"})
    log_resp.raise_for_status()
    log_text = log_resp.text

    return sanitize_log_text(log_text)


async def fetch_all_logs_async(
    failed_steps: list[FailedStepWithPlatform],
) -> list[FailedStepWithLog]:
    """Fetch all logs asynchronously.

    Args:
        failed_steps: List of failed steps with their records.
        event_loop: The event loop to use for async operations.

    Returns:
        List of failed steps with their log content.
    """

    # reuse a single client for all requests
    async with httpx.AsyncClient(timeout=30.0) as client:

        async def _fetch_all() -> list[FailedStepWithLog]:
            # Get all steps with logs
            steps_with_logs = [step for step in failed_steps if step.record.log]
            logger.debug("Fetching %d logs in parallel...", len(steps_with_logs))
            tasks = [
                fetch_log_async(client, step.record.log.url)
                for step in steps_with_logs
                if step.record.log
            ]
            results = await asyncio.gather(*tasks)

            return [
                FailedStepWithLog(
                    step=step,
                    sanitized_log_content=str(result),
                )
                for step, result in zip(steps_with_logs, results)
            ]

        return await _fetch_all()
