"""Build the static, read-only copy of the viewer that is hosted on GitHub Pages."""

import json
import os
import shutil
import sys
from pathlib import Path

from pipeline.export import build_graph

DIST = Path(__file__).resolve().parent.parent / "viewer" / "dist"


PUBLIC_SOURCE = "gutenberg-us"  # texts from elsewhere may be in copyright in the US, where Pages is hosted


def public_graph(store):
    """The exported graph without rejected links, review notes, or quotes from texts that may be in
    copyright in the United States."""
    graph = build_graph(store)
    quotable = {work["id"] for work in graph["works"] if work["source"] == PUBLIC_SOURCE}
    links = []
    for link in graph["links"]:
        if link["status"] == "rejected":
            continue
        link.pop("note", None)
        for item in link["evidence"]:
            for side in ("source", "target"):
                if link[side] not in quotable:
                    item[f"{side}_quote"] = None
        links.append(link)
    graph["links"] = links
    graph["reviewable"] = False
    return graph


def build_site(store, args):
    dist = Path(os.environ.get("BOOK_LINKS_VIEWER_DIST", DIST))
    if not (dist / "index.html").is_file():
        print(f"viewer not built ({dist}): run `npm run build` in viewer/ first", file=sys.stderr)
        return 1
    graph = public_graph(store)
    out = Path(args.out)
    shutil.copytree(dist, out, dirs_exist_ok=True)
    (out / "graph.json").write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}/ ({len(graph['works'])} works, {len(graph['links'])} links)")


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("build-site", help="write the read-only viewer and graph for GitHub Pages")
    parser.add_argument("--out", default="site", help="directory to write (default: site)")
    parser.set_defaults(func=build_site)
