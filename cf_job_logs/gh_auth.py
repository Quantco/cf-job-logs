# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

"""Resolution of the GitHub token used for API requests.

Unauthenticated GitHub API requests are limited to 60 requests per hour, which is
easily exhausted by a single PR inspection. Some endpoints (e.g. GitHub Actions job
logs) require authentication altogether. Besides `GITHUB_TOKEN`, we therefore also
support borrowing the token of a logged-in `gh` CLI.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from enum import StrEnum
from functools import cache
from typing import assert_never

logger = logging.getLogger(__name__)

GH_HOSTNAME = "github.com"
GH_TIMEOUT = 10.0


class GhCliUnavailableError(Exception):
    """Raised when the `gh` CLI cannot provide a token but was explicitly requested."""


class GitHubAuthMode(StrEnum):
    """How to obtain the token for GitHub API requests."""

    # `GITHUB_TOKEN`, else the `gh` CLI, else unauthenticated.
    AUTO = "auto"
    # Require a token from the `gh` CLI.
    GH = "gh"
    # `GITHUB_TOKEN` only, never invoke the `gh` CLI.
    ENV = "env"


_auth_mode = GitHubAuthMode.AUTO


def configure_github_auth(mode: GitHubAuthMode) -> None:
    """Set the process-wide mode used to resolve the GitHub token.

    Args:
        mode: The authentication mode to use for subsequent requests.

    Raises:
        GhCliUnavailableError: If mode is GH but the `gh` CLI provides no token.
    """
    global _auth_mode
    _auth_mode = mode

    # Fail fast so the user learns about a missing `gh` login before any request.
    if mode == GitHubAuthMode.GH and gh_cli_token() is None:
        raise GhCliUnavailableError(
            "`--gh` was requested but no token could be obtained from the `gh` CLI.\n\n"
            "Install it from https://cli.github.com and run `gh auth login`, "
            "or set `GITHUB_TOKEN` and pass `--no-gh` instead."
        )


@cache
def gh_cli_token() -> str | None:
    """Get the GitHub token of the logged-in `gh` CLI.

    The result is cached: `get_github_headers` is called once per request (and
    `wait-for-ci` polls in a loop), so we must not spawn a subprocess every time.

    Returns:
        The token, or None if `gh` is not installed or not logged in.
    """
    gh = shutil.which("gh")
    if gh is None:
        logger.debug("`gh` CLI not found on PATH.")
        return None

    try:
        proc = subprocess.run(
            [gh, "auth", "token", "--hostname", GH_HOSTNAME],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.debug("Could not run `gh auth token`: %s", e)
        return None

    if proc.returncode != 0:
        logger.debug("`gh auth token` failed: %s", proc.stderr.strip())
        return None

    return proc.stdout.strip() or None


def resolve_github_token() -> str | None:
    """Get the GitHub token for the configured authentication mode.

    `GITHUB_TOKEN` takes precedence over the `gh` CLI, so that CI environments keep
    using the token they provide.

    Returns:
        The token to authenticate with, or None to request anonymously.
    """
    match _auth_mode:
        case GitHubAuthMode.ENV:
            return os.getenv("GITHUB_TOKEN") or None
        case GitHubAuthMode.GH:
            return gh_cli_token()
        case GitHubAuthMode.AUTO:
            if github_token := os.getenv("GITHUB_TOKEN"):
                logger.debug(
                    "Authenticating with the `GITHUB_TOKEN` environment variable."
                )
                return github_token
            if gh_token := gh_cli_token():
                logger.debug("Authenticating with the token of the `gh` CLI.")
                return gh_token
            logger.debug(
                "No GitHub token available, sending unauthenticated requests. "
                "Run `gh auth login` or set `GITHUB_TOKEN` to raise the rate limit."
            )
            return None
        case _ as unreachable:
            assert_never(unreachable)
