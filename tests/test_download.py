# Copyright (c) QuantCo 2025-2026
# SPDX-License-Identifier: LicenseRef-QuantCo

import pytest

from cf_job_logs.download import download_pr_async

HTTP_TIMEOUT = 60.0

TEST_PR_URLS: list[tuple[str, str]] = [
    ("bun-feedstock-pr10", "https://github.com/conda-forge/bun-feedstock/pull/10"),
]


@pytest.mark.vcr
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("test_id", "pr_url"), TEST_PR_URLS, ids=[t[0] for t in TEST_PR_URLS]
)
async def test_download_prs(test_id: str, pr_url: str) -> None:
    """Downloads PRs and validates the result structure."""
    result = await download_pr_async(pr_url, http_timeout=HTTP_TIMEOUT)

    assert result is not None
    assert result.recipe.content is not None
    assert len(result.failed_steps) > 0
    assert result.pr_info.owner
    assert result.pr_info.repo
    assert result.pr_info.pr_number > 0
    assert len(result.check_runs) > 0

    log_content = result.failed_steps[0].sanitized_log_content
    assert "Error: " in log_content
    assert "sha256 checksum validation failed" in log_content
