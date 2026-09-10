# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

import subprocess
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cf_job_logs.cli import cli
from cf_job_logs.gh_auth import (
    GhCliUnavailableError,
    GitHubAuthMode,
    configure_github_auth,
    gh_cli_token,
    resolve_github_token,
)
from cf_job_logs.github_api import get_github_headers


@pytest.fixture(autouse=True)
def clear_token_cache():
    """`gh_cli_token` is cached process-wide, so drop it around every test."""
    gh_cli_token.cache_clear()
    yield
    gh_cli_token.cache_clear()


def mock_gh(returncode: int = 0, stdout: str = "gho_token\n", stderr: str = ""):
    """Patch `subprocess.run` so `gh auth token` returns the given result."""
    completed = subprocess.CompletedProcess(
        args=["gh", "auth", "token"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )
    return patch("cf_job_logs.gh_auth.subprocess.run", return_value=completed)


@pytest.fixture
def gh_on_path():
    with patch("cf_job_logs.gh_auth.shutil.which", return_value="/usr/bin/gh"):
        yield


def test_gh_cli_token_not_installed():
    """No token is returned if `gh` is not on PATH."""
    with patch("cf_job_logs.gh_auth.shutil.which", return_value=None) as which:
        assert gh_cli_token() is None
    which.assert_called_once_with("gh")


def test_gh_cli_token_success(gh_on_path):
    """The token printed by `gh auth token` is returned, stripped of whitespace."""
    with mock_gh(stdout="gho_token\n") as run:
        assert gh_cli_token() == "gho_token"

    args = run.call_args.args[0]
    assert args[:3] == ["/usr/bin/gh", "auth", "token"]


def test_gh_cli_token_logged_out(gh_on_path):
    """A non-zero exit code (e.g. not logged in) yields no token."""
    with mock_gh(returncode=1, stdout="", stderr="gh: not logged in"):
        assert gh_cli_token() is None


def test_gh_cli_token_empty_output(gh_on_path):
    """Empty output is treated as no token rather than an empty token."""
    with mock_gh(stdout="\n"):
        assert gh_cli_token() is None


@pytest.mark.parametrize(
    "error", [OSError("boom"), subprocess.TimeoutExpired(cmd="gh", timeout=10.0)]
)
def test_gh_cli_token_subprocess_error(gh_on_path, error):
    """Failures to even run `gh` are swallowed."""
    with patch("cf_job_logs.gh_auth.subprocess.run", side_effect=error):
        assert gh_cli_token() is None


def test_gh_cli_token_is_cached(gh_on_path):
    """`gh` is invoked at most once per process."""
    with mock_gh() as run:
        assert gh_cli_token() == "gho_token"
        assert gh_cli_token() == "gho_token"
    run.assert_called_once()


def test_auto_prefers_github_token(gh_on_path, monkeypatch):
    """GITHUB_TOKEN wins over the `gh` CLI so CI keeps using its own token."""
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    configure_github_auth(GitHubAuthMode.AUTO)

    with mock_gh() as run:
        assert resolve_github_token() == "env-token"
    run.assert_not_called()


def test_auto_falls_back_to_gh(gh_on_path, monkeypatch):
    """Without GITHUB_TOKEN, the `gh` CLI token is used."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    configure_github_auth(GitHubAuthMode.AUTO)

    with mock_gh():
        assert resolve_github_token() == "gho_token"


def test_auto_falls_back_to_anonymous(monkeypatch):
    """Without GITHUB_TOKEN and without `gh`, requests stay unauthenticated."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    configure_github_auth(GitHubAuthMode.AUTO)

    with patch("cf_job_logs.gh_auth.shutil.which", return_value=None):
        assert resolve_github_token() is None


def test_env_mode_ignores_gh(gh_on_path, monkeypatch):
    """`--no-gh` never invokes the `gh` CLI, but still honors GITHUB_TOKEN."""
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    configure_github_auth(GitHubAuthMode.ENV)

    with mock_gh() as run:
        assert resolve_github_token() == "env-token"
    run.assert_not_called()

    monkeypatch.delenv("GITHUB_TOKEN")
    with mock_gh() as run:
        assert resolve_github_token() is None
    run.assert_not_called()


def test_gh_mode_ignores_github_token(gh_on_path, monkeypatch):
    """`--gh` uses the `gh` CLI token even if GITHUB_TOKEN is set."""
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    with mock_gh():
        configure_github_auth(GitHubAuthMode.GH)
        assert resolve_github_token() == "gho_token"


def test_gh_mode_fails_fast_without_gh(monkeypatch):
    """Requesting `--gh` without a usable `gh` CLI is an error, not a silent fallback."""
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    with patch("cf_job_logs.gh_auth.shutil.which", return_value=None):
        with pytest.raises(GhCliUnavailableError, match="gh auth login"):
            configure_github_auth(GitHubAuthMode.GH)


def test_get_github_headers_includes_token(gh_on_path, monkeypatch):
    """The resolved token ends up in the Authorization header."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    configure_github_auth(GitHubAuthMode.AUTO)

    with mock_gh():
        assert get_github_headers() == {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": "Bearer gho_token",
        }


def test_get_github_headers_without_token(monkeypatch):
    """Without a token, no Authorization header is sent."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    configure_github_auth(GitHubAuthMode.AUTO)

    with patch("cf_job_logs.gh_auth.shutil.which", return_value=None):
        assert get_github_headers() == {"Accept": "application/vnd.github.v3+json"}


def test_cli_gh_flag_reports_missing_gh(monkeypatch):
    """`--gh` without a logged-in `gh` CLI exits with an actionable message."""
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    with patch("cf_job_logs.gh_auth.shutil.which", return_value=None):
        result = CliRunner().invoke(cli, ["--gh", "list-jobs", "https://example.com"])

    assert result.exit_code != 0
    assert "gh auth login" in result.output
