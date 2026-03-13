# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import annotations

import base64
from enum import StrEnum
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class CIProvider(StrEnum):
    AZURE = "azure-pipelines"
    GITHUB_ACTIONS = "github-actions"


class CIResult(StrEnum):
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"
    SKIPPED = "skipped"

    # Coerce unknown results to "unknown" instead of raising an error
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> CIResult | None:
        """Normalize provider-specific result strings.

        Azure: https://learn.microsoft.com/en-us/rest/api/azure/devops/build/timeline/get?view=azure-devops-rest-7.1#taskresult
        GitHub: https://docs.github.com/rest/actions/workflow-jobs?apiVersion=2022-11-28
        """
        if not isinstance(value, str):
            return None

        aliases = {
            # Azure
            "abandoned": cls.CANCELED,
            "succeededWithIssues": cls.SUCCEEDED,
            # GitHub
            "success": cls.SUCCEEDED,
            "failure": cls.FAILED,
            "cancelled": cls.CANCELED,
            "timed_out": cls.FAILED,
            "action_required": cls.FAILED,
            "neutral": cls.SUCCEEDED,
            "stale": cls.FAILED,
        }
        return aliases.get(value, cls.UNKNOWN)


class LogInfo(BaseModel):
    """Information about a log file."""

    url: str


class CIRecord(BaseModel):
    """Base class for a CI job or task record."""

    id: str
    ci_provider: CIProvider
    parent_id: str | None = Field(None, alias="parentId")
    type: str
    name: str
    result: CIResult | None
    log: LogInfo | None = None


class TimelineRecord(CIRecord):
    """A timeline record from Azure DevOps."""

    ci_provider: Literal[CIProvider.AZURE] = CIProvider.AZURE

    def html_url(self, line_number: int | None = None) -> str:
        """Construct the Azure DevOps web UI URL for this timeline record.

        Rewrites the log URL to point to the web UI.
        The original log URL format is:
        https://dev.azure.com/conda-forge/<project_id>/_apis/build/builds/<build_id>/logs/<log_id>

        Args:
            line_number: Optional line number to link to a specific line.
        Returns:
            The Azure DevOps web UI URL for this timeline record.
        """
        if not self.log:
            return ""

        parsed = urlparse(self.log.url)
        path_parts = parsed.path.split("/")
        project_id = path_parts[2]
        build_id = path_parts[6]

        base_url = f"https://dev.azure.com/conda-forge/{project_id}/_build/results?buildId={build_id}&view=logs&j={self.parent_id}&t={self.id}"
        if line_number is not None:
            return f"{base_url}&l={line_number}"
        return base_url


class GitHubActionsRecord(CIRecord):
    """A record from GitHub Actions."""

    ci_provider: Literal[CIProvider.GITHUB_ACTIONS] = CIProvider.GITHUB_ACTIONS
    type: Literal["Task"] = "Task"

    @classmethod
    def from_check_run(
        cls, check_run: CheckRun, owner: str, repo: str
    ) -> GitHubActionsRecord:
        return cls.model_validate(
            {
                "id": str(check_run.id),
                "parentId": None,
                "type": "Task",
                "name": check_run.name,
                "result": check_run.conclusion,
                "log": {
                    "url": f"https://api.github.com/repos/{owner}/{repo}/actions/jobs/{check_run.id}/logs"
                },
            }
        )


class GithubApp(BaseModel):
    """GitHub App information."""

    slug: str


class CheckRun(BaseModel):
    """A GitHub check run."""

    id: int
    external_id: str | None
    conclusion: str | None
    name: str
    html_url: str | None = None
    app: GithubApp

    @property
    def build_info(self) -> tuple[str, str]:
        """Extract build_id and project_id from external_id.

        external_id format: <id>|<build_id>|<project_id>

        Returns:
            A tuple of (build_id, project_id)
        """
        if not self.external_id:
            raise ValueError("CheckRun has no external_id")

        _, build_id, project_id = self.external_id.split("|")
        return build_id, project_id

    @property
    def ci_provider(self) -> CIProvider | None:
        try:
            return CIProvider(self.app.slug)
        except ValueError:
            return None


class CheckRunsResponse(BaseModel):
    """Response from GitHub check runs API."""

    check_runs: list[CheckRun]


class PRRepo(BaseModel):
    """Repository information from GitHub PR."""

    full_name: str


class PRBranch(BaseModel):
    """Branch information from GitHub PR."""

    ref: str
    repo: PRRepo
    sha: str


class PullRequestResponse(BaseModel):
    """Response from GitHub PR API."""

    head: PRBranch
    base: PRBranch


class PRFile(BaseModel):
    """A file changed in a GitHub PR."""

    filename: str


class GitHubContentFile(BaseModel):
    """Response from GitHub contents API."""

    name: str
    content_base64: str | None = Field(None, alias="content")
    encoding: str | None = None
    html_url: str | None = None

    @property
    def content(self) -> str:
        """Decode the base64-encoded content.

        Returns:
            The decoded content as a UTF-8 string.

        Raises:
            ValueError: If content cannot be decoded.
            UnicodeDecodeError: If content is not valid UTF-8.
        """

        if not self.content_base64:
            raise ValueError("No content to decode")

        if self.encoding != "base64":
            raise ValueError(f"Unsupported encoding: {self.encoding}")

        return base64.b64decode(self.content_base64).decode("utf-8")
