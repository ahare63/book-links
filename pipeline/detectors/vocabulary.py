"""Clusters of distinctive words that two works share and few other works use.

Two long books share a few rare words by chance, so a pair is proposed only when it shares
far more than chance predicts from the size of each book's rare vocabulary.
"""

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
# Chance overlap is estimated from the corpus itself, plus this many imaginary shared words standing
# for the rest of English's rare vocabulary. Without them a corpus of a few short texts would make
# any two shared rare words look expected; with them, small corpora lean towards proposing.
PRIOR_POOL = 1000
# Across all pairs tested, about this many pairs should pass by chance alone.
FALSE_PAIRS = 0.5

_WORD = re.compile(rf"[^\W\d_]{{{MIN_LENGTH},}}")


def poisson_tail(count, expected):
    """The probability of seeing ``count`` or more when chance predicts ``expected``."""
    term = math.exp(-expected)
    below = 0.0
    for k in range(count):
        below += term
        term *= expected / (k + 1)
    return max(0.0, 1.0 - below)


class VocabularyDetector(Detector):
    name = "vocabulary"
    version = "3"

    def detect(self, corpus):
        works = sorted(
            (w for w in corpus.works if w.passages and w.text_year is not None), key=lambda w: (w.text_year, w.id)
        )
        if len(works) < 2:
            return []
        zipf = {}
        first_use = []
        users = defaultdict(list)
        for index, work in enumerate(works):
            found = self._rare_words(work, zipf)
            first_use.append(found)
            for word in found:
                users[word].append(index)

        limit = max(2, int(0.05 * len(works)))
        shared = defaultdict(list)
        pairable = [0] * len(works)  # per work: its distinctive words that some other work also uses
        pool = PRIOR_POOL
        for word, holders in users.items():
            if 2 <= len(holders) <= limit:
                pool += len(holders) * (len(holders) - 1) // 2
                for index in holders:
                    pairable[index] += len(holders) - 1
                for a, b in combinations(holders, 2):
                    shared[(a, b)].append(word)

        max_chance = FALSE_PAIRS / (len(works) * (len(works) - 1) / 2)
        candidates = []
        for (target_index, source_index), words in sorted(shared.items()):
            source, target = works[source_index], works[target_index]
            if len(words) < MIN_SHARED or self._same_author(source, target):
                continue
            # If shared words fell on pairs at random, this pair would get about this many.
            expected = pairable[source_index] * pairable[target_index] / (2 * pool)
            chance = poisson_tail(len(words), expected)
            if chance > max_chance:
                continue
            words.sort(key=lambda w: (zipf[w], w))
            candidates.append(
                self._candidate(
                    source,
                    target,
                    words[:WORDS_PER_PAIR],
                    len(words),
                    expected,
                    chance,
                    first_use[source_index],
                    first_use[target_index],
                )
            )
        return candidates

    @staticmethod
    def _same_author(a, b):
        return bool(a.author.strip()) and a.author.strip().lower() == b.author.strip().lower()

    @staticmethod
    def _rare_words(work, zipf):
        """Distinctive words the work uses in lower case, each with where it first occurs."""
        first = {}
        for passage_index, passage in enumerate(work.passages):
            for match in _WORD.finditer(passage.text):
                word = match.group()
                if word in first or not word.islower():
                    continue
                if word not in zipf:
                    zipf[word] = zipf_frequency(word, "en")
                if 0 < zipf[word] < MAX_ZIPF:
                    first[word] = (passage_index, match.start(), match.end())
        return first

    @staticmethod
    def _candidate(source, target, words, total, expected, chance, source_use, target_use):
        evidence = []
        for word in words:
            sp, ss, se = source_use[word]
            tp, ts, te = target_use[word]
            evidence.append(
                Evidence(
                    source.passages[sp].id,
                    target.passages[tp].id,
                    snippet(source.passages[sp].text, ss, se),
                    snippet(target.passages[tp].text, ts, te),
                )
            )
        score = min(MAX_SCORE, 0.1 * -math.log10(max(chance, 1e-16)))
        if source.translated or target.translated:
            score /= 2
        return Candidate(
            source.id,
            target.id,
            "shared-vocabulary",
            score,
            f"Shares {total} rare words that at most one other work here uses (chance predicts about {expected:.1f}): "
            f"{', '.join(words)}",
            evidence,
        )
