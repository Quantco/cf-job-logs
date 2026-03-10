# Copyright (c) QuantCo 2025-2026
# SPDX-License-Identifier: LicenseRef-QuantCo

import pytest

from cf_job_logs.download import (
    download_pr_async,
)
from cf_job_logs.models import (
    CIProvider,
)

HTTP_TIMEOUT = 60.0


@pytest.mark.vcr
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pr_url,expected_error,expected_providers",
    [
        pytest.param(
            "https://github.com/conda-forge/bun-feedstock/pull/10",
            "sha256 checksum validation failed",
            set([CIProvider.AZURE]),
            id="bun-feedstock-pr10",
        ),
        pytest.param(
            "https://github.com/conda-forge/tensorflow-feedstock/pull/474/checks",
            "Label '@com_github_grpc_grpc//bazel:grpc_deps.bzl' is invalid because 'bazel' is not a package;",
            set([CIProvider.GITHUB_ACTIONS]),
            id="tensorflow-feedstock-pr474",
        ),
        pytest.param(
            "https://github.com/conda-forge/jaxlib-feedstock/pull/336/checks",
            "This job was abandoned.",
            set([CIProvider.GITHUB_ACTIONS, CIProvider.AZURE]),
            id="jaxlib-feedstock-pr336",
        ),
    ],
)
async def test_download_prs(pr_url, expected_error, expected_providers):
    """Downloads PRs and validates the result structure."""
    result = await download_pr_async(pr_url, http_timeout=HTTP_TIMEOUT)

    assert result is not None
    assert result.recipe.content is not None
    assert len(result.failed_steps) > 0
    assert result.pr_info.owner
    assert result.pr_info.repo
    assert result.pr_info.pr_number > 0
    assert len(result.check_runs) > 0

    log_contents = (step.sanitized_log_content for step in result.failed_steps)
    assert any(expected_error in log_content for log_content in log_contents)

    all_providers = {
        cr.ci_provider for cr in result.check_runs if cr.ci_provider is not None
    }
    assert expected_providers == all_providers
