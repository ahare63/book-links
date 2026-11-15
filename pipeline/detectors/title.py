"""A work's title found inside another work's text."""

import re
from collections import defaultdict

from wordfreq import zipf_frequency

from pipeline.detectors.base import Candidate, Detector, Evidence, dated, snippet

EVIDENCE_PER_CANDIDATE = 5
ARTICLES = {"the", "a", "an"}
TOO_COMMON = 5.0
WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")


def words(text):
    """Each word of ``text`` as ``(original, lower-cased, start, end)``; punctuation is skipped."""
    return [(m.group(), m.group().lower().replace("’", "'"), m.start(), m.end()) for m in WORD.finditer(text)]


def title_words(title):
    """The words a title is matched by; a leading article is dropped when two or more words remain."""
    found = [w[:2] for w in words(title)]
    if len(found) > 2 and found[0][1] in ARTICLES:
        found = found[1:]
    return found


def phrase_for(title):
    """``(original words, lower-cased words)`` of a title, or None when it has no words."""
    found = title_words(title)
    if not found:
        return None
    return tuple(w[0] for w in found), tuple(w[1] for w in found)


def one_word_weight(word):
    """How far a single-word title is trusted: 0 for everyday words, up to 1 for rare ones."""
    zipf = zipf_frequency(word, "en")
    if zipf > TOO_COMMON:
        return 0.0
    if zipf > 4.0:
        return 0.4
    if zipf > 3.0:
        return 0.7
    return 1.0


class PhraseIndex:
    """Titles looked up by their first word, so a text is scanned once."""

    def __init__(self, entries):
        self.by_first = defaultdict(list)
        for key, (original, lower) in entries:
            self.by_first[lower[0]].append((key, original, lower))

    def matches(self, tokens, case_sensitive_single=False):
        """Yield ``(key, token index)`` for every phrase found in ``tokens`` (from ``words``)."""
        lowers = [t[1] for t in tokens]
        for i, lower in enumerate(lowers):
            for key, original, phrase in self.by_first.get(lower, ()):
                n = len(phrase)
                if tuple(lowers[i:i + n]) != phrase:
                    continue
                if n == 1 and case_sensitive_single and tokens[i][0].replace("’", "'") != original[0].replace("’", "'"):
                    continue
                yield key, i, i + n - 1


class TitleDetector(Detector):
    name = "title"
    version = "1"

    def detect(self, corpus):
        titled = {}
        for work in corpus.works:
            phrase = phrase_for(work.title)
            if phrase is None or work.year is None:
                continue
            if len(phrase[1]) == 1 and one_word_weight(phrase[1][0]) == 0.0:
                continue
            titled[work.id] = (work, phrase)
        index = PhraseIndex((wid, phrase) for wid, (_, phrase) in titled.items())

        candidates = []
        for text_work in corpus.works:
            if not text_work.passages:
                continue
            found = defaultdict(dict)
            for passage in text_work.passages:
                tokens = words(passage.text)
                for wid, first, last in index.matches(tokens):
                    if wid == text_work.id:
                        continue
                    work = titled[wid][0]
                    if not dated(text_work, work):
                        continue
                    quote = snippet(passage.text, tokens[first][2], tokens[last][3])
                    hit = found[wid].setdefault(passage.id, [0, passage.position, passage.id, quote])
                    hit[0] += 1
            for wid in sorted(found):
                work, (_, lower) = titled[wid]
                hits = sorted(found[wid].values(), key=lambda h: (-h[0], h[1]))[:EVIDENCE_PER_CANDIDATE]
                evidence = [Evidence(target_passage_id=pid, target_quote=quote) for _, _, pid, quote in hits]
                candidates.append(Candidate(
                    source_id=wid,
                    target_id=text_work.id,
                    type="title-source",
                    score=self.score(lower),
                    rationale=f"The title \"{work.title}\" appears in the text of \"{text_work.title}\".",
                    evidence=evidence,
                ))
        return candidates

    @staticmethod
    def score(lower):
        if len(lower) == 1:
            return round(0.2 * one_word_weight(lower[0]), 3)
        return {2: 0.6, 3: 0.8}.get(len(lower), 0.9)
