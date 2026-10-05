#!/usr/bin/env bash
# =============================================================================
# Kenvue SOP Assistant Launcher
# =============================================================================
set -e

# Change to the project directory containing this script
cd "$(dirname "$0")"

# Execute launcher script
python3 run.py "$@"
