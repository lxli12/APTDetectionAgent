"""Command-line entry point for finite checkpoint preparation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pidsmaker_adapter.configuration import DEFAULT_SPACE, load_configuration_space

DEFAULT_OUTPUT_ROOT = Path("/root/autodl-tmp/apt-detection-agent/pidsmaker-output")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pidsmaker_adapter.main")
    parser.add_argument(
        "--configuration-space",
        type=Path,
        default=DEFAULT_SPACE,
        help="Versioned finite configuration-space YAML",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-configs")
    list_parser.add_argument("--plain", action="store_true")

    prepare = subparsers.add_parser("prepare")
    selection = prepare.add_mutually_exclusive_group(required=True)
    selection.add_argument("--config", action="append", dest="config_ids")
    selection.add_argument("--all", action="store_true")
    prepare.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    prepare.add_argument("--database-host", default=os.environ.get("PIDS_DB_HOST", "localhost"))
    prepare.add_argument("--database-port", default=os.environ.get("PIDS_DB_PORT", "5432"))
    prepare.add_argument("--database-user", default=os.environ.get("PIDS_DB_USER", "postgres"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    space = load_configuration_space(args.configuration_space)
    if args.command == "list-configs":
        if args.plain:
            for item in space.configurations:
                print(item.config_id)
        else:
            for item in space.configurations:
                print(f"{item.config_id}\t{item.pids}\t{item.scoring}")
        return 0

    password = os.environ.get("PIDS_DB_PASSWORD")
    if password is None:
        raise SystemExit("PIDS_DB_PASSWORD must be supplied through the environment")
    database = {
        "host": args.database_host,
        "port": str(args.database_port),
        "user": args.database_user,
        "password": password,
    }
    selected = (
        list(space.configurations)
        if args.all
        else [space.get(config_id) for config_id in args.config_ids]
    )
    from pidsmaker_adapter.pipeline import prepare_checkpoint

    for legal in selected:
        path = prepare_checkpoint(
            legal=legal,
            space=space,
            output_root=args.output_root,
            database=database,
        )
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
