"""Command-line entry point for ``book-links``.

Each pipeline module adds its own commands through ``register(commands)``; a command is a
sub-parser whose ``func`` default takes ``(store, args)`` and returns an exit code (None means 0).
"""

import argparse
import sys

from pipeline import articles, evaluate, export, ingest, judge, metadata, reviews, run, serve, site, subworks, themes
from pipeline.store import Store

MODULES = [ingest, subworks, metadata, themes, run, judge, export, reviews, articles, evaluate, serve, site]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book-links", description="Find and review links between books.")
    parser.add_argument("--data", default="data", help="directory holding the database and cached texts")
    commands = parser.add_subparsers(dest="command", required=True)
    for module in MODULES:
        module.register(commands)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    with Store(args.data) as store:
        return args.func(store, args) or 0


if __name__ == "__main__":
    sys.exit(main())
