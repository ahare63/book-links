"""Clusters of distinctive words that two works share and few other works use."""

import math
import re
from collections import defaultdict
from itertools import combinations

from wordfreq import zipf_frequency

from pipeline.detectors.base import Candidate, Detector, Evidence, snippet

MIN_LENGTH = 5
MAX_ZIPF = 3.0
MIN_SHARED = 2
WORDS_PER_PAIR = 5
MAX_SCORE = 0.5
LENGTH_SCALE = 5000

_WORD = re.compile(r"[^\W\d_]{%d,}" % MIN_LENGTH)


class VocabularyDetector(Detector):
    name = "vocabulary"
    version = "1"

    def detect(self, corpus):
        works = sorted((w for w in corpus.works if w.passages and w.year is not None),
                       key=lambda w: (w.year, w.id))
        if len(works) < 2:
            return []
        zipf = {}
        first_use = []
        lengths = []
        users = defaultdict(list)
        for index, work in enumerate(works):
            found, length = self._rare_words(work, zipf)
            first_use.append(found)
            lengths.append(length)
            for word in found:
                users[word].append(index)

        limit = max(2, int(0.05 * len(works)))
        shared = defaultdict(list)
        for word, holders in users.items():
            if 2 <= len(holders) <= limit:
                for a, b in combinations(holders, 2):
                    shared[(a, b)].append(word)

        candidates = []
        for (target_index, source_index), words in sorted(shared.items()):
            source, target = works[source_index], works[target_index]
            if len(words) < MIN_SHARED or self._same_author(source, target):
                continue
            words.sort(key=lambda w: (zipf[w], w))
            candidates.append(self._candidate(
                source, target, words[:WORDS_PER_PAIR], len(words), zipf,
                first_use[source_index], first_use[target_index],
                max(lengths[source_index], lengths[target_index]),
            ))
        return candidates

    @staticmethod
    def _same_author(a, b):
        return bool(a.author.strip()) and a.author.strip().lower() == b.author.strip().lower()

    @staticmethod
    def _rare_words(work, zipf):
        """Distinctive words the work uses in lower case, each with where it first occurs, and the work's length."""
        first = {}
        length = 0
        for passage_index, passage in enumerate(work.passages):
            length += len(passage.text.split())
            for match in _WORD.finditer(passage.text):
                word = match.group()
                if word in first or not word.islower():
                    continue
                if word not in zipf:
                    zipf[word] = zipf_frequency(word, "en")
                if 0 < zipf[word] < MAX_ZIPF:
                    first[word] = (passage_index, match.start(), match.end())
        return first, length

    @staticmethod
    def _candidate(source, target, words, total, zipf, source_use, target_use, length):
        evidence = []
        for word in words:
            sp, ss, se = source_use[word]
            tp, ts, te = target_use[word]
            evidence.append(Evidence(
                source.passages[sp].id, target.passages[tp].id,
                snippet(source.passages[sp].text, ss, se), snippet(target.passages[tp].text, ts, te),
            ))
        strength = sum(0.5 + 0.5 * (MAX_ZIPF - zipf[w]) / MAX_ZIPF for w in words)
        damping = 1 / (1 + math.log10(max(1.0, length / LENGTH_SCALE)))
        score = MAX_SCORE * (1 - math.exp(-1.24 * strength)) * damping
        if source.translated or target.translated:
            score /= 2
        return Candidate(
            source.id, target.id, "shared-vocabulary", score,
            f"Shares {total} distinctive words: {', '.join(words)}", evidence,
        )
