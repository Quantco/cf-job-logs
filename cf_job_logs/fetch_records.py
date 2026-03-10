# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause


import asyncio
import logging
from dataclasses import dataclass

import httpx

from cf_job_logs.azure_devops_api import fetch_azure_steps
from cf_job_logs.github_api import (
    NoCompletedCheckRunsError,
    PRInfo,
    get_azure_build_info,
)
from cf_job_logs.models import CheckRun, TimelineRecord
from cf_job_logs.sanitize import sanitize_log_text

logger = logging.getLogger(__name__)


@dataclass
class FailedStepWithPlatform:
    """A failed build step for a specific platform."""

    task_name: str
    platform: str
    record: TimelineRecord


@dataclass
class FailedStepWithLog:
    """A failed step with its fetched log content."""

    step: FailedStepWithPlatform
    sanitized_log_content: str


def fetch_timeline_records(
    http_client: httpx.Client,
    check_runs: list[CheckRun],
    pr_info: PRInfo,
) -> list[TimelineRecord]:
    """Fetch CI records for given GitHub check runs. Handles both Azure DevOps and GitHub Actions records.

    Args:
        http_client: The HTTP client to use for requests.
        check_runs: List of GitHub check runs from the PR.
        pr_info: Information about the PR (owner, repo, pr_number).
    Returns:
        List of CI records from both Azure DevOps and GitHub Actions.
    """

    records: list[TimelineRecord] = []

    azure_steps = [
        cr
        for cr in check_runs
        if cr.app.slug == "azure-pipelines" and cr.conclusion is not None
    ]

    if azure_steps:
        try:
            build_id, project_id = get_azure_build_info(azure_steps)
            records.extend(fetch_azure_steps(http_client, project_id, build_id))
        except NoCompletedCheckRunsError:
            pass  # No completed Azure check runs, continue

    return records


def get_failed_steps_with_platform(
    all_records: list[TimelineRecord],
) -> list[FailedStepWithPlatform]:
    """Extract failed steps with their platforms from CI records.

    Args:
        all_records: All CI records (any provider).

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


async def _fetch_log_async(client: httpx.AsyncClient, record: TimelineRecord) -> str:
    """Fetch log content for a CI record (Azure or GitHub Actions) asynchronously.

    Args:
        client: The async HTTP client to use for the request.
        record: The TimelineRecord containing the log URL.

    Returns:
        The log content as a string with timestamps removed.

    Raises:
        httpx.HTTPError: If the HTTP request fails.
    """

    if not record.log:
        raise ValueError("Record does not contain log information.")

    resp = await client.get(record.log.url, headers={"Accept": "text/plain"})
    resp.raise_for_status()
    return sanitize_log_text(resp.text)


async def fetch_all_logs_async(
    failed_steps: list[FailedStepWithPlatform],
) -> list[FailedStepWithLog]:
    """Fetch all logs asynchronously.

    Args:
        failed_steps: List of failed steps with their records.

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
                _fetch_log_async(client, step.record)
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
