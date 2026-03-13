# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

from cf_job_logs.github_api import (
    GITHUB_PER_PAGE,
    InvalidPRURLError,
    NoCompletedCheckRunsError,
    PRInfo,
    RecipeNotFoundError,
    fetch_changed_files_in_pr,
    fetch_github_check_runs,
    fetch_pr_details,
    fetch_recipe_file,
    get_azure_build_info,
    parse_pr_url,
    try_fetch_github_file,
)
from cf_job_logs.models import PRBranch, PRRepo, PullRequestResponse

requires_github_token = pytest.mark.skipif(
    not os.environ.get("GITHUB_TOKEN"),
    reason="GITHUB_TOKEN environment variable not set",
)


def test_parse_pr_url():
    """Test the parse_pr_url function."""
    pr_url = "https://github.com/conda-forge/feedstocks/pull/123"
    pr_info = parse_pr_url(pr_url)
    assert pr_info.owner == "conda-forge"
    assert pr_info.repo == "feedstocks"
    assert pr_info.pr_number == 123

    pr_url = "https://github.com/conda-forge/hpp-gui-feedstock/pull/22#issuecomment-3546665651"
    pr_info = parse_pr_url(pr_url)
    assert pr_info.owner == "conda-forge"
    assert pr_info.repo == "hpp-gui-feedstock"
    assert pr_info.pr_number == 22


def test_parse_pr_url_invalid_url():
    """Test the parse_pr_url function with an invalid URL."""
    pr_url = "https://something_else.com/conda-forge/hpp-gui-feedstock/pull/123"
    with pytest.raises(InvalidPRURLError):
        parse_pr_url(pr_url)

    pr_url = "https://github.com/conda-forge/hpp-gui-feedstock"
    with pytest.raises(InvalidPRURLError):
        parse_pr_url(pr_url)


def test_fetch_pr_details(mock_httpx_client):
    """Test fetch_pr_details returns full PR information including head and base
    branches."""
    pr_info = PRInfo(owner="conda-forge", repo="mock-repo", pr_number=123)

    expected_url = f"https://api.github.com/repos/{pr_info.owner}/{pr_info.repo}/pulls/{pr_info.pr_number}"
    mock_client = mock_httpx_client(
        json_data={
            "head": {
                "sha": "abc123def456",
                "ref": "feature-branch",
                "repo": {"full_name": "conda-forge/mock-repo"},
            },
            "base": {
                "sha": "def456abc789",
                "ref": "main",
                "repo": {"full_name": "conda-forge/mock-repo"},
            },
        },
        expected_url=expected_url,
    )

    result = fetch_pr_details(mock_client, pr_info)

    assert result.head.sha == "abc123def456"
    assert result.head.ref == "feature-branch"
    assert result.head.repo.full_name == "conda-forge/mock-repo"
    assert result.base.sha == "def456abc789"
    assert result.base.ref == "main"
    assert result.base.repo.full_name == "conda-forge/mock-repo"
    mock_client.get.assert_called_once()


def test_fetch_github_check_runs(mock_httpx_client):
    """Test fetch_github_check_runs returns check runs from GitHub API."""
    pr_info = PRInfo(owner="conda-forge", repo="feedstock", pr_number=123)
    head_sha = "abc123def456"

    expected_url = f"https://api.github.com/repos/{pr_info.owner}/{pr_info.repo}/commits/{head_sha}/check-runs"
    mock_client = mock_httpx_client(
        json_data={
            "check_runs": [
                {
                    "id": 1,
                    "conclusion": None,
                    "external_id": "12345|11111|still-running-1",
                    "name": "linux_64",
                    "app": {"slug": "azure-pipelines"},
                },
                {
                    "id": 2,
                    "conclusion": "failure",
                    "external_id": "12345|67890|abc-def-ghi",
                    "name": "win_64",
                    "app": {"slug": "azure-pipelines"},
                },
                {
                    "id": 3,
                    "conclusion": "success",
                    "external_id": "other|99999|other-id",
                    "name": "other-check",
                    "app": {"slug": "github-actions"},
                },
            ]
        },
        expected_url=expected_url,
    )

    check_runs = fetch_github_check_runs(mock_client, pr_info, head_sha)

    assert len(check_runs) == 3
    assert check_runs[0].conclusion is None
    assert check_runs[0].name == "linux_64"
    assert check_runs[1].conclusion == "failure"
    assert check_runs[1].external_id == "12345|67890|abc-def-ghi"
    assert check_runs[2].app.slug == "github-actions"
    mock_client.get.assert_called_once()


