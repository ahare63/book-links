"""Run the detectors and save what they propose."""

import hashlib
import json
from collections import defaultdict

from pipeline.detectors import DETECTORS
from pipeline.detectors.base import QUOTE_LIMIT, Corpus, Passage, SignatureTerm, Work

EVIDENCE_PER_LINK = 5


def load_corpus(store) -> Corpus:
    works = []
    for row in store.works():
        if row["kind"] == "subwork":
            continue
        passages = tuple(Passage(p["id"], p["position"], p["text"]) for p in store.passages(row["id"]))
        works.append(Work(row["id"], row["title"], row["author"], row["year"], row["kind"],
                          bool(row["translated"]), passages))
    terms = tuple(
        SignatureTerm(row["term"], row["work_id"], row["weight"])
        for row in store.conn.execute("SELECT term, work_id, weight FROM signature_terms")
    )
    return Corpus(tuple(works), terms)


def evidence_key(store, source_id, target_id, link_type, evidence) -> str:
    """Identifies a candidate by the works, type and quotes shown to the judge."""
    source, target = store.work(source_id), store.work(target_id)
    quotes = sorted((e.source_quote or "", e.target_quote or "") for e in evidence)
    payload = [source["title"], source["author"], target["title"], target["author"], link_type, quotes]
    return hashlib.sha1(json.dumps(payload).encode("utf-8")).hexdigest()


class Subworks:
    """Moves one side of a link onto a subwork when all its evidence lies inside that subwork."""

    def __init__(self, store):
        self.ranges = defaultdict(list)
        for row in store.conn.execute("SELECT id, parent_id, start_pos, end_pos FROM works WHERE kind = 'subwork'"):
            self.ranges[row["parent_id"]].append((row["start_pos"], row["end_pos"], row["id"]))
        self.positions = dict(store.conn.execute("SELECT id, position FROM passages"))

    def resolve(self, work_id, passage_ids):
        ids = [p for p in passage_ids if p is not None]
        if not ids or work_id not in self.ranges:
            return work_id
        containing = set()
        for passage_id in ids:
            position = self.positions[passage_id]
            inside = [sub for start, end, sub in self.ranges[work_id] if start <= position < end]
            containing.add(inside[0] if inside else None)
        only = containing.pop() if len(containing) == 1 else None
        return only if only is not None else work_id


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
            evidence = candidate.evidence[:EVIDENCE_PER_LINK]
            for item in evidence:
                item.source_quote = item.source_quote[:QUOTE_LIMIT] if item.source_quote else None
                item.target_quote = item.target_quote[:QUOTE_LIMIT] if item.target_quote else None
            source_id = subworks.resolve(candidate.source_id, [e.source_passage_id for e in evidence])
            target_id = subworks.resolve(candidate.target_id, [e.target_passage_id for e in evidence])
            if not allowed(store, source_id, target_id):
                continue
            key = (source_id, target_id, candidate.type)
            if key not in best or candidate.score > best[key][1].score:
                candidate.evidence = evidence
                best[key] = (detector, candidate)

    ran = [detector.name for detector in DETECTORS]
    marks = ",".join("?" for _ in ran)
    existing = {
        (row["source_id"], row["target_id"], row["type"]): row
        for row in store.conn.execute("SELECT * FROM links")
    }
    for key, row in existing.items():
        if row["detector"] in ran and key not in best:
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
            store.conn.execute("DELETE FROM evidence WHERE link_id = ?", (link_id,))
        store.conn.executemany(
            "INSERT INTO evidence (link_id, source_passage_id, target_passage_id, source_quote, target_quote)"
            " VALUES (?, ?, ?, ?, ?)",
            [(link_id, e.source_passage_id, e.target_passage_id, e.source_quote, e.target_quote)
             for e in candidate.evidence],
        )
    print(f"{len(best)} candidate links from {len(ran)} detectors")


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("detect", help="run every detector and save the candidate links")
    parser.set_defaults(func=detect)
