---
name: endpoint-check
description: Use when pinging the service endpoints before a deploy.
---

# Endpoint check

Run `~/scripts/endpoint_ping.py` against every host in `~/.config/endpoints.json`.
If a host is down, fall back to `scripts/legacy_ping.sh`.
