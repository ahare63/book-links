"""Shared word sequences: five-grams that two works have in common, reported as merged spans."""

import heapq
import re
from array import array
from itertools import groupby

from pipeline.detectors.base import Candidate, Detector, Evidence, snippet

NGRAM = 5
MIN_CONTENT_WORDS = 2
SPANS_PER_PAIR = 5

_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*")

STOP_WORDS = frozenset("""
a about above across after afterwards again against ago all almost alone along already also although always am among
amongst an and another any anybody anyone anything anywhere are aren't around as at away be became because become
becomes been before beforehand behind being below beside besides between beyond both but by can can't cannot could
couldn't did didn't do does doesn't doing don't done down during each either else elsewhere enough even ever every
everybody everyone everything everywhere except few for former formerly from further had hadn't has hasn't have haven't
having he hence her here hereby herein hers herself him himself his how however i i'd i'll i'm i've if in indeed
instead into is isn't it it's its itself just last latter least less let like many may me meanwhile might mine more
moreover most mostly much must my myself neither never nevertheless next no nobody none nor not nothing now nowhere of
off often oh on once one ones only onto or other others otherwise ought our ours ourselves out over own perhaps quite
rather really same shall shan't she should shouldn't since so some somebody someone something sometimes somewhat
somewhere still such than that that's the their theirs them themselves then there there's therefore these they they'd
they'll they're they've thine this thither those thou though through throughout thus thy thyself till to together too
toward towards under unless until up upon us very was wasn't we we'd we'll we're we've well were weren't what whatever
when whence whenever where whereas whereby wherein wherever whether which while whither who whoever whole whom whose why
will with within without won't would wouldn't yes yet you you'd you'll you're you've your yours yourself yourselves
ye hath doth art shalt wilt dost hast
""".split())


def words_of(text):
    return _WORD.findall(text.replace("’", "'").replace("‘", "'").lower())


def ngram_hashes(words):
    """Yield ``(index, hash)`` for each five-gram holding at least two content words."""
    n = len(words)
    if n < NGRAM:
        return
    content = [w not in STOP_WORDS for w in words]
    count = sum(content[:NGRAM])
    for i in range(n - NGRAM + 1):
        if i:
            count += content[i + NGRAM - 1] - content[i - 1]
        if count >= MIN_CONTENT_WORDS:
            yield i, hash(tuple(words[i:i + NGRAM]))


def same_author(a, b):
    a, b = a.strip().lower(), b.strip().lower()
    return bool(a) and a == b


def span_score(words):
    if words <= 5:
        return 0.5
    if words <= 8:
        return 0.5 + 0.1 * (words - 5)
    if words <= 12:
        return 0.8 + 0.15 * (words - 8) / 4
    return 0.95


class QuotationDetector(Detector):
    name = "quotation"
    version = "1"

    def detect(self, corpus):
        works = sorted((w for w in corpus.works if w.passages and w.year is not None),
                       key=lambda w: (w.year, w.id))
        shared = self._shared_hashes(works)
        if not shared:
            return []
        first, occurrences = self._locate(works, shared)
        candidates = []
        for source_index, found in sorted(occurrences.items()):
            by_target = {}
            for passage_index, word_index, h in found:
                by_target.setdefault(shared[h][0], []).append((passage_index, word_index, h))
            for target_index, hits in sorted(by_target.items()):
                spans = self._spans(hits, first)
                candidates.append(self._candidate(works[source_index], works[target_index], spans))
        return candidates

    def _shared_hashes(self, works):
        """Map each hash held by works of more than one author to the indexes of its holders, earliest first."""
        per_work = []
        for index, work in enumerate(works):
            hashes = set()
            for passage in work.passages:
                hashes.update(h for _, h in ngram_hashes(words_of(passage.text)))
            per_work.append(array("q", sorted(hashes)))
            del hashes
        streams = [self._tagged(hashes, index) for index, hashes in enumerate(per_work)]
        shared = {}
        for h, group in groupby(heapq.merge(*streams), key=lambda item: item[0]):
            holders = tuple(index for _, index in group)
            if len(holders) > 1 and len({works[i].author.strip().lower() for i in holders}) > 1:
                shared[h] = holders
        return shared

    @staticmethod
    def _tagged(hashes, index):
        return ((h, index) for h in hashes)

    def _locate(self, works, shared):
        """First position in the earliest holder, and every position in each later holder by another author."""
        first = {}
        occurrences = {}
        for index, work in enumerate(works):
            found = []
            for passage_index, passage in enumerate(work.passages):
                for word_index, h in ngram_hashes(words_of(passage.text)):
                    holders = shared.get(h)
                    if holders is None:
                        continue
                    if holders[0] == index:
                        first.setdefault(h, (passage_index, word_index))
                    elif not same_author(work.author, works[holders[0]].author):
                        found.append((passage_index, word_index, h))
            if found:
                occurrences[index] = found
        return first, occurrences

    def _spans(self, hits, first):
        """Merge consecutive five-grams that are also consecutive in the target into spans."""
        spans = []
        for passage_index, word_index, h in hits:
            target_passage, target_word = first[h]
            last = spans[-1] if spans else None
            if (last and last[0] == passage_index and last[2] + 1 == word_index
                    and last[3] == target_passage and last[5] + 1 == target_word):
                last[2] = word_index
                last[5] = target_word
            else:
                spans.append([passage_index, word_index, word_index, target_passage, target_word, target_word])
        unique = {}
        for span in spans:
            unique.setdefault((span[3], span[4]), span)
        ordered = sorted(unique.values(), key=lambda s: (-(s[2] - s[1]), s[0], s[1]))
        return ordered[:SPANS_PER_PAIR]

    def _candidate(self, source, target, spans):
        evidence = []
        for source_passage, s0, s1, target_passage, t0, t1 in spans:
            evidence.append(Evidence(
                source.passages[source_passage].id, target.passages[target_passage].id,
                self._quote(source.passages[source_passage].text, s0, s1),
                self._quote(target.passages[target_passage].text, t0, t1),
            ))
        longest = spans[0][2] - spans[0][1] + NGRAM
        source_passage, s0, s1 = spans[0][:3]
        shown = " ".join(words_of(source.passages[source_passage].text)[s0:s1 + NGRAM])
        return Candidate(
            source.id, target.id, "quotation", span_score(longest),
            f"{len(spans)} shared word sequence(s); the longest is {longest} words: \"{shown}\"",
            evidence,
        )

    @staticmethod
    def _quote(text, first_word, last_word):
        matches = list(_WORD.finditer(text.replace("’", "'").replace("‘", "'")))
        return snippet(text, matches[first_word].start(), matches[last_word + NGRAM - 1].end())
