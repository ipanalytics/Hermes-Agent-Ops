# 31 — Compaction Effect Check

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

This module checks the effect of changing context compaction policies in Hermes Agent. It collects baseline metrics before a policy change, then compares usage patterns after the change period to determine if the new policy improves or worsens resource consumption.

## Overview

I run this module to evaluate context compaction policy changes in Hermes Agent. The module establishes a baseline during a pre-change period, then measures changes in daily costs, compression ratios, and cache efficiency after implementing a new compaction policy. I analyze metrics like daily cost, compaction model usage, and cache-to-input token ratios to provide a clear verdict on policy effectiveness.

## How it works

I collect usage data from the Hermes database before and after a compaction policy change. My process involves:

1. Establishing baseline metrics over a configurable period before the change
2. Recording the exact timestamp of the policy change
3. Measuring the same metrics after the change over an observation period
4. Comparing daily costs, compaction usage, and cache efficiency
5. Providing a clear verdict on whether the change improved or worsened performance

I store my intermediate state in a JSON file to track the experiment progress and avoid duplicate reporting.

## Quick start

```bash
# Set environment variables for your experiment
export CHANGE_TIMESTAMP=$(date +%s)  # Timestamp of policy change
export COMPACT_MODEL_NAME="glm-5.3-flash"
export BASELINE_DAYS=3
export OBSERVE_DAYS=3

# Run the check
python3 compaction_effect_check.py
```

## Usage

The module accepts configuration through environment variables:

- `HERMES_DB_PATH`: Path to the Hermes database (default: `~/.hermes/state.db`)
- `COMPACT_STATE_FILE`: State file path (default: `~/.hermes/data/compaction_experiment.json`)
- `BASELINE_DAYS`: Days to collect baseline data (default: 3)
- `OBSERVE_DAYS`: Days to observe after change (default: 3)
- `COMPACT_MODEL_NAME`: Model name for compaction tracking (default: `glm-5.3-flash`)
- `CHANGE_TIMESTAMP`: Unix timestamp of the policy change

Run the script repeatedly during the experiment. It will remain silent until the observation period completes, then print results once.

## Outputs

My output includes:

- Daily cost comparison (before vs after)
- Compaction model cost comparison
- Number of compaction calls
- Cache-to-input token ratio
- Clear verdict on whether the change was beneficial

## Limitations

I require access to the Hermes database with usage statistics. My effectiveness depends on having sufficient baseline and observation periods to establish reliable metrics. I only track models identified by the compaction model name pattern. The experiment assumes a single policy change during the observation window.

## Structure

```
├── compaction_effect_check.py  # Main script
├── README.md                   # English documentation
├── README.ru.md                # Russian documentation
├── tests/
│   └── test_compaction_effect_check.py
└── examples/
    ├── sample_config.env       # Example environment variables
    └── experiment_state.json   # Example state file
```

## License

MIT License - see the LICENSE file in the repository for details.