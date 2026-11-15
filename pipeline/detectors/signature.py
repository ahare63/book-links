"""Terms known to be signatures of a work, found in later works by other authors."""

import re
from collections import defaultdict

from pipeline.detectors.base import Candidate, Detector, Evidence, snippet

SINGLE_TERM_FACTOR = 0.6
MAX_SCORE = 0.95


class SignatureDetector(Detector):
    name = "signature"
    version = "1"

    def detect(self, corpus):
        if not corpus.signature_terms:
            return []
        by_target = defaultdict(dict)
        for term in corpus.signature_terms:
            key = term.term.strip().lower()
            if key:
                current = by_target[term.work_id].get(key, 0.0)
                by_target[term.work_id][key] = max(current, term.weight)
        keys = sorted({key for terms in by_target.values() for key in terms}, key=lambda k: (-len(k), k))
        pattern = re.compile(r"(?<!\w)(?:%s)(?!\w)" % "|".join(re.escape(k) for k in keys), re.IGNORECASE)

        works = sorted(corpus.works, key=lambda w: w.id)
        first_use = {work.id: self._first_uses(work, pattern) for work in works if work.passages}
        by_id = {work.id: work for work in works}

        candidates = []
        for target_id in sorted(by_target):
            target = by_id.get(target_id)
            if target is None or target.year is None:
                continue
            terms = by_target[target_id]
            for source in works:
                if (source.id == target_id or source.year is None or source.year < target.year
                        or source.id not in first_use
                        or source.author.strip().lower() == target.author.strip().lower()):
                    continue
                found = [t for t in sorted(terms) if t in first_use[source.id]]
                if found:
                    candidates.append(self._candidate(source, target, found, terms, first_use))
        return candidates

    @staticmethod
    def _first_uses(work, pattern):
        first = {}
        for passage_index, passage in enumerate(work.passages):
            for match in pattern.finditer(passage.text):
                first.setdefault(match.group().lower(), (passage_index, match.start(), match.end()))
        return first

    @staticmethod
    def _candidate(source, target, found, weights, first_use):
        evidence = []
        miss = 1.0
        for term in found:
            sp, ss, se = first_use[source.id][term]
            item = Evidence(source.passages[sp].id, None, snippet(source.passages[sp].text, ss, se), None)
            if target.id in first_use and term in first_use[target.id]:
                tp, ts, te = first_use[target.id][term]
                item.target_passage_id = target.passages[tp].id
                item.target_quote = snippet(target.passages[tp].text, ts, te)
            evidence.append(item)
            miss *= 1 - SINGLE_TERM_FACTOR * max(0.0, min(1.0, weights[term]))
        return Candidate(
            source.id, target.id, "shared-vocabulary", min(MAX_SCORE, 1 - miss),
            f"Uses {', '.join(found)}, known as signature of {target.title}", evidence,
        )
