"""Run the detectors and save what they propose."""

import hashlib
import json
from dataclasses import replace

from pipeline.detectors import DETECTORS
from pipeline.detectors.base import QUOTE_LIMIT, Corpus, Passage, SignatureTerm, ThemeLabel, Work
from pipeline.subworks import subwork_at, subwork_ranges

EVIDENCE_PER_LINK = 5


def load_corpus(store) -> Corpus:
    works = []
    for row in store.works():
        if row["kind"] == "subwork":
            passages = ()
        else:
            passages = tuple(Passage(p["id"], p["position"], p["text"]) for p in store.passages(row["id"]))
        text_year = row["text_year"] if row["text_year"] is not None else row["year"]
        works.append(
            Work(
                row["id"],
                row["title"],
                row["author"],
                row["year"],
                row["kind"],
                bool(row["translated"]),
                text_year,
                passages,
                row["parent_id"],
                (row["start_pos"], row["end_pos"]) if row["kind"] == "subwork" else None,
            )
        )
    terms = tuple(
        SignatureTerm(row["term"], row["work_id"], row["weight"])
        for row in store.conn.execute("SELECT term, work_id, weight FROM signature_terms")
    )
    themes = tuple(
        ThemeLabel(row["work_id"], row["theme"], row["note"])
        for row in store.conn.execute(
            "SELECT work_id, coalesce(canonical, theme) AS theme, note FROM themes ORDER BY id"
        )
    )
    return Corpus(tuple(works), terms, themes)


def evidence_key(store, source_id, target_id, link_type, evidence) -> str:
    """Identifies a candidate by the works, type and quotes shown to the judge."""
    source, target = store.work(source_id), store.work(target_id)
    quotes = sorted((e.source_quote or "", e.target_quote or "") for e in evidence)
    payload = [source["title"], source["author"], target["title"], target["author"], link_type, quotes]
    return hashlib.sha1(json.dumps(payload).encode("utf-8")).hexdigest()


class Subworks:
    """Moves the sides of a link onto subworks of the collections they point into."""

    def __init__(self, store):
        self.ranges = subwork_ranges(store)
        self.positions = dict(store.conn.execute("SELECT id, position FROM passages"))

    def of_passage(self, work_id, passage_id):
        """The subwork holding one passage, or ``work_id`` when no declared subwork does."""
        if passage_id is None:
            return work_id
        found = subwork_at(self.ranges, work_id, self.positions[passage_id])
        return work_id if found is None else found

    def resolve(self, work_id, passage_ids):
        """The one subwork holding all these passages, or ``work_id`` when they are spread or outside."""
        ids = [p for p in passage_ids if p is not None]
        if not ids or work_id not in self.ranges:
            return work_id
        containing = {subwork_at(self.ranges, work_id, self.positions[passage_id]) for passage_id in ids}
        only = containing.pop() if len(containing) == 1 else None
        return only if only is not None else work_id

    def split(self, candidate):
        """``(source id, target id, evidence)`` for each place a candidate's evidence belongs.

        Quotations are split evidence item by evidence item. Every other type moves as a whole, because
        its evidence is statistical across the whole work.
        """
        if candidate.type != "quotation":
            evidence = candidate.evidence[:EVIDENCE_PER_LINK]
            return [
                (
                    self.resolve(candidate.source_id, [e.source_passage_id for e in evidence]),
                    self.resolve(candidate.target_id, [e.target_passage_id for e in evidence]),
                    evidence,
                )
            ]
        groups = {}
        for item in candidate.evidence:
            key = (
                self.of_passage(candidate.source_id, item.source_passage_id),
                self.of_passage(candidate.target_id, item.target_passage_id),
            )
            groups.setdefault(key, []).append(item)
        return [(source, target, items[:EVIDENCE_PER_LINK]) for (source, target), items in groups.items()]


def allowed(store, source_id, target_id) -> bool:
    """A link needs two different works with known years, the source not earlier than the target."""
    if source_id == target_id:
        return False
    source, target = store.work(source_id), store.work(target_id)
    if source["year"] is None or target["year"] is None:
        return False
    return source["year"] >= target["year"]


def detect(store, args=None):
    corpus = load_corpus(store)
    subworks = Subworks(store)
    best = {}
    for detector in DETECTORS:
        for candidate in detector.detect(corpus):
            places = subworks.split(candidate)
            for source_id, target_id, evidence in places:
                if not allowed(store, source_id, target_id):
                    continue
                for item in evidence:
                    item.source_quote = item.source_quote[:QUOTE_LIMIT] if item.source_quote else None
                    item.target_quote = item.target_quote[:QUOTE_LIMIT] if item.target_quote else None
                if len(places) == 1 and (source_id, target_id) != (candidate.source_id, candidate.target_id):
                    store.conn.execute(
                        "UPDATE OR IGNORE reviews SET source_id = ?, target_id = ?"
                        " WHERE source_id = ? AND target_id = ? AND type = ?",
                        (source_id, target_id, candidate.source_id, candidate.target_id, candidate.type),
                    )
                key = (source_id, target_id, candidate.type)
                if key not in best or candidate.score > best[key][1].score:
                    best[key] = (
                        detector,
                        replace(candidate, source_id=source_id, target_id=target_id, evidence=evidence),
                    )

    ran = [detector.name for detector in DETECTORS]
    existing = {
        (row["source_id"], row["target_id"], row["type"]): row for row in store.conn.execute("SELECT * FROM links")
    }
    for key, row in existing.items():
        if row["detector"] in ran and key not in best and row["article_id"] is None:
            store.conn.execute("DELETE FROM links WHERE id = ?", (row["id"],))

    for key, (detector, candidate) in best.items():
        source_id, target_id, link_type = key
        row = existing.get(key)
        if row is not None and row["detector"] not in ran:
            continue  # a link from an article or another route already covers this pair and type
        ekey = evidence_key(store, source_id, target_id, link_type, candidate.evidence)
        score = max(0.0, min(1.0, candidate.score))
        if row is None:
            link_id = store.conn.execute(
                "INSERT INTO links (source_id, target_id, type, detector, detector_version, score, rationale, evidence_key)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (source_id, target_id, link_type, detector.name, detector.version, score, candidate.rationale, ekey),
            ).lastrowid
        else:
            link_id = row["id"]
            store.conn.execute(
                "UPDATE links SET detector = ?, detector_version = ?, score = ?, rationale = ?, evidence_key = ? WHERE id = ?",
                (detector.name, detector.version, score, candidate.rationale, ekey, link_id),
            )
            store.conn.execute(
                "DELETE FROM evidence WHERE link_id = ?"
                " AND (source_passage_id IS NOT NULL OR target_passage_id IS NOT NULL)",
                (link_id,),
            )
        store.conn.executemany(
            "INSERT INTO evidence (link_id, source_passage_id, target_passage_id, source_quote, target_quote)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (link_id, e.source_passage_id, e.target_passage_id, e.source_quote, e.target_quote)
                for e in candidate.evidence
            ],
        )
    print(f"{len(best)} candidate links from {len(ran)} detectors")


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("detect", help="run every detector and save the candidate links")
    parser.set_defaults(func=detect)
