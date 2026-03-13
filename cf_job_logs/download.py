# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

import logging
from dataclasses import dataclass

import httpx

from cf_job_logs.fetch_records import (
    FailedStepWithLog,
    fetch_all_logs_async,
    fetch_ci_records,
    get_failed_steps_with_platform,
)
from cf_job_logs.github_api import (
    PRInfo,
    fetch_github_check_runs,
    fetch_pr_details,
    fetch_recipe_file,
    parse_pr_url,
)
from cf_job_logs.models import CheckRun, GitHubContentFile

logger = logging.getLogger(__name__)

# Constants
HTTP_TIMEOUT = 30.0


@dataclass
class DownloadResult:
    """Result of downloading PR data."""

    recipe: GitHubContentFile
    failed_steps: list[FailedStepWithLog]
    pr_info: PRInfo
    check_runs: list[CheckRun]


async def download_pr_async(
    pr_url: str,
    http_timeout: float = HTTP_TIMEOUT,
) -> DownloadResult:
    """Download recipe and failed step logs from a conda-forge PR URL.

    Args:
        pr_url: The GitHub PR URL.
        http_timeout: Timeout for HTTP requests in seconds.

    Returns:
        DownloadResult containing recipe, failed steps, pr_info, and check runs.

    Raises:
        InvalidPRURLError: If the PR URL cannot be parsed.
        RecipeNotFoundError: If the recipe file is not found.
        NoCompletedCheckRunsError: If no completed check runs are found.
        BuildLogsUnavailableError: If build logs cannot be fetched.
        RuntimeError: For other HTTP/API errors.
    """

    with httpx.Client(timeout=http_timeout) as http_client:
        logger.info("🔗 Parsing PR URL...")
        pr_info = parse_pr_url(pr_url)

        logger.info(
            f"👀 Fetching PR information for {pr_info.owner}/{pr_info.repo} #{pr_info.pr_number}..."
        )
        pr_details = fetch_pr_details(http_client, pr_info)
        head_sha = pr_details.head.sha

        logger.info("📩 Fetching recipe file...")
        recipe = fetch_recipe_file(http_client, pr_info, pr_details)

        logger.info("🔍 Fetching check runs...")
        check_runs = fetch_github_check_runs(http_client, pr_info, head_sha)

        logger.info("🏷️ Fetching CI records...")
        all_records = fetch_ci_records(http_client, check_runs, pr_info)

        logger.info("🔍 Extracting failed steps...")
        failed_steps = get_failed_steps_with_platform(all_records)

        logger.info("📥 Fetching logs...")
        failed_steps_with_logs = await fetch_all_logs_async(failed_steps)

        logger.info(
            f"✅ Download complete! Found {len(failed_steps_with_logs)} failed steps."
        )

    return DownloadResult(
        recipe=recipe,
        failed_steps=failed_steps_with_logs,
        pr_info=pr_info,
        check_runs=check_runs,
    )
