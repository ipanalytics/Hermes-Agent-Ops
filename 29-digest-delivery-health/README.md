# 29 — digest-delivery-health

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python](https://img.shields.io/badge/python-3.10+-blue)

The script analyzes digest delivery health by comparing actual cron job executions with expected schedules, providing coverage reports for daily digest deliveries.

## Overview

I run as a cron job to monitor digest delivery health over the past 7 days. I analyze the execution history from audit logs and compare actual runs with expected schedule patterns, generating reports about coverage, silence periods, and errors for various digest types.

## How it works

I read execution history from a JSONL audit log file and match actual runs to expected schedule patterns for different digest types. I calculate coverage ratios, detect errors and silent responses, and track performance metrics like maximum execution time. I compare current week's data with previous week to identify trends.

## Quick start

```bash
# Set required environment variables
export HERMES_AUDIT_LOG=~/.hermes/cron/usage_audit.jsonl
export HERMES_JOBS_FILE=~/.hermes/cron/jobs.json
export HERMES_DIGEST_HEALTH_STATE=~/.hermes/data/digest_health_state.json

# Run the script
python3 digest_health.py
```

## Usage

The script accepts no command-line arguments. It uses environment variables to locate configuration files:

- `HERMES_AUDIT_LOG`: Path to the audit log file (default: `~/.hermes/cron/usage_audit.jsonl`)
- `HERMES_JOBS_FILE`: Path to the jobs configuration (default: `~/.hermes/cron/jobs.json`)
- `HERMES_DIGEST_HEALTH_STATE`: Path to the state file (default: `~/.hermes/data/digest_health_state.json`)

## Outputs

I output a formatted report showing:
- Coverage statistics for each digest type (actual/expected runs)
- Error counts and silent response counts
- Performance indicators (slowest execution times)
- Trend indicators (comparing to previous week)
- Visual status indicators (red/yellow/green)

## Limitations

- Requires properly formatted audit logs in JSONL format
- Timezone-sensitive (uses UTC for calculations)
- Depends on consistent job IDs in the configuration
- Historical analysis limited to 7-day windows

## Structure

- `digest_health.py` - Main script for digest delivery health monitoring
- `README.md` - English documentation
- `README.ru.md` - Russian documentation
- `tests/test_digest_health.py` - Unit tests
- `examples/` - Sample input data files

## License

MIT License - see the LICENSE file in the repository for details.