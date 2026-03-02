# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for CLI error cases that are hard to test with VCR."""

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
        id="task-without-log",
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


def test_list_jobs_empty(capsys):
    """Empty timeline prints a message."""
    with (
        patch("sys.argv", ["cf-job-logs", "list-jobs", PR_URL]),
        PATCH_RECORDS_EMPTY,
    ):
        main()

    output = capsys.readouterr().out
    assert "No tasks with logs found." in output


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
        patch("sys.argv", ["cf-job-logs", "download-log", PR_URL, "task-without-log"]),
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
