# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from cf_job_logs.azure_devops_api import BuildLogsUnavailableError
from cf_job_logs.download import download_pr_async
from cf_job_logs.github_api import get_github_headers

# --- Configuration ---
HTTP_TIMEOUT = 60.0
GITHUB_SEARCH_API = "https://api.github.com/search/issues"
NUM_PRS_TO_TEST = 4


@pytest.fixture(scope="session")
def review_queue_urls() -> list[str]:
    """Fetch open PRs from the conda-forge review queue."""

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        pytest.skip("GITHUB_TOKEN not set; skipping review queue PR fetching")

    one_day_ago = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")

    params = {
        "q": f"is:pr is:open user:conda-forge review-requested:xhochy status:failure created:<={one_day_ago}",
        "sort": "updated",
        "order": "desc",
        "per_page": str(NUM_PRS_TO_TEST),
    }

    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        response = client.get(
            GITHUB_SEARCH_API, headers=get_github_headers(), params=params
        )
        response.raise_for_status()
        data = response.json()

    urls = [item["html_url"] for item in data.get("items", [])]

    if not urls:
        pytest.fail("No PRs found in the review queue")

    return urls


@pytest.mark.asyncio
async def test_download_prs(review_queue_urls: list[str]) -> None:
    """Downloads PRs and categorizes them.

    Returns a PrTestSuite object containing results and the best LLM candidate.
    """

    for pr_url in review_queue_urls:
        try:
            result = await download_pr_async(
                pr_url,
                http_timeout=HTTP_TIMEOUT,
            )
        except BuildLogsUnavailableError:
            pytest.skip(f"Build logs unavailable for PR: {pr_url}, skipping test.")

        if not result or not result.recipe.content:
            raise ValueError("Download returned empty result or missing recipe")

        assert result.recipe.content is not None
        assert len(result.failed_steps) >= 0  # Can be zero if no failed steps
        assert result.pr_info.owner
        assert result.pr_info.repo
        assert result.pr_info.pr_number > 0
        assert len(result.check_runs) >= 0  # Can be zero if no check runs
