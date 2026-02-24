# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause


import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Concatenate
from urllib.parse import urlparse

import httpx

from cf_job_logs.models import (
    CheckRun,
    CheckRunsResponse,
    GitHubContentFile,
    PRFile,
    PullRequestResponse,
)

logger = logging.getLogger(__name__)

# Constants
GITHUB_API_BASE = "https://api.github.com"
DEFAULT_BRANCH = "main"
GITHUB_PER_PAGE = 100  # Maximum items per page for GitHub API
DEFAULT_RECIPE_PATHS = ["recipe/meta.yaml", "recipe/recipe.yaml"]


class RecipeNotFoundError(Exception):
    """Raised when the recipe file is not found in the PR branch."""


class InvalidPRURLError(Exception):
    """Raised when a PR URL cannot be parsed."""


class NoCompletedCheckRunsError(Exception):
    """Raised when no completed check runs are found for a commit."""


@dataclass
class PRInfo:
    """Parsed information from a GitHub PR URL."""

    owner: str
    repo: str
    pr_number: int


def get_github_headers() -> dict[str, str]:
    """Get headers for GitHub API requests with authentication if available.

    Returns:
        Dictionary with headers including Authorization if GITHUB_TOKEN is set.
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {github_token}"
    return headers


def paginate_github_api[T, **P](
    func: Callable[Concatenate[httpx.Client, P], list[T]],
) -> Callable[Concatenate[httpx.Client, P], list[T]]:
    """Decorator to handle pagination for GitHub API requests.

    This decorator wraps functions that make GitHub API requests and automatically
    handles pagination by fetching all pages of results.

    Args:
        func: The function to wrap. Should accept http_client as first parameter
              and return a list of items.

    Returns:
        A wrapped function that returns all paginated results.
    """

    @wraps(func)
    def wrapper(
        http_client: httpx.Client, *args: P.args, **kwargs: P.kwargs
    ) -> list[T]:
        all_items: list[T] = []
        page = 1
        while True:
            kwargs["page"] = page
            kwargs["per_page"] = GITHUB_PER_PAGE

            items = func(http_client, *args, **kwargs)
            all_items.extend(items)

            # If we got fewer items than per_page, we've reached the last page
            if len(items) < GITHUB_PER_PAGE:
                break
            page += 1
        return all_items

    return wrapper


def parse_pr_url(pr_url: str) -> PRInfo:
    """Parse a conda-forge PR URL to extract owner, repo, and PR number.

    Args:
        pr_url: The PR URL (e.g., https://github.com/conda-forge/feedstocks/pull/123)

    Returns:
        A PRInfo dataclass containing owner, repo, and pr_number

    Raises:
        InvalidPRURLError: If the URL cannot be parsed
    """
    # Extract path to handle URLs with fragments (e.g., #comment)
    parsed_url = urlparse(pr_url)
    path = parsed_url.path
    parts = path.rstrip("/").split("/")

    if parsed_url.netloc != "github.com":
        raise InvalidPRURLError(
            f"Invalid PR URL: {pr_url}.\n\nOnly github.com URLs are supported."
        )

    try:
        pull_idx = parts.index("pull")
        owner = parts[pull_idx - 2]
        repo = parts[pull_idx - 1]
        pr_number = int(parts[pull_idx + 1])
        return PRInfo(owner=owner, repo=repo, pr_number=pr_number)
    except (ValueError, IndexError):
        raise InvalidPRURLError(
            f"Invalid PR URL: `{pr_url}`.\n\n"
            "Please provide a valid GitHub PR URL in the format:\n"
            "`https://github.com/owner/repo/pull/number`"
        )


def fetch_pr_details(http_client: httpx.Client, pr_info: PRInfo) -> PullRequestResponse:
    """Fetch full PR details from GitHub API.

    Args:
        http_client: The HTTP client to use for the request.
        pr_info: Parsed PR information.

    Returns:
        The PR details including head and base branch information.

    Raises:
        RuntimeError: If fetching PR details fails.
    """
    try:
        response = http_client.get(
            f"{GITHUB_API_BASE}/repos/{pr_info.owner}/{pr_info.repo}/pulls/{pr_info.pr_number}",
            headers=get_github_headers(),
        )
        logger.debug("Fetching PR details from GitHub API: %s", response.url)
        response.raise_for_status()
        return PullRequestResponse.model_validate(response.json())
    except httpx.HTTPError as e:
        raise RuntimeError(f"Error fetching PR details: {e}") from e


@paginate_github_api
def fetch_github_check_runs(
    http_client: httpx.Client,
    pr_info: PRInfo,
    head_sha: str,
    page: int = 1,
    per_page: int = GITHUB_PER_PAGE,
) -> list[CheckRun]:
    """Get the check runs for a commit SHA in a PR.

    Args:
        http_client: The HTTP client to use for the request.
        pr_info: Parsed PR information.
        head_sha: The commit SHA to check.
        page: Page number to fetch (handled by decorator).
        per_page: Number of items per page (handled by decorator).

    Returns:
        A list of CheckRun objects for the commit.

    Raises:
        RuntimeError: If fetching check runs fails.
    """
    try:
        status_response = http_client.get(
            f"{GITHUB_API_BASE}/repos/{pr_info.owner}/{pr_info.repo}/commits/{head_sha}/check-runs",
            headers=get_github_headers(),
            params={"page": page, "per_page": per_page},
        )
        logger.debug(
            "Fetching check runs from GitHub API (page %d): %s",
            page,
            status_response.url,
        )
        status_response.raise_for_status()
        return CheckRunsResponse.model_validate(status_response.json()).check_runs
    except httpx.HTTPError as e:
        raise RuntimeError(f"Error fetching check runs: {e}") from e


def get_azure_build_info(
    check_runs: list[CheckRun],
) -> tuple[str, str]:
    """Extract build_id and project_id from completed check runs.

    Args:
        check_runs: List of CheckRun instances.
    Returns:
        A tuple of (build_id, project_id).
    Raises:
        NoCompletedCheckRunsError: If no completed check runs are found.
    """
    # Get completed Azure Pipelines check runs (conclusion is not None)
    azure_check_runs = [
        cr
        for cr in check_runs
        if cr.app.slug == "azure-pipelines" and cr.conclusion is not None
    ]

    # All azure check runs have the same external_id, so we can just pick the first valid one
    azure_check_run = next((cr for cr in azure_check_runs if cr.external_id), None)

    if not azure_check_run:
        raise NoCompletedCheckRunsError("No completed check runs found for the commit.")

    return azure_check_run.build_info


def try_fetch_github_file(
    http_client: httpx.Client, repo: str, ref: str, file_path: str
) -> GitHubContentFile | None:
    """Try to fetch a file from a GitHub repository at a specific ref.

    Args:
        http_client: The HTTP client to use for the request.
        repo: Full repository name (owner/repo).
        ref: Git ref (branch, tag, or commit SHA).
        file_path: Path to the file in the repository.

    Returns:
        A GitHubContentFile if found, else None.
    """
    try:
        url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{file_path}"
        resp = http_client.get(url, headers=get_github_headers(), params={"ref": ref})
        gh_file = GitHubContentFile.model_validate(resp.json())
        return gh_file
    except (httpx.HTTPError, ValueError):
        # Return None if the file is not found or cannot be decoded
        return None


@paginate_github_api
def fetch_changed_files_in_pr(
    http_client: httpx.Client,
    pr_info: PRInfo,
    page: int = 1,
    per_page: int = GITHUB_PER_PAGE,
) -> list[str]:
    """Get the list of changed files in a GitHub PR, handling pagination automatically.

    Args:
        http_client: The HTTP client to use for the request.
        pr_info: Parsed PR information containing owner, repo, and PR number.
        page: Page number to fetch (handled by decorator).
        per_page: Number of items per page (handled by decorator).

    Returns:
        A list of changed file paths in the PR.
    """
    try:
        response = http_client.get(
            f"{GITHUB_API_BASE}/repos/{pr_info.owner}/{pr_info.repo}/pulls/{pr_info.pr_number}/files",
            headers=get_github_headers(),
            params={"page": page, "per_page": per_page},
        )
        response.raise_for_status()
        logger.debug(
            "Fetching PR files from GitHub API (page %d): %s", page, response.url
        )
        files = [PRFile.model_validate(f) for f in response.json()]
        return [f.filename for f in files]
    except httpx.HTTPError as e:
        raise RuntimeError(f"Error fetching PR files: {e}") from e


def fetch_recipe_file(
    http_client: httpx.Client, pr_info: PRInfo, pr_data: PullRequestResponse
) -> GitHubContentFile:
    """Fetch the conda build recipe file (meta.yaml or recipe.yaml) for a GitHub PR.

    Fetches the recipe from the PR head branch only. Handles both regular feedstock
    repositories and staged-recipes repositories.

    Args:
        http_client: The HTTP client to use for the request.
        pr_info: Parsed PR information containing owner, repo, and PR number.
        pr_data: Pull request details containing head branch information.

    Returns:
        A GitHubContentFile containing the recipe content and URL.

    Raises:
        RecipeNotFoundError: If no recipe file is found in the PR branch.
    """

    changed_files = fetch_changed_files_in_pr(http_client, pr_info)
    recipe_paths = [
        path
        for path in changed_files
        if path.endswith("/meta.yaml") or path.endswith("/recipe.yaml")
    ]

    repo = pr_data.head.repo.full_name
    ref = pr_data.head.ref

    for recipe_path in recipe_paths or DEFAULT_RECIPE_PATHS:
        recipe_file = try_fetch_github_file(http_client, repo, ref, recipe_path)
        if recipe_file:
            return recipe_file

    raise RecipeNotFoundError(
        "Recipe file not found. The recipe might not exist anymore, "
        "or the branch may have been deleted."
    )