def test_fetch_github_check_runs_empty(mock_httpx_client):
    """Test fetch_github_check_runs returns empty list when no check runs found."""
    pr_info = PRInfo(owner="conda-forge", repo="feedstock", pr_number=123)
    head_sha = "abc123def456"

    expected_url = f"https://api.github.com/repos/{pr_info.owner}/{pr_info.repo}/commits/{head_sha}/check-runs"
    mock_client = mock_httpx_client(
        json_data={"check_runs": []},
        expected_url=expected_url,
    )

    check_runs = fetch_github_check_runs(mock_client, pr_info, head_sha)
    assert check_runs == []
    mock_client.get.assert_called_once()


def test_get_azure_build_info_extracts_build_info():
    """Test get_azure_build_info extracts build_id and project_id from Azure Pipelines
    check runs."""
    from cf_job_logs.models import CheckRun, GithubApp

    check_runs = [
        CheckRun(
            id=1,
            conclusion="success",
            external_id="other|11111|other-id",
            name="other-check",
            app=GithubApp(slug="github-actions"),
        ),
        CheckRun(
            id=2,
            conclusion="failure",
            external_id="12345|67890|abc-def-ghi",
            name="azure-check",
            app=GithubApp(slug="azure-pipelines"),
        ),
    ]

    build_id, project_id = get_azure_build_info(check_runs)

    assert build_id == "67890"
    assert project_id == "abc-def-ghi"


def test_get_azure_build_info_raises_when_no_valid_check_runs():
    """Test get_azure_build_info raises NoCompletedCheckRunsError when no valid Azure
    check runs found."""
    from cf_job_logs.models import CheckRun, GithubApp

    # No Azure Pipelines check runs
    check_runs = [
        CheckRun(
            id=1,
            conclusion="success",
            external_id="other|11111|other-id",
            name="other-check",
            app=GithubApp(slug="github-actions"),
        ),
    ]

    with pytest.raises(
        NoCompletedCheckRunsError, match="No completed check runs found"
    ):
        get_azure_build_info(check_runs)

    # Azure check run but no external_id
    check_runs = [
        CheckRun(
            id=2,
            conclusion="failure",
            external_id=None,
            name="azure-check",
            app=GithubApp(slug="azure-pipelines"),
        ),
    ]

    with pytest.raises(
        NoCompletedCheckRunsError, match="No completed check runs found"
    ):
        get_azure_build_info(check_runs)


def test_fetch_pr_details_handles_http_error(mock_httpx_client):
    """Test fetch_pr_details raises RuntimeError when HTTP request fails."""
    pr_info = PRInfo(owner="conda-forge", repo="mock-repo", pr_number=123)

    expected_url = f"https://api.github.com/repos/{pr_info.owner}/{pr_info.repo}/pulls/{pr_info.pr_number}"
    mock_client = mock_httpx_client(
        json_data={
            "head": {
                "sha": "abc123def456",
                "ref": "feature-branch",
                "repo": {"full_name": "conda-forge/mock-repo"},
            },
            "base": {
                "sha": "def456abc789",
                "ref": "main",
                "repo": {"full_name": "conda-forge/mock-repo"},
            },
        },
        expected_url=expected_url,
        raise_for_status_side_effect=httpx.HTTPError("Connection error"),
    )

    with pytest.raises(RuntimeError):
        fetch_pr_details(mock_client, pr_info)
    mock_client.get.assert_called_once()


