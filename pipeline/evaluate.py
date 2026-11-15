"""Compare the links in the store with a gold list of known links."""

import json
from collections import defaultdict

import yaml


def resolve(store, ref, title):
    """The work whose source_ref is ``ref`` or, failing that, whose title is ``title``; else None."""
    row = store.conn.execute("SELECT * FROM works WHERE source_ref = ? ORDER BY id", (str(ref),)).fetchone()
    if row is None and title:
        row = store.conn.execute("SELECT * FROM works WHERE lower(title) = lower(?) ORDER BY id", (title,)).fetchone()
    return row


def with_subworks(store, work_id):
    rows = store.conn.execute("SELECT id FROM works WHERE parent_id = ?", (work_id,))
    return {work_id} | {row["id"] for row in rows}


def matching_detectors(store, source_ids, target_ids):
    """Detectors of the links between the two sides that no owner review rejected."""
    detectors = set()
    for link in store.conn.execute("SELECT * FROM links"):
        if link["source_id"] not in source_ids or link["target_id"] not in target_ids:
            continue
        review = store.conn.execute(
            "SELECT verdict FROM reviews WHERE source_id = ? AND target_id = ? AND type = ?",
            (link["source_id"], link["target_id"], link["type"]),
        ).fetchone()
        if review is None or review["verdict"] != "reject":
            detectors.add(link["detector"])
    return detectors


def evaluate_gold(store, entries) -> dict:
    total = found = skipped = 0
    missing = []
    by_detector = defaultdict(lambda: {"found": 0})
    for entry in entries:
        source = resolve(store, entry.get("source"), entry.get("source_title"))
        target = resolve(store, entry.get("target"), entry.get("target_title"))
        if source is None or target is None:
            skipped += 1
            continue
        total += 1
        detectors = matching_detectors(store, with_subworks(store, source["id"]), with_subworks(store, target["id"]))
        if detectors:
            found += 1
            for name in detectors:
                by_detector[name]["found"] += 1
        else:
            missing.append({
                "source_title": entry.get("source_title"),
                "target_title": entry.get("target_title"),
                "type": entry.get("type"),
            })
    return {"total": total, "found": found, "skipped": skipped, "missing": missing,
            "by_detector": dict(by_detector)}


def evaluate(store, args):
    with open(args.gold, encoding="utf-8") as handle:
        report = evaluate_gold(store, yaml.safe_load(handle) or [])
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
        return
    print(f"recall: {report['found']}/{report['total']} gold links found ({report['skipped']} skipped: works not in the corpus)")
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
