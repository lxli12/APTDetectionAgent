#!/usr/bin/env python3
"""Run only the Agent-visible half of the Phase 9 synthetic scenario.

Requirements: REQ-CAUSAL-001..004, REQ-LABEL-001..004,
REQ-MEMORY-001..007, REQ-CONFIG-001..003, REQ-REPRO-001..002.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from apt_detection_agent.experiment import SyntheticScenarioConfig, SyntheticScenarioRunner


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    config = SyntheticScenarioConfig(
        run_id=args.run_id,
        run_root=args.run_root,
        project_root=args.project_root,
    )
    run_dir = SyntheticScenarioRunner(config).run()
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
