# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

import logging
import sys

import click
import httpx

from cf_job_logs.azure_devops_api import (
    fetch_azure_steps,
    sanitize_log_text,
)
from cf_job_logs.github_api import (
    fetch_github_check_runs,
    fetch_pr_details,
    get_azure_build_info,
    parse_pr_url,
)
from cf_job_logs.models import TimelineRecord

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 30.0


def _get_timeline_records(pr_url: str) -> list[TimelineRecord]:
    """Fetch Azure DevOps timeline records for a GitHub PR."""
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        pr_info = parse_pr_url(pr_url)
        pr_details = fetch_pr_details(client, pr_info)
        head_sha = pr_details.head.sha
        check_runs = fetch_github_check_runs(client, pr_info, head_sha)
        build_id, project_id = get_azure_build_info(check_runs)
        return fetch_azure_steps(client, project_id, build_id)


def _fetch_raw_log(log_url: str) -> str:
    """Fetch raw log content from Azure DevOps."""
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        resp = client.get(log_url, headers={"Accept": "text/plain"})
        resp.raise_for_status()
        return resp.text


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Fetch and inspect conda-forge Azure CI logs."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(message)s",
    )


@cli.command("list-jobs")
@click.argument("pr_url")
@click.option(
    "--all",
    is_flag=True,
    help="List all jobs, not just failed ones.",
)
def list_jobs(pr_url: str, all: bool) -> None:
    """List all jobs for a PR."""
    records = _get_timeline_records(pr_url)
    name_by_id = {r.id: r.name for r in records}
    tasks = [r for r in records if r.log and r.type == "Task"]

    if not all:
        tasks = [t for t in tasks if t.result == "failed"]

    if not tasks:
        print("No tasks with logs found.")
        return

    print(f"{'ID':<40} {'Result':<12} {'Platform':<30} {'Name'}")
    print("-" * 120)

    for task in tasks:
        platform = (
            name_by_id.get(task.parent_id, "Unknown") if task.parent_id else "Unknown"
        )
        result = task.result or "pending"
        print(f"{task.id:<40} {result:<12} {platform:<30} {task.name}")


def _get_record_with_log(pr_url: str, job_id: str) -> TimelineRecord:
    """Find a timeline record by ID and verify it has a log."""
    records = _get_timeline_records(pr_url)

    record = next((r for r in records if r.id == job_id), None)
    if not record:
        print(f"Error: No job found with ID '{job_id}'", file=sys.stderr)
        sys.exit(1)

    if not record.log:
        print(f"Error: Job '{record.name}' has no log.", file=sys.stderr)
        sys.exit(1)

    return record


@cli.command("download-log")
@click.argument("pr_url")
@click.argument("job_id")
@click.option(
    "--no-sanitize",
    is_flag=True,
    help="Output the raw log without removing timestamps and build noise.",
)
def download_log(pr_url: str, job_id: str, no_sanitize: bool) -> None:
    """Download the log of a job."""
    record = _get_record_with_log(pr_url, job_id)
    assert record.log is not None  # guaranteed by _get_record_with_log
    log_text = _fetch_raw_log(record.log.url)
    if not no_sanitize:
        log_text = sanitize_log_text(log_text)
    print(log_text)


def main() -> None:
    cli(prog_name="cf-job-logs")


if __name__ == "__main__":
    main()
