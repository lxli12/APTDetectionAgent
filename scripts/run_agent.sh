#!/usr/bin/env bash
set -euo pipefail

python -m apt_detection_agent.experiment.experiment_runner "$@"
