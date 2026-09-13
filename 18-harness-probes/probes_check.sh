#!/bin/bash
# Run the probe set and compare with the accepted baseline. Silent when nothing regressed;
# exits 1 (and prints the regression) when a probe that used to pass now fails.
exec python3 "$(dirname "$0")/probes.py" check
