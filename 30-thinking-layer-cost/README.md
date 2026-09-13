# 30 — thinking-layer-cost

_Русская версия: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

The script generates a daily report about the "thinking layer" costs and spending ceiling. It calculates spending from a state database and fetches live balance information from API endpoints.

## Overview

I analyze the costs associated with the "thinking layer" of the agent ecosystem. This includes tracking expenses for advanced models like M3 and calculating daily spending limits to control costs. My report shows current usage, daily averages, and remaining balance information.

## How it works

I connect to a SQLite database containing session model usage data to calculate costs for the thinking layer models. I retrieve current balance information from API endpoints like OpenRouter and DeepSeek. Then I compile this data into a comprehensive daily report showing spending patterns and thresholds.

## Quick start

```bash
python3 thinking_layer_cost.py
```

Make sure your environment variables are set for API access:
- OPENROUTER_API_KEY
- DEEPSEEK_API_KEY

## Usage

Run the script directly to generate the daily report:

```bash
# Set environment variables first
export OPENROUTER_API_KEY="your_key_here"
export DEEPSEEK_API_KEY="your_key_here"

# Generate the report
python3 thinking_layer_cost.py
```

The script will output a formatted report with cost information, daily limits, and current status.

## Outputs

- Daily cost of the thinking layer models
- Total daily spending across all models
- Peak and average daily spending over the past week
- Current API service balances
- Estimated runway based on average spending
- Status indicator showing if spending exceeds thresholds

## Limitations

- Requires access to the state database (state.db) with session model usage data
- Needs valid API keys for balance checking services
- Depends on specific environment variable configuration
- Works only with UTC timezone for date calculations

## Structure

- `thinking_layer_cost.py`: Main script that analyzes costs and generates reports
- `tests/test_thinking_layer_cost.py`: Unit tests for the cost analysis functionality
- `examples/`: Sample data and configuration files
- `README.md`: Documentation in English
- `README.ru.md`: Documentation in Russian

## License

MIT License - see the LICENSE file in the repository for details.