# cf-job-logs

[![CI](https://img.shields.io/github/actions/workflow/status/ManuelLerchnerQC/cf-job-logs/ci.yml?style=flat-square&branch=main)](https://github.com/ManuelLerchnerQC/cf-job-logs/actions/workflows/ci.yml)
[![conda-forge](https://img.shields.io/conda/vn/conda-forge/cf-job-logs?logoColor=white&logo=conda-forge&style=flat-square)](https://prefix.dev/channels/conda-forge/packages/cf-job-logs)
[![pypi-version](https://img.shields.io/pypi/v/cf-job-logs.svg?logo=pypi&logoColor=white&style=flat-square)](https://pypi.org/project/cf-job-logs)
[![python-version](https://img.shields.io/pypi/pyversions/cf-job-logs?logoColor=white&logo=python&style=flat-square)](https://pypi.org/project/cf-job-logs)

A utility for fetching and structuring conda-forge Azure CI logs into clean, agent-readable artifacts.

## Installation

This project is managed by [pixi](https://pixi.sh).
You can install the package in development mode using:

```bash
git clone https://github.com/ManuelLerchnerQC/cf-job-logs
cd cf-job-logs

pixi run pre-commit-install
pixi run postinstall
pixi run test
```

## CLI Usage

The `cf-job-logs` CLI provides commands to inspect Azure CI jobs for a conda-forge PR.

### List jobs

List failed jobs (default) for a PR:

```bash
cf-job-logs list-jobs https://github.com/conda-forge/some-feedstock/pull/123
```

List all jobs (including succeeded):

```bash
cf-job-logs list-jobs --all https://github.com/conda-forge/some-feedstock/pull/123
```

### Download a job log

Use a job ID from the `list-jobs` output to download its full (raw) log:

```bash
cf-job-logs download-log https://github.com/conda-forge/some-feedstock/pull/123 <job_id>
```

Or download the sanitized log (timestamps and build noise removed):

```bash
cf-job-logs download-sanitized-log https://github.com/conda-forge/some-feedstock/pull/123 <job_id>
```

Output goes to stdout, so you can redirect it to a file:

```bash
cf-job-logs download-sanitized-log <pr_url> <job_id> > build.log
```

### Verbose mode

Add `-v` for debug logging:

```bash
cf-job-logs -v list-jobs https://github.com/conda-forge/some-feedstock/pull/123
```

### Running via pixi

All commands can also be run through pixi:

```bash
pixi run cf-job-logs list-jobs <pr_url>
```
