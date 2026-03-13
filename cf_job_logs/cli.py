# Copyright (c) QuantCo 2025
# SPDX-License-Identifier: BSD-3-Clause

import json
import logging
import sys
from typing import assert_never

import click
import httpx

from cf_job_logs.fetch_records import fetch_ci_records
from cf_job_logs.github_api import (
    fetch_github_check_runs,
    fetch_pr_details,
    get_github_headers,
    parse_pr_url,
)
from cf_job_logs.models import CIProvider, CIRecord, CIResult
from cf_job_logs.sanitize import sanitize_log_text

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 30.0


def _get_ci_records(pr_url: str) -> list[CIRecord]:
    """Fetch CI records for a GitHub PR."""
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        pr_info = parse_pr_url(pr_url)
        pr_details = fetch_pr_details(client, pr_info)
        head_sha = pr_details.head.sha
        check_runs = fetch_github_check_runs(client, pr_info, head_sha)
        return fetch_ci_records(client, check_runs, pr_info)


def _fetch_raw_log(record: CIRecord) -> str:
    """Fetch raw log content for a provider-specific CI record."""

    if not record.log:
        raise ValueError(f"Record '{record.name}' has no log information.")

    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        match record.ci_provider:
            case CIProvider.AZURE:
                resp = client.get(record.log.url, headers={"Accept": "text/plain"})
            case CIProvider.GITHUB_ACTIONS:
                resp = client.get(
                    record.log.url, headers=get_github_headers(), follow_redirects=True
                )
            case _ as unreachable:
                assert_never(unreachable)

        resp.raise_for_status()
        return resp.text


@click.group(invoke_without_command=True)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Fetch and inspect conda-forge CI logs."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(message)s",
    )

    # Show help if no subcommand is provided
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command("list-jobs")
@click.argument("pr_url")
@click.option(
    "--all",
    is_flag=True,
    help="List all jobs, not just failed ones.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output in JSON format.",
)
def list_jobs(pr_url: str, all: bool, output_json: bool) -> None:
    """List all jobs for a PR."""
    records = _get_ci_records(pr_url)
    name_by_id = {r.id: r.name for r in records}
    tasks = [r for r in records if r.log and r.type == "Task"]

    if not all:
        tasks = [t for t in tasks if t.result == CIResult.FAILED]

    if not tasks:
        if output_json:
            print(json.dumps([]))
        else:
            print("No tasks with logs found.")
        return

    output = []
    for task in tasks:
        platform = (
            name_by_id.get(task.parent_id, "Unknown") if task.parent_id else "Unknown"
        )
        result = task.result or "pending"
        output.append(
            {
                "id": task.id,
                "result": result,
                "platform": platform,
                "name": task.name,
            }
        )

    if output_json:
        print(json.dumps(output, indent=2))
    else:
        print(f"{'ID':<40} {'Result':<12} {'Platform':<30} {'Name'}")
        print("-" * 120)
        for entry in output:
            print(
                f"{entry['id']:<40} {entry['result']:<12} {entry['platform']:<30} {entry['name']}"
            )


def _get_record_with_log(pr_url: str, job_id: str) -> CIRecord:
    """Find a CI record by ID and verify it has a log."""
    records = _get_ci_records(pr_url)

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
    log_text = _fetch_raw_log(record)
    if not no_sanitize:
        log_text = sanitize_log_text(log_text)
    print(log_text)


if __name__ == "__main__":
    cli()
