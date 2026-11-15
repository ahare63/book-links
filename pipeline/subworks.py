"""Poems declared inside a collection become their own works."""

import sys

import yaml

from pipeline.ingest import stripped_text


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("add-subworks", help="declare subworks from a YAML file")
    parser.add_argument("file", nargs="?", default="works/subworks.yaml")
    parser.set_defaults(func=add_subworks)


def add_subworks(store, args):
    try:
        with open(args.file, encoding="utf-8") as handle:
            entries = yaml.safe_load(handle) or []
    except OSError as error:
        return _fail(f"cannot read {args.file}: {error.strerror}")

    planned = []
    for entry in entries:
        found = _locate(store, entry)
        if isinstance(found, str):
            return _fail(found)
        planned.append(found)
    for parent, entry, start, end in planned:
        store.add_work(
            entry["title"],
            entry.get("author", parent["author"]),
            entry.get("year", parent["year"]),
            parent["source"],
            "subwork",
            source_ref=parent["source_ref"],
            parent_id=parent["id"],
            start_pos=start,
            end_pos=end,
            text_year=parent["text_year"],
        )


def _locate(store, entry):
    """(parent row, entry, start, end) for a declaration, or a message saying what is missing."""
    name = str(entry["parent"])
    parent = store.find_work(name) or next((w for w in store.works() if w["source_ref"] == name), None)
    if parent is None:
        return f"{entry['title']}: no parent work {name!r}"
    text = stripped_text(store, parent["id"])
    if text is None:
        return f"{entry['title']}: parent {name!r} has no text"

    lines, offset = [], 0
    for line in text.split("\n"):
        lines.append((offset, " ".join(line.split())))
        offset += len(line) + 1
    first, last = " ".join(entry["first_line"].split()), " ".join(entry["last_line"].split())
    first_at = next((i for i, (_, line) in enumerate(lines) if first in line), None)
    if first_at is None:
        return f"{entry['title']}: first line {entry['first_line']!r} not found in {name!r}"
    last_at = next((i for i in range(first_at + 1, len(lines)) if last in lines[i][1]), None)
    if last_at is None:
        return f"{entry['title']}: last line {entry['last_line']!r} not found after the first line in {name!r}"

    start = lines[first_at][0]
    end = lines[last_at][0] + len(text[lines[last_at][0]:].split("\n", 1)[0])
    return parent, entry, start, end


def _fail(message):
    print(f"error: {message}", file=sys.stderr)
    return 1
