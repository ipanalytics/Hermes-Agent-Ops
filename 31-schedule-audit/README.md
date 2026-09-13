# 31 — Schedule Audit

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

Schedule audit identifies heavy cron jobs that can be moved to night hours to reduce costs and optimize resource usage. It analyzes token consumption patterns and identifies tasks that are not time-critical and can be rescheduled for off-peak hours.

## Overview

I run an audit of scheduled tasks to identify which ones consume significant computational resources but are not time-sensitive. I analyze token usage patterns and identify candidates for moving to night hours when processing costs are lower and system load is reduced.

## How it works

I examine the jobs.json file containing scheduled tasks and cross-reference it with usage_audit.jsonl which contains token consumption data. I categorize tasks based on their average token consumption and time sensitivity. Heavy tasks that are not time-critical are identified as candidates for rescheduling during night hours.

The script distinguishes between time-critical tasks (like morning routines or time-dependent operations) and flexible tasks (like audits, research, translations) that can be moved without impact.

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the audit without making changes
python schedule_audit.py

# Apply suggested changes to reschedule tasks
python schedule_audit.py --apply
```

## Usage

The script requires two input files:
- `jobs.json`: Contains the scheduled tasks configuration
- `usage_audit.jsonl`: Contains token consumption data in JSONL format

I analyze token usage per job and identify those consuming more than 200,000 tokens on average as heavy tasks. Tasks consuming more than 100,000 tokens that are marked as flexible and not time-critical are candidates for rescheduling to night hours.

When applying changes, I create backups of the original jobs.json file before making modifications.

## Outputs

- List of heavy cron jobs with their average token consumption
- List of tasks that can be moved to night hours
- Backup of original jobs.json before applying changes
- Rollback file with information about changes made

## Limitations

- Requires both jobs.json and usage_audit.jsonl files to be present
- Time-critical tasks are determined by regex patterns that may need adjustment
- Night hours are hardcoded as 0-5 UTC

## Structure

- `schedule_audit.py`: Main script for analyzing and rescheduling tasks
- `requirements.txt`: Dependencies
- `tests/`: Unit tests
- `examples/`: Sample input data

## License

MIT