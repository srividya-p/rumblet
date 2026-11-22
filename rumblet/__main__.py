"""Command-line entry point for python -m rumblet."""

import argparse
import sys
from pathlib import Path

from rumblet.engine import evaluate
from rumblet.errors import DynamicError, StaticError
from rumblet.sequence import print_sequence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rumblet")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="evaluate a query")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--expr", help="inline query expression")
    source.add_argument("--file", type=Path, help="UTF-8 file containing one query")
    args = parser.parse_args(argv)
    expression = args.expr
    if args.file is not None:
        try:
            with args.file.open(encoding="utf-8", newline="") as query_file:
                expression = query_file.read()
        except (OSError, UnicodeError) as error:
            print(f"[rumblet] cannot read query file {str(args.file)!r}: {error}", file=sys.stderr)
            return 2
    try:
        print_sequence(evaluate(expression))
    except (StaticError, DynamicError) as error:
        print(f"[rumblet] {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
