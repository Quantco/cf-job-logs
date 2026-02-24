# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

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


def _fetch_review_queue_urls() -> list[str]:
    """Fetch open PRs from the conda-forge review queue."""
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

    return [item["html_url"] for item in data.get("items", [])]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_download_prs() -> None:
    """Downloads PRs and verifies the results."""
    urls = _fetch_review_queue_urls()
    assert urls, "No PRs found in the review queue"

    for pr_url in urls:
        try:
            result = await download_pr_async(
                pr_url,
                http_timeout=HTTP_TIMEOUT,
            )
        except BuildLogsUnavailableError:
            pytest.skip(f"Build logs unavailable for PR: {pr_url}, skipping test.")

        assert result.recipe.content
        assert result.pr_info.owner
        assert result.pr_info.repo
        assert result.pr_info.pr_number > 0
        assert len(result.check_runs) > 0
