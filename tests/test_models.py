# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause


from cf_job_logs.models import (
    CheckRun,
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
        result="failed",
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
        result="failed",
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
        result="failed",
        log=None,
    )

    url = record.html_url()

    assert url == ""


def test_check_run_build_info():
    """Test CheckRun model can be instantiated with a conclusion."""
    check_run = CheckRun(
        conclusion="failure",
        external_id="12345|67890|abc-def-ghi",
        name="Test Check",
        app=GithubApp(slug="test-app"),
    )

    build_id, project_id = check_run.build_info
    assert build_id == "67890"
    assert project_id == "abc-def-ghi"
