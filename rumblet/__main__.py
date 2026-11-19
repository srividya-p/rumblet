"""Command-line entry point for python -m rumblet."""

import argparse
import sys

from rumblet.engine import evaluate
from rumblet.errors import DynamicError, StaticError
from rumblet.sequence import print_sequence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rumblet")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="evaluate a query")
    run.add_argument("--expr", required=True, help="query expression")
    args = parser.parse_args(argv)
    try:
        print_sequence(evaluate(args.expr))
    except (StaticError, DynamicError) as error:
        print(f"[rumblet] {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
