"""Compare the links in the store with a gold list of known links."""

import json
from collections import defaultdict

import yaml

from pipeline.export import build_graph


def resolve(store, ref, title):
    """The work whose source_ref is ``ref`` or, failing that, whose title is ``title``; else None."""
    row = store.conn.execute("SELECT * FROM works WHERE source_ref = ? ORDER BY id", (str(ref),)).fetchone()
    if row is None and title:
        row = store.conn.execute("SELECT * FROM works WHERE lower(title) = lower(?) ORDER BY id", (title,)).fetchone()
    return row


def with_subworks(store, work_id):
    rows = store.conn.execute("SELECT id FROM works WHERE parent_id = ?", (work_id,))
    return {work_id} | {row["id"] for row in rows}


def side(store, ref, title, part=None):
    """Ids a gold entry's side may match: the work and its subworks, plus the named part if held
    separately (``target_part: Hamlet`` also matches a standalone Hamlet). Empty if none is held."""
    ids = set()
    for row in (resolve(store, ref, title), resolve(store, None, part) if part else None):
        if row is not None:
            ids |= with_subworks(store, row["id"])
    return ids


def evaluate_gold(store, entries) -> dict:
    # Only links that are not rejected, by the judge or by the owner, count as found.
    standing = [link for link in build_graph(store)["links"] if link["status"] != "rejected"]
    total = found = skipped = 0
    missing = []
    by_detector = defaultdict(lambda: {"found": 0})
    for entry in entries:
        sources = side(store, entry.get("source"), entry.get("source_title"))
        targets = side(store, entry.get("target"), entry.get("target_title"), entry.get("target_part"))
        if not sources or not targets:
            skipped += 1
            continue
        total += 1
        detectors = {link["detector"] for link in standing if link["source"] in sources and link["target"] in targets}
        if detectors:
            found += 1
            for name in detectors:
                by_detector[name]["found"] += 1
        else:
            missing.append(
                {
                    "source_title": entry.get("source_title"),
                    "target_title": entry.get("target_title"),
                    "type": entry.get("type"),
                }
            )
    return {"total": total, "found": found, "skipped": skipped, "missing": missing, "by_detector": dict(by_detector)}


def evaluate(store, args):
    with open(args.gold, encoding="utf-8") as handle:
        report = evaluate_gold(store, yaml.safe_load(handle) or [])
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
        return
    print(
        f"recall: {report['found']}/{report['total']} gold links found and not rejected ({report['skipped']} skipped: works not in the corpus)"
    )
    for name, counts in sorted(report["by_detector"].items()):
        print(f"  {name}: {counts['found']}")
    for entry in report["missing"]:
        print(f"missing: {entry['source_title']} -> {entry['target_title']} ({entry['type']})")


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("evaluate", help="report which gold-list links the store contains")
    parser.add_argument("gold", help="path to the gold YAML file")
    parser.add_argument("--json", action="store_true", help="print one JSON object instead of a report")
    parser.set_defaults(func=evaluate)
