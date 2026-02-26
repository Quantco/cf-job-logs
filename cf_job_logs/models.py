# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

import base64
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class LogInfo(BaseModel):
    """Information about a log file from Azure DevOps."""

    url: str


class TimelineRecord(BaseModel):
    """A timeline record from Azure DevOps."""

    id: str
    parent_id: str | None = Field(None, alias="parentId")
    type: str
    name: str
    result: str | None
    log: LogInfo | None = None

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


class TimelineResponse(BaseModel):
    """Response from Azure DevOps timeline API."""

    records: list[TimelineRecord]


class GithubApp(BaseModel):
    """GitHub App information."""

    slug: str


class CheckRun(BaseModel):
    """A GitHub check run."""

    external_id: str | None
    conclusion: str | None
    name: str
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
