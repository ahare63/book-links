"""A later text that names an earlier work by its title, optionally with its author."""

from collections import defaultdict

from pipeline.detectors.base import Candidate, Detector, Evidence, snippet
from pipeline.detectors.title import ARTICLES, EVIDENCE_PER_CANDIDATE, PhraseIndex, one_word_weight, phrase_for, words


class MentionDetector(Detector):
    name = "mention"
    version = "2"

    def detect(self, corpus):
        titled = {}
        for work in corpus.works:
            phrase = phrase_for(work.title)
            if phrase is None or work.year is None:
                continue
            if len(phrase[1]) == 1 and one_word_weight(phrase[1][0]) == 0.0:
                continue
            titled[work.id] = (work, phrase)
        titles = PhraseIndex((wid, phrase) for wid, (_, phrase) in titled.items())
        authors = {}
        for work in corpus.works:
            phrase = phrase_for(work.author)
            if phrase is not None and len(phrase[1]) > 1:
                authors.setdefault(phrase[1], phrase)
        author_index = PhraseIndex((lower, phrase) for lower, phrase in authors.items())

        candidates = []
        for text_work in corpus.works:
            if not text_work.passages or text_work.text_year is None:
                continue
            found = defaultdict(dict)
            named = set()
            for passage in text_work.passages:
                tokens = words(passage.text)
                for lower, _, _ in author_index.matches(tokens):
                    named.add(lower)
                for wid, first, last in titles.matches(tokens, as_printed=True):
                    work = titled[wid][0]
                    if work.id == text_work.id or work.year >= text_work.text_year or work.author == text_work.author:
                        continue
                    quote = snippet(passage.text, tokens[first][2], tokens[last][3])
                    hit = found[wid].setdefault(passage.id, [0, passage.position, passage.id, quote])
                    hit[0] += 1
            for wid in sorted(found):
                work, (_, lower) = titled[wid]
                author = phrase_for(work.author)
                with_author = author is not None and author[1] in named
                hits = sorted(found[wid].values(), key=lambda h: (-h[0], h[1]))[:EVIDENCE_PER_CANDIDATE]
                candidates.append(
                    Candidate(
                        source_id=text_work.id,
                        target_id=wid,
                        type="mention",
                        score=self.score(lower, with_author),
                        rationale=f'"{text_work.title}" names "{work.title}"'
                        + (f" and its author {work.author}." if with_author else "."),
                        evidence=[Evidence(source_passage_id=pid, source_quote=quote) for _, _, pid, quote in hits],
                    )
                )
        return candidates

    @staticmethod
    def score(lower, with_author):
        distinct = [w for w in lower if w not in ARTICLES]
        if len(distinct) == 1:
            base = 0.3 * one_word_weight(distinct[0])
            return round(base + (0.3 if with_author else 0.0), 3)
        base = {2: 0.5, 3: 0.6}.get(len(lower), 0.7)
        return round(base + (0.2 if with_author else 0.0), 3)
