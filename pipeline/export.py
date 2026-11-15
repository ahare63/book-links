"""Build the graph the viewer reads: works, and links with status, confidence and short quotes."""

import json
from pathlib import Path

from pipeline.confidence import assess


def build_graph(store) -> dict:
    works = [
        {
            "id": row["id"],
            "title": row["title"],
            "author": row["author"],
            "year": row["year"],
            "year_approximate": bool(row["year_approximate"]),
            "kind": row["kind"],
            "source": row["source"],
            "parent": row["parent_id"],
            "translated": bool(row["translated"]),
        }
        for row in store.works()
    ]
    judgements = {row["evidence_key"]: row for row in store.conn.execute("SELECT * FROM judgements")}
    reviews = {
        (row["source_id"], row["target_id"], row["type"]): row
        for row in store.conn.execute("SELECT * FROM reviews")
    }
    citations = dict(store.conn.execute("SELECT id, citation FROM articles"))
    evidence = {}
    for row in store.conn.execute("SELECT link_id, source_quote, target_quote FROM evidence ORDER BY id"):
        evidence.setdefault(row["link_id"], []).append(
            {"source_quote": row["source_quote"], "target_quote": row["target_quote"]}
        )
    links = []
    for row in store.conn.execute("SELECT * FROM links ORDER BY id"):
        judgement = judgements.get(row["evidence_key"])
        review = reviews.get((row["source_id"], row["target_id"], row["type"]))
        confidence, status = assess(row["score"], judgement, review)
        links.append(
            {
                "id": row["id"],
                "source": row["source_id"],
                "target": row["target_id"],
                "type": (review["corrected_type"] if review and review["corrected_type"] else row["type"]),
                "confidence": round(confidence, 4),
                "status": status,
                "reviewed": review is not None,
                "note": review["note"] if review else None,
                "detector": row["detector"],
                "detector_version": row["detector_version"],
                "rationale": judgement["rationale"] if judgement and judgement["rationale"] else row["rationale"],
                "detector_rationale": row["rationale"],
                "article": citations.get(row["article_id"]),
                "evidence": evidence.get(row["id"], []),
            }
        )
    return {"works": works, "links": links}


def export(store, args):
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    graph = build_graph(store)
    out.write_text(json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(graph['works'])} works and {len(graph['links'])} links to {out}")


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("export", help="write the graph JSON the viewer reads")
    parser.add_argument("out", help="path of the JSON file to write")
    parser.set_defaults(func=export)
