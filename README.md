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
