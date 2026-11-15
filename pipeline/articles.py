"""Ingest an article: ask the model which links and signature terms it claims, and store them."""

import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from pipeline.detectors.base import LINK_TYPES, QUOTE_LIMIT, Evidence
from pipeline.model import ModelError, ask_json
from pipeline.run import allowed, evidence_key
from pipeline.sources.http import FetchError, fetch

ARTICLE_SCORE = 0.8

PROMPT = """\
Below is an article about books, followed by the list of works in a reference corpus.
Extract the claims the article itself makes about links between works in that list.

A link runs from a later work (source) to the earlier work it draws on (target). Use only works
from the list, written exactly as listed, and only claims the article actually makes; do not add
links from your own knowledge. Link types: {types}.

Also extract signature terms: single distinctive words or short phrases that the article says are
characteristic of one of the listed works, so that another book using the term is probably
drawing on that work. Give each a weight from 0 to 1 for how strongly the article ties it to the work.

Works in the corpus:
{works}

Article:
{article}

Reply with one JSON object and nothing else:
{{"links": [{{"source": "title of the later work", "target": "title of the earlier work it draws on", "type": "one of: {types}", "quote": "a short quotation from the article that supports the claim", "rationale": "one or two sentences"}}], "signature_terms": [{{"work": "title of the work", "term": "a single distinctive word or short phrase", "weight": a number from 0 to 1}}]}}
Use empty lists if the article makes no such claims.
"""


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        else:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def strip_html(content: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(content)
    lines = (" ".join(line.split()) for line in "".join(extractor.parts).splitlines())
    return "\n".join(line for line in lines if line)


def read_article(location: str) -> tuple[str, str]:
    """The article's text and the name to cite it by (file name or URL)."""
    if urlparse(location).scheme in ("http", "https"):
        text = fetch(location).decode("utf-8", errors="replace")
        name = location
    else:
        text = Path(location).read_text(encoding="utf-8", errors="replace")
        name = Path(location).name
    if "<" in text and ("</" in text or "<html" in text.lower()) and text.lstrip().startswith("<"):
        text = strip_html(text)
    return text, name


def build_prompt(text, works) -> str:
    listing = "\n".join(
        f"- {w['title']} | {w['author']} | {w['year'] if w['year'] is not None else 'year unknown'}" for w in works
    )
    return PROMPT.format(types=", ".join(LINK_TYPES), works=listing, article=text)


def add_article(store, args):
    location = str(args.location)
    if store.conn.execute("SELECT 1 FROM articles WHERE location = ?", (location,)).fetchone():
        return 0
    try:
        text, name = read_article(location)
    except (OSError, FetchError) as error:
        print(f"add-article: {error}", file=sys.stderr)
        return 1
    works = [w for w in store.works() if w["kind"] != "subwork"]
    try:
        reply = ask_json(build_prompt(text, works), "links")
    except ModelError as error:
        print(f"add-article: {error}", file=sys.stderr)
        return 1

    by_title = {w["title"].lower(): w["id"] for w in works}
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), name)
    article_id = store.conn.execute(
        "INSERT INTO articles (citation, location, added) VALUES (?, ?, ?)",
        (f"{first_line} ({name})", location, date.today().isoformat()),
    ).lastrowid

    added = skipped = 0
    unknown = []
    for claim in reply.get("links") or []:
        if not isinstance(claim, dict):
            continue
        source_id = by_title.get(str(claim.get("source", "")).lower())
        target_id = by_title.get(str(claim.get("target", "")).lower())
        if source_id is None or target_id is None:
            unknown.append(f"{claim.get('source')} -> {claim.get('target')}")
            continue
        link_type = claim.get("type")
        if link_type not in LINK_TYPES or not allowed(store, source_id, target_id):
            skipped += 1
            continue
        evidence = [Evidence(source_quote=str(claim.get("quote", ""))[:QUOTE_LIMIT] or None)]
        existing = store.conn.execute(
            "SELECT id FROM links WHERE source_id = ? AND target_id = ? AND type = ?",
            (source_id, target_id, link_type),
        ).fetchone()
        if existing is not None:
            # A detector found it too: cite the article on that link and keep its quote as evidence.
            store.conn.execute("UPDATE links SET article_id = ? WHERE id = ?", (article_id, existing["id"]))
            store.conn.execute(
                "INSERT INTO evidence (link_id, source_quote, target_quote) VALUES (?, ?, NULL)",
                (existing["id"], evidence[0].source_quote),
            )
            added += 1
            continue
        link_id = store.conn.execute(
            "INSERT INTO links (source_id, target_id, type, detector, detector_version, score, rationale,"
            " evidence_key, article_id) VALUES (?, ?, ?, 'article', '1', ?, ?, ?, ?)",
            (
                source_id,
                target_id,
                link_type,
                ARTICLE_SCORE,
                str(claim.get("rationale", "")),
                evidence_key(store, source_id, target_id, link_type, evidence),
                article_id,
            ),
        ).lastrowid
        store.conn.execute(
            "INSERT INTO evidence (link_id, source_quote, target_quote) VALUES (?, ?, NULL)",
            (link_id, evidence[0].source_quote),
        )
        added += 1

    terms = 0
    for item in reply.get("signature_terms") or []:
        if not isinstance(item, dict):
            continue
        work_id = by_title.get(str(item.get("work", "")).lower())
        term = str(item.get("term", "")).strip().lower()
        try:
            weight = max(0.0, min(1.0, float(item.get("weight", 0.5))))
        except (TypeError, ValueError):
            continue
        if work_id is None or not term:
            if work_id is None:
                unknown.append(str(item.get("work")))
            continue
        store.conn.execute(
            "INSERT INTO signature_terms (term, work_id, weight, article_id) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (term, work_id) DO UPDATE SET weight = excluded.weight, article_id = excluded.article_id",
            (term, work_id, weight, article_id),
        )
        terms += 1

    if unknown:
        print("add-article: not in the corpus, skipped: " + "; ".join(sorted(set(unknown))), file=sys.stderr)
    print(
        f"added {added} links and {terms} signature terms from {name}"
        + (f" ({skipped} claims skipped: unknown type or impossible direction)" if skipped else "")
    )
    return 0


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("add-article", help="ingest an article (file path or URL) and its claimed links")
    parser.add_argument("location", help="a file path or an http(s) URL")
    parser.set_defaults(func=add_article)