def test_fetch_check_run_status_handles_http_error(mock_httpx_client):
    """Test fetch_check_run_status raises RuntimeError when HTTP request fails."""
    pr_info = PRInfo(owner="conda-forge", repo="feedstock", pr_number=123)
    head_sha = "abc123def456"

    expected_url = f"https://api.github.com/repos/{pr_info.owner}/{pr_info.repo}/commits/{head_sha}/check-runs"
    mock_client = mock_httpx_client(
        json_data={
            "check_runs": [
                {"conclusion": "failure", "external_id": "12345|67890|abc-def-ghi"}
            ]
        },
        expected_url=expected_url,
        raise_for_status_side_effect=httpx.HTTPError("Connection error"),
    )

    with pytest.raises(RuntimeError):
        fetch_github_check_runs(mock_client, pr_info, head_sha)

    mock_client.get.assert_called_once()


@requires_github_token
def test_fetch_changed_files_in_pr_regular_feedstock_online():
    """Test that get_changed_files_in_pr correctly identifies recipe files in a regular
    feedstock PR."""
    pr_info = PRInfo(owner="conda-forge", repo="fastapi-feedstock", pr_number=187)

    with httpx.Client(timeout=30.0) as http_client:
        recipe_files = fetch_changed_files_in_pr(http_client, pr_info)
    assert "recipe/recipe.yaml" in recipe_files


@requires_github_token
def test_fetch_changed_files_in_pr_staged_recipes_recipe_yaml_online():
    """Test fetch_changed_files_in_pr returns the correct changed recipe file for a
    staged-recipes PR with recipe.yaml."""
    pr_info = PRInfo(owner="conda-forge", repo="staged-recipes", pr_number=31205)

    with httpx.Client(timeout=30.0) as http_client:
        recipe_files = fetch_changed_files_in_pr(http_client, pr_info)
    assert "recipes/okd-install/recipe.yaml" in recipe_files


@requires_github_token
def test_fetch_changed_files_in_pr_staged_recipes_meta_yaml_online():
    """Test fetch_changed_files_in_pr returns the correct changed recipe file for a
    staged-recipes PR with meta.yaml."""
    pr_info = PRInfo(owner="conda-forge", repo="staged-recipes", pr_number=31610)

    with httpx.Client(timeout=30.0) as http_client:
        recipe_files = fetch_changed_files_in_pr(http_client, pr_info)
    assert "recipes/mammos-analysis/meta.yaml" in recipe_files


@requires_github_token
def test_try_fetch_github_file_online():
    """Test try_fetch_github_file fetches a file from a GitHub repository."""
    with httpx.Client(timeout=30.0) as http_client:
        result = try_fetch_github_file(
            http_client,
            repo="conda-forge/conda-forge-pinning-feedstock",
            ref="main",
            file_path="recipe/conda_build_config.yaml",
        )

    assert result is not None
    assert result.name == "conda_build_config.yaml"


@requires_github_token
def test_fetch_recipe_file_regular_feedstock_online():
    """Test fetch_recipe_file fetches the recipe file from a regular feedstock PR."""
    pr_info = PRInfo(owner="conda-forge", repo="fastapi-feedstock", pr_number=187)

    with httpx.Client(timeout=30.0) as http_client:
        pr_data = fetch_pr_details(http_client, pr_info)
        recipe_file = fetch_recipe_file(http_client, pr_info, pr_data)

    assert recipe_file is not None
    assert recipe_file.name == "recipe.yaml"


