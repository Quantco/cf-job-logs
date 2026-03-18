# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause


import pytest

from cf_job_logs.models import (
    CheckRun,
    CIProvider,
    CIResult,
    GitHubActionsRecord,
    GithubApp,
    LogInfo,
    TimelineRecord,
)


def test_timeline_record_html_url():
    """Test TimelineRecord.html_url extracts build_id and project_id from log URL."""
    record = TimelineRecord(
        id="9eb77fd2-8ddd-5444-8fc0-71cb28dcb736",
        parentId="7b6f2c87-f3a7-5133-8d84-7c03a75d9dfc&t=9eb77fd2-8ddd-5444-8fc0-71cb28dcb736",
        type="Task",
        name="Build",
        result=CIResult.FAILED,
        log=LogInfo(
            url="https://dev.azure.com/conda-forge/feedstock-builds/_apis/build/builds/1394602/logs/4"
        ),
    )

    url = record.html_url()

    assert url == (
        "https://dev.azure.com/conda-forge/feedstock-builds/_build/results?buildId=1394602&view=logs&j=7b6f2c87-f3a7-5133-8d84-7c03a75d9dfc&t=9eb77fd2-8ddd-5444-8fc0-71cb28dcb736&t=9eb77fd2-8ddd-5444-8fc0-71cb28dcb736"
    )


def test_timeline_record_html_url_with_line_number():
    """Test TimelineRecord.html_url includes line number when provided."""
    record = TimelineRecord(
        id="9eb77fd2-8ddd-5444-8fc0-71cb28dcb736",
        parentId="7b6f2c87-f3a7-5133-8d84-7c03a75d9dfc&t=9eb77fd2-8ddd-5444-8fc0-71cb28dcb736",
        type="Task",
        name="Build",
        result=CIResult.FAILED,
        log=LogInfo(
            url="https://dev.azure.com/conda-forge/feedstock-builds/_apis/build/builds/1394602/logs/4"
        ),
    )

    url = record.html_url(line_number=42)

    assert url == (
        "https://dev.azure.com/conda-forge/feedstock-builds/_build/results?buildId=1394602&view=logs&j=7b6f2c87-f3a7-5133-8d84-7c03a75d9dfc&t=9eb77fd2-8ddd-5444-8fc0-71cb28dcb736&t=9eb77fd2-8ddd-5444-8fc0-71cb28dcb736&l=42"
    )


def test_timeline_record_html_url_without_log():
    """Test TimelineRecord.html_url returns empty string when no log."""
    record = TimelineRecord(
        id="task-123",
        parentId="job-456",
        type="Task",
        name="Build",
        result=CIResult.FAILED,
        log=None,
    )

    url = record.html_url()

    assert url == ""


def test_check_run_build_info():
    """Test CheckRun model can be instantiated with a conclusion."""
    check_run = CheckRun(
        id=1,
        status="completed",
        conclusion="failure",
        external_id="12345|67890|abc-def-ghi",
        name="Test Check",
        app=GithubApp(slug="test-app"),
    )

    build_id, project_id = check_run.build_info
    assert build_id == "67890"
    assert project_id == "abc-def-ghi"


def test_github_actions_record_defaults():
    """Test GitHubActionsRecord has correct defaults for type and parent_id."""
    record = GitHubActionsRecord(
        id="12345",
        parentId=None,
        name="Build",
        result=CIResult.FAILED,
    )

    assert record.type == "Task"
    assert record.parent_id is None
    assert record.ci_provider == CIProvider.GITHUB_ACTIONS


def test_github_actions_record_from_check_run():
    """Test GitHubActionsRecord can be created from a CheckRun."""
    check_run = CheckRun(
        id=12345,
        status="completed",
        conclusion="failure",
        external_id="",
        name="Build linux-64",
        app=GithubApp(slug="github-actions"),
    )

    record = GitHubActionsRecord.from_check_run(check_run, owner="owner", repo="repo")

    assert record.id == "12345"
    assert record.name == "Build linux-64"
    assert record.ci_provider == CIProvider.GITHUB_ACTIONS
    assert record.result == CIResult.FAILED
    assert record.log
    assert (
        record.log.url
        == "https://api.github.com/repos/owner/repo/actions/jobs/12345/logs"
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        # Direct members
        ("failed", CIResult.FAILED),
        ("succeeded", CIResult.SUCCEEDED),
        ("canceled", CIResult.CANCELED),
        ("skipped", CIResult.SKIPPED),
        # Azure aliases
        ("abandoned", CIResult.CANCELED),
        ("succeededWithIssues", CIResult.SUCCEEDED),
        # GitHub aliases
        ("success", CIResult.SUCCEEDED),
        ("failure", CIResult.FAILED),
        ("cancelled", CIResult.CANCELED),
        ("timed_out", CIResult.FAILED),
        ("action_required", CIResult.FAILED),
        ("neutral", CIResult.SUCCEEDED),
        ("stale", CIResult.FAILED),
    ],
)
def test_ci_result_normalizes_provider_values(value: str, expected: CIResult):
    """CIResult handles all known Azure and GitHub result strings."""
    assert CIResult(value) == expected


def test_ci_result_unknown_value():
    """Unrecognized result strings resolve to UNKNOWN."""
    assert CIResult("some_unknown_result") == CIResult.UNKNOWN
