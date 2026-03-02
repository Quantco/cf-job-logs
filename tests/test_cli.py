# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

from unittest.mock import patch

import pytest

from cf_job_logs.cli import main
from cf_job_logs.models import LogInfo, TimelineRecord

SAMPLE_RECORDS = [
    TimelineRecord(
        id="job-1",
        parentId=None,
        type="Job",
        name="linux_64",
        result="failed",
        log=None,
    ),
    TimelineRecord(
        id="task-1",
        parentId="job-1",
        type="Task",
        name="Run build",
        result="failed",
        log=LogInfo(url="https://example.com/log/1"),
    ),
    TimelineRecord(
        id="task-2",
        parentId="job-1",
        type="Task",
        name="Initialize job",
        result="succeeded",
        log=LogInfo(url="https://example.com/log/2"),
    ),
    TimelineRecord(
        id="task-3",
        parentId="job-1",
        type="Task",
        name="Checkout",
        result="succeeded",
        log=None,
    ),
]

PR_URL = "https://github.com/conda-forge/some-feedstock/pull/42"
PATCH_RECORDS = patch(
    "cf_job_logs.cli._get_timeline_records", return_value=SAMPLE_RECORDS
)
PATCH_RECORDS_EMPTY = patch("cf_job_logs.cli._get_timeline_records", return_value=[])


def test_list_jobs_default_shows_only_failed(capsys):
    """Default list-jobs shows only failed tasks."""
    with (
        patch("sys.argv", ["cf-job-logs", "list-jobs", PR_URL]),
        PATCH_RECORDS,
    ):
        main()

    output = capsys.readouterr().out
    assert "task-1" in output
    assert "Run build" in output
    assert "failed" in output
    # succeeded tasks should not appear
    assert "task-2" not in output
    assert "Initialize job" not in output


def test_list_jobs_all_flag(capsys):
    """--all flag shows all tasks with logs."""
    with (
        patch("sys.argv", ["cf-job-logs", "list-jobs", "--all", PR_URL]),
        PATCH_RECORDS,
    ):
        main()

    output = capsys.readouterr().out
    assert "task-1" in output
    assert "task-2" in output
    # task-3 has no log, should still be excluded
    assert "task-3" not in output


def test_list_jobs_shows_platform_from_parent(capsys):
    """Platform column shows parent record name."""
    with (
        patch("sys.argv", ["cf-job-logs", "list-jobs", "--all", PR_URL]),
        PATCH_RECORDS,
    ):
        main()

    output = capsys.readouterr().out
    assert "linux_64" in output


def test_list_jobs_empty(capsys):
    """Empty timeline prints a message."""
    with (
        patch("sys.argv", ["cf-job-logs", "list-jobs", PR_URL]),
        PATCH_RECORDS_EMPTY,
    ):
        main()

    output = capsys.readouterr().out
    assert "No tasks with logs found." in output


def test_list_jobs_prints_header(capsys):
    """Output includes a header row."""
    with (
        patch("sys.argv", ["cf-job-logs", "list-jobs", "--all", PR_URL]),
        PATCH_RECORDS,
    ):
        main()

    output = capsys.readouterr().out
    assert "ID" in output
    assert "Result" in output
    assert "Platform" in output
    assert "Name" in output


def test_download_log(capsys):
    """download-log prints sanitized log by default."""
    with (
        patch("sys.argv", ["cf-job-logs", "download-log", PR_URL, "task-1"]),
        PATCH_RECORDS,
        patch(
            "cf_job_logs.cli._fetch_raw_log",
            return_value="2025-01-01T00:00:00.0000000Z ERROR: Build failed",
        ) as mock_fetch,
    ):
        main()

    output = capsys.readouterr().out
    assert "2025-01-01T00:00:00" not in output
    assert "ERROR: Build failed" in output
    mock_fetch.assert_called_once_with("https://example.com/log/1")


def test_download_log_unknown_job_id(capsys):
    """download-log exits with error for unknown job ID."""
    with (
        patch("sys.argv", ["cf-job-logs", "download-log", PR_URL, "no-such-id"]),
        PATCH_RECORDS,
        pytest.raises(SystemExit, match="1"),
    ):
        main()

    err = capsys.readouterr().err
    assert "No job found with ID 'no-such-id'" in err


def test_download_log_job_without_log(capsys):
    """download-log exits with error when job has no log."""
    with (
        patch("sys.argv", ["cf-job-logs", "download-log", PR_URL, "task-3"]),
        PATCH_RECORDS,
        pytest.raises(SystemExit, match="1"),
    ):
        main()

    err = capsys.readouterr().err
    assert "has no log" in err


def test_download_log_no_sanitize(capsys):
    """download-log --no-sanitize outputs raw log with timestamps."""
    with (
        patch(
            "sys.argv",
            ["cf-job-logs", "download-log", "--no-sanitize", PR_URL, "task-1"],
        ),
        PATCH_RECORDS,
        patch(
            "cf_job_logs.cli._fetch_raw_log",
            return_value="2025-01-01T00:00:00.0000000Z ERROR: Build failed\n2025-01-01T00:00:01.0000000Z INFO: Done",
        ),
    ):
        main()

    output = capsys.readouterr().out
    # Timestamps should be preserved
    assert "2025-01-01T00:00:00" in output
    assert "ERROR: Build failed" in output
    assert "INFO: Done" in output


def test_download_log_no_sanitize_unknown_job_id(capsys):
    """download-log --no-sanitize exits with error for unknown job ID."""
    with (
        patch(
            "sys.argv",
            ["cf-job-logs", "download-log", "--no-sanitize", PR_URL, "no-such-id"],
        ),
        PATCH_RECORDS,
        pytest.raises(SystemExit, match="1"),
    ):
        main()

    err = capsys.readouterr().err
    assert "No job found with ID 'no-such-id'" in err


def test_download_log_no_sanitize_job_without_log(capsys):
    """download-log --no-sanitize exits with error when job has no log."""
    with (
        patch(
            "sys.argv",
            ["cf-job-logs", "download-log", "--no-sanitize", PR_URL, "task-3"],
        ),
        PATCH_RECORDS,
        pytest.raises(SystemExit, match="1"),
    ):
        main()

    err = capsys.readouterr().err
    assert "has no log" in err


def test_no_command_exits():
    """Running without a subcommand exits with error."""
    with (
        patch("sys.argv", ["cf-job-logs"]),
        pytest.raises(SystemExit, match="2"),
    ):
        main()


def test_verbose_flag(capsys):
    """The -v flag is accepted."""
    with (
        patch("sys.argv", ["cf-job-logs", "-v", "list-jobs", PR_URL]),
        PATCH_RECORDS_EMPTY,
    ):
        main()

    output = capsys.readouterr().out
    assert "No tasks with logs found." in output
