# 27 — Ecosystem Map

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-production-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

This module generates a live map of the agent ecosystem, showing jobs, profiles, and connections. It monitors cron jobs and their states, creating a comprehensive overview of the agent's scheduled tasks.

## Overview

The ecosystem map script creates a real-time view of all scheduled tasks in the Hermes agent system. I run it as a no_agent-cron every Monday at 05:30 UTC to track the state of all jobs, profiles, and their delivery targets. The script produces both a full map and a change diff since the last run.

## How it works

I read job data from `~/.hermes/cron/jobs.json` and profile information from `~/.hermes/profiles/` to build a complete picture of the ecosystem. The script groups cron jobs by their delivery targets and categorizes them by state (active, paused, completed). It maintains a state file to detect changes between runs and only reports meaningful updates.

## Quick start

```bash
# Run the script directly
python3 ecosystem_map.py

# Or set up as a cron job
# 30 5 * * 1 python3 ecosystem_map.py
```

## Usage

The script automatically reads from the standard Hermes locations and creates:
- Full ecosystem map at `~/.hermes/data/ecosystem_map.md`
- State file at `~/.hermes/data/ecosystem_map_state.json` 
- Change report printed to stdout (when there are changes)

Set environment variables for custom chat IDs:
- HERMES_GROUP_CHAT - Group chat ID with topics
- HERMES_MYNET_CHAT - MyNET chat ID
- HERMES_OPERATOR_CHAT - Operator chat ID

## Outputs

- Markdown-formatted ecosystem map showing all jobs by delivery target
- Profile list with main profile marked
- Problem section highlighting failing jobs
- Change diff showing new/removed/resumed jobs
- State tracking for continuous monitoring

## Limitations

- Requires access to the Hermes cron job data structure
- Depends on specific file paths in the ~/.hermes directory
- Environment variables needed for custom chat configurations
- Only tracks scheduled and paused jobs, not completed one-offs in the change detection

## Structure

- `ecosystem_map.py` - Main script that builds the map and detects changes
- `README.md` - This file
- `README.ru.md` - Russian translation
- `tests/test_ecosystem_map.py` - Unit tests
- `examples/` - Sample input data

## License

MIT License - see the LICENSE file in the repository for details.