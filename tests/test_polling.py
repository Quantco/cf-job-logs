# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

from unittest.mock import MagicMock, patch

import httpx

from cf_job_logs.github_api import PRInfo
from cf_job_logs.models import CheckRun, GithubApp
from cf_job_logs.polling import (
    format_summary_table,
    wait_for_check_runs,
)


def _make_check_run(
    name: str,
    status: str = "completed",
    conclusion: str | None = "success",
    app_slug: str = "github-actions",
    id: int = 1,
) -> CheckRun:
    return CheckRun(
        id=id,
        external_id=None,
        status=status,
        conclusion=conclusion,
        name=name,
        html_url=f"https://github.com/example/run/{name}",
        app=GithubApp(slug=app_slug),
    )


PR_INFO = PRInfo(owner="conda-forge", repo="example-feedstock", pr_number=1)
HEAD_SHA = "abc123"


@patch("cf_job_logs.polling.time.sleep")
@patch("cf_job_logs.polling.fetch_github_check_runs")
def test_wait_all_completed_immediately(mock_fetch, mock_sleep):
    """When all check runs are already completed, return immediately."""
    mock_fetch.return_value = [
        _make_check_run("linux_64", conclusion="success"),
        _make_check_run("osx_64", conclusion="failure"),
    ]

    client = MagicMock(spec=httpx.Client)
    result = wait_for_check_runs(client, PR_INFO, HEAD_SHA)

    assert not result.timed_out
    assert not result.all_passed
    assert len(result.check_runs) == 2
    mock_sleep.assert_not_called()


@patch("cf_job_logs.polling.time.sleep")
@patch("cf_job_logs.polling.fetch_github_check_runs")
def test_wait_polls_until_complete(mock_fetch, mock_sleep):
    """Polls until in-progress runs complete."""
    mock_fetch.side_effect = [
        [
            _make_check_run("linux_64", status="in_progress", conclusion=None),
            _make_check_run("osx_64", conclusion="success"),
        ],
        [
            _make_check_run("linux_64", conclusion="success"),
            _make_check_run("osx_64", conclusion="success"),
        ],
    ]

    client = MagicMock(spec=httpx.Client)
    result = wait_for_check_runs(client, PR_INFO, HEAD_SHA, interval=1.0)

    assert not result.timed_out
    assert result.all_passed
    assert mock_fetch.call_count == 2
    mock_sleep.assert_called_once_with(1.0)


@patch("cf_job_logs.polling.time.monotonic")
@patch("cf_job_logs.polling.time.sleep")
@patch("cf_job_logs.polling.fetch_github_check_runs")
def test_wait_times_out(mock_fetch, mock_sleep, mock_monotonic):
    """Returns timed_out=True when timeout is exceeded."""
    mock_fetch.return_value = [
        _make_check_run("linux_64", status="in_progress", conclusion=None),
    ]
    # First call at start (0), second call after first poll (60 >= 10 timeout)
    mock_monotonic.side_effect = [0.0, 60.0]

    client = MagicMock(spec=httpx.Client)
    result = wait_for_check_runs(client, PR_INFO, HEAD_SHA, interval=1.0, timeout=10.0)

    assert result.timed_out
    assert not result.all_passed


@patch("cf_job_logs.polling.time.sleep")
@patch("cf_job_logs.polling.fetch_github_check_runs")
def test_wait_filters_unknown_providers(mock_fetch, mock_sleep):
    """Check runs from unknown CI providers are ignored."""
    mock_fetch.return_value = [
        _make_check_run("linux_64", conclusion="success"),
        _make_check_run("codecov", app_slug="codecov"),
    ]

    client = MagicMock(spec=httpx.Client)
    result = wait_for_check_runs(client, PR_INFO, HEAD_SHA)

    assert len(result.check_runs) == 1
    assert result.check_runs[0].name == "linux_64"
    assert result.all_passed


@patch("cf_job_logs.polling.time.sleep")
@patch("cf_job_logs.polling.fetch_github_check_runs")
def test_wait_retries_on_transient_error(mock_fetch, mock_sleep):
    """Retries on transient errors up to the limit."""
    mock_fetch.side_effect = [
        RuntimeError("Connection error"),
        [_make_check_run("linux_64", conclusion="success")],
    ]

    client = MagicMock(spec=httpx.Client)
    result = wait_for_check_runs(client, PR_INFO, HEAD_SHA, interval=1.0)

    assert not result.timed_out
    assert result.all_passed
    assert mock_fetch.call_count == 2


@patch("cf_job_logs.polling.time.monotonic")
@patch("cf_job_logs.polling.time.sleep")
@patch("cf_job_logs.polling.fetch_github_check_runs")
def test_wait_timeout_during_error_retry(mock_fetch, mock_sleep, mock_monotonic):
    """Returns timed_out=True when timeout exceeded during error retry."""
    mock_fetch.side_effect = RuntimeError("Connection error")
    # First call at start (0), second call after error exceeds timeout
    mock_monotonic.side_effect = [0.0, 15.0]

    client = MagicMock(spec=httpx.Client)
    result = wait_for_check_runs(client, PR_INFO, HEAD_SHA, interval=1.0, timeout=10.0)

    assert result.timed_out
    assert result.check_runs == []
    assert mock_fetch.call_count == 1
    mock_sleep.assert_not_called()


@patch("cf_job_logs.polling.time.sleep")
@patch("cf_job_logs.polling.fetch_github_check_runs")
def test_wait_calls_on_status_change(mock_fetch, mock_sleep):
    """on_status_change callback is called when statuses change."""
    mock_fetch.side_effect = [
        [_make_check_run("linux_64", status="in_progress", conclusion=None)],
        [_make_check_run("linux_64", status="in_progress", conclusion=None)],
        [_make_check_run("linux_64", conclusion="success")],
    ]

    callback = MagicMock()
    client = MagicMock(spec=httpx.Client)
    wait_for_check_runs(
        client, PR_INFO, HEAD_SHA, interval=1.0, on_status_change=callback
    )

    # Called twice: once for initial in_progress, once for completed (not for duplicate)
    assert callback.call_count == 2


@patch("cf_job_logs.polling.time.sleep")
@patch("cf_job_logs.polling.fetch_github_check_runs")
def test_wait_all_passed_with_skipped(mock_fetch, mock_sleep):
    """all_passed is True when conclusions are success, neutral, or skipped."""
    mock_fetch.return_value = [
        _make_check_run("linux_64", conclusion="success"),
        _make_check_run("osx_64", conclusion="skipped"),
        _make_check_run("win_64", conclusion="neutral"),
    ]

    client = MagicMock(spec=httpx.Client)
    result = wait_for_check_runs(client, PR_INFO, HEAD_SHA)

    assert result.all_passed


@patch("cf_job_logs.polling.time.sleep")
@patch("cf_job_logs.polling.fetch_github_check_runs")
def test_wait_no_relevant_check_runs_returns_immediately(mock_fetch, mock_sleep):
    """Returns immediately with empty result when no relevant CI check runs exist."""
    mock_fetch.return_value = [
        _make_check_run("codecov", app_slug="codecov"),
        _make_check_run("other-bot", app_slug="some-other-app"),
    ]

    client = MagicMock(spec=httpx.Client)
    result = wait_for_check_runs(client, PR_INFO, HEAD_SHA)

    assert not result.timed_out
    assert result.check_runs == []
    assert result.all_passed  # vacuously true
    mock_sleep.assert_not_called()


@patch("cf_job_logs.polling.time.sleep")
@patch("cf_job_logs.polling.fetch_github_check_runs")
def test_wait_status_change_stable_with_different_order(mock_fetch, mock_sleep):
    """on_status_change only fires when actual status changes, not API order changes."""
    # First poll returns runs in one order
    mock_fetch.side_effect = [
        [
            _make_check_run("aaa", status="in_progress", conclusion=None),
            _make_check_run("bbb", status="in_progress", conclusion=None),
        ],
        # Second poll returns same runs in different order - should NOT trigger callback
        [
            _make_check_run("bbb", status="in_progress", conclusion=None),
            _make_check_run("aaa", status="in_progress", conclusion=None),
        ],
        # Third poll has actual status change
        [
            _make_check_run("aaa", conclusion="success"),
            _make_check_run("bbb", conclusion="success"),
        ],
    ]

    callback = MagicMock()
    client = MagicMock(spec=httpx.Client)
    wait_for_check_runs(
        client, PR_INFO, HEAD_SHA, interval=1.0, on_status_change=callback
    )

    # Should be called exactly twice: initial state + completion (not for reordering)
    assert callback.call_count == 2


def test_format_summary_table_empty():
    assert "No relevant CI" in format_summary_table([])


def test_format_summary_table():
    summaries = [
        _make_check_run("linux_64", conclusion="success", id=101),
        _make_check_run("osx_64", conclusion="failure", id=102),
        _make_check_run("win_64", status="in_progress", conclusion=None, id=103),
    ]
    table = format_summary_table(summaries)
    assert "ID" in table
    assert "101" in table
    assert "102" in table
    assert "103" in table
    assert "linux_64" in table
    assert "succeeded" in table
    assert "failure" in table
    assert "in_progress" in table