@requires_github_token
def test_fetch_recipe_file_staged_recipes_online():
    """Test fetch_recipe_file fetches the recipe file from a staged-recipes PR."""
    pr_info = PRInfo(owner="conda-forge", repo="staged-recipes", pr_number=31205)

    with httpx.Client(timeout=30.0) as http_client:
        pr_data = fetch_pr_details(http_client, pr_info)
        recipe_file = fetch_recipe_file(http_client, pr_info, pr_data)

    assert recipe_file is not None
    assert recipe_file.name == "recipe.yaml"


@patch("cf_job_logs.github_api.fetch_changed_files_in_pr")
@patch("cf_job_logs.github_api.try_fetch_github_file")
def test_fetch_recipe_file_raises_recipe_not_found_error(
    mock_try_fetch, mock_fetch_changed_files, mock_httpx_client
):
    """Test fetch_recipe_file raises RecipeNotFoundError when recipe file not found."""
    pr_info = PRInfo(owner="conda-forge", repo="mock-repo", pr_number=123)
    pr_data = PullRequestResponse(
        head=PRBranch(
            sha="abc123",
            ref="feature-branch",
            repo=PRRepo(full_name="conda-forge/mock-repo"),
        ),
        base=PRBranch(
            sha="def456",
            ref="main",
            repo=PRRepo(full_name="conda-forge/mock-repo"),
        ),
    )

    mock_client = mock_httpx_client(json_data={}, expected_url="")

    # Mock fetch_changed_files_in_pr to return a recipe path
    mock_fetch_changed_files.return_value = ["recipe/recipe.yaml"]
    # Mock try_fetch_github_file to return None (file not found)
    mock_try_fetch.return_value = None

    with pytest.raises(RecipeNotFoundError):
        fetch_recipe_file(mock_client, pr_info, pr_data)


def test_fetch_changed_files_in_pr_with_pagination():
    """Test fetch_changed_files_in_pr handles pagination correctly for PRs with many
    changed files."""

    pr_info = PRInfo(owner="conda-forge", repo="mock-repo", pr_number=123)

    # Simulate 3 pages of results
    # Page 1: GITHUB_PER_PAGE files
    # Page 2: GITHUB_PER_PAGE files
    # Page 3: GITHUB_PER_PAGE / 2 files
    page1_files = [
        {"filename": f"file_{i:03d}.py", "status": "modified"}
        for i in range(0, GITHUB_PER_PAGE)
    ]
    page2_files = [
        {"filename": f"file_{i:03d}.py", "status": "modified"}
        for i in range(GITHUB_PER_PAGE, 2 * GITHUB_PER_PAGE)
    ]
    page3_files = [
        {"filename": f"file_{i:03d}.py", "status": "modified"}
        for i in range(2 * GITHUB_PER_PAGE, int(2.5 * GITHUB_PER_PAGE))
    ]

    # Create mock responses for each page
    mock_response_1 = MagicMock()
    mock_response_1.json.return_value = page1_files
    mock_response_1.raise_for_status = MagicMock()

    mock_response_2 = MagicMock()
    mock_response_2.json.return_value = page2_files
    mock_response_2.raise_for_status = MagicMock()

    mock_response_3 = MagicMock()
    mock_response_3.json.return_value = page3_files
    mock_response_3.raise_for_status = MagicMock()

    # Create mock client that returns different responses for each call
    mock_client = MagicMock()
    mock_client.get.side_effect = [mock_response_1, mock_response_2, mock_response_3]

    # Call the function - with pagination, it should fetch all pages
    result = fetch_changed_files_in_pr(mock_client, pr_info)

    # Verify all 250 files from all 3 pages are returned
    expected_files = [f"file_{i:03d}.py" for i in range(0, int(2.5 * GITHUB_PER_PAGE))]

    assert result == expected_files, (
        "All files from all pages should be returned in order"
    )

    # Verify the client made 3 API calls (one per page)
    assert mock_client.get.call_count == 3, (
        f"Expected 3 API calls, got {mock_client.get.call_count}"
    )
