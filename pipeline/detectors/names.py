"""A later text that uses the names of an earlier work's people and places, or names its author.

Names survive translation, so this finds allusions that share no wording: Dante's Aeneas and
Dido point to the Aeneid whichever English version is held. A collection's declared subworks are
treated as separate works here, so names from the book of Jonah point to Jonah, not to the Bible.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from wordfreq import zipf_frequency

from pipeline.detectors.base import Candidate, Detector, Evidence, snippet

TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
POSSESSIVE = re.compile(r"['’]s$")
SENTENCE_START = re.compile(r"(?:^|[.!?:;\"“‘(\[—])\s*$")  # closing quotes and hyphens do not start one
TITLE_ABBREVIATION = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|St|Mt|Messrs|Mme|Mlle|Rev|Col|Capt|Gen|Sir)\.\s*$")

MIN_LENGTH = 4
MIN_USES = 3  # capitalised uses for a word to count as one of a work's names
PROPER_SHARE = 0.9  # share of a word's uses that are capitalised, so sentence-initial words do not count
MAX_ZIPF = 4.0  # names that are also common words ("Hope", "Grace") or famous places ("London") are not evidence
MAX_HOLDERS = 0.12  # a name used by more than this share of works is too widespread to point anywhere
MIN_NAMES = 3  # without the author's name; two shared names are still often a shared place or myth
MIN_AUTHOR_USES = 2  # the author's name alone needs this many uses in the later text
LOWER_SHARE = 0.05  # a word written in lower case more often than this, anywhere in the corpus, is not a name
NAME_WEIGHT = 0.25
AUTHOR_WEIGHT = 0.35
SCORE_CAP = 0.5
EVIDENCE_PER_CANDIDATE = 5
NO_AUTHOR = {"various", "anonymous", "unknown"}


@dataclass
class Unit:
    """A work, or one declared subwork of it, with the passages that fall inside it."""

    work: object  # the Work the unit stands for (a subwork, or the top-level work itself)
    top: object  # the top-level work whose passages these are
    passages: list = field(default_factory=list)
    capitals: Counter = field(default_factory=Counter)
    lower: Counter = field(default_factory=Counter)
    first_use: dict = field(default_factory=dict)  # name -> (passage, start, end)
    names: set = field(default_factory=set)


class NamesDetector(Detector):
    name = "names"
    version = "4"

    def detect(self, corpus):
        units = self._units(corpus)
        # Holders are counted by top-level work, so Pharaoh used across the books of the Bible is one holder.
        holders, capitals, lower = Counter(), Counter(), Counter()
        for top_id in {unit.top.id for unit in units}:
            holders.update({name for unit in units if unit.top.id == top_id for name in unit.capitals})
        for unit in units:
            capitals.update({word.lower(): n for word, n in unit.capitals.items()})
            lower.update(unit.lower)
        for unit in units:
            # Translators capitalise common nouns ("the Convent"); the rest of the corpus gives them away.
            unit.names = {n for n in unit.names if lower[n.lower()] <= LOWER_SHARE * capitals[n.lower()]}
        limit = max(3, MAX_HOLDERS * len({unit.top.id for unit in units}))
        # Like a quotation, a name points only to the earliest work that uses it as a name, and there to
        # every part that does: Nineveh belongs to Jonah and Nahum alike, not to whichever is dated first.
        first = {}
        for unit in units:
            year = unit.work.year if unit.work.year is not None else 10**6
            for name in unit.names:
                first[name] = min(first.get(name, (year, unit.top.id)), (year, unit.top.id))
        for unit in units:
            unit.names = {name for name in unit.names if holders[name] <= limit and first[name][1] == unit.top.id}

        candidates = []
        for source in units:
            for target in units:
                candidate = self._pair(source, target, holders, limit)
                if candidate is not None:
                    candidates.append(candidate)
        return candidates

    def _units(self, corpus):
        subworks = defaultdict(list)
        for work in corpus.works:
            if work.parent_id is not None and work.span is not None:
                subworks[work.parent_id].append(work)
        units = []
        for top in corpus.works:
            if not top.passages:
                continue
            own = Unit(top, top)
            parts = [Unit(sub, top) for sub in subworks[top.id]]
            for passage in top.passages:
                inside = [u for u in parts if u.work.span[0] <= passage.position < u.work.span[1]]
                (inside[0] if inside else own).passages.append(passage)
            for unit in [own, *parts]:
                if unit.passages:
                    self._read(unit)
                    units.append(unit)
        return units

    @staticmethod
    def _read(unit):
        uses = Counter()
        for passage in unit.passages:
            text = passage.text
            for match in TOKEN.finditer(text):
                word = POSSESSIVE.sub("", match.group())
                line_start = text.rfind("\n", 0, match.start()) + 1
                before = text[line_start : match.start()]
                if SENTENCE_START.search(before) and not TITLE_ABBREVIATION.search(before):
                    continue  # a capital that starts a sentence or a line of verse says nothing
                uses[word.lower()] += 1
                if word.islower():
                    unit.lower[word] += 1
                elif word[0].isupper() and not word.isupper():
                    unit.capitals[word] += 1
                    unit.first_use.setdefault(word, (passage, match.start(), match.end()))
        unit.names = {
            word
            for word, count in unit.capitals.items()
            if count >= MIN_USES
            and len(word) >= MIN_LENGTH
            and count >= PROPER_SHARE * uses[word.lower()]
            and zipf_frequency(word.lower(), "en") < MAX_ZIPF
        }

    def _pair(self, source, target, holders, limit):
        later, earlier = source.work, target.work
        if source.top.id == target.top.id or later.author == earlier.author:
            return None
        if later.year is None or earlier.year is None or later.year < earlier.year:
            return None
        own = {self._surname(later), self._surname(earlier)}
        shared = sorted(
            (name for name in target.names if name in source.capitals and name not in own),
            key=lambda name: (holders[name], name),
        )
        author = self._author_name(target)
        named_author = author if author and author in source.capitals and author != self._surname(later) else None
        if named_author is None and len(shared) < MIN_NAMES:
            return None
        if named_author is not None and not shared and source.capitals[named_author] < MIN_AUTHOR_USES:
            return None

        miss = 1.0
        for name in shared:
            miss *= 1 - NAME_WEIGHT * (1 - (holders[name] - 1) / limit)
        if named_author:
            miss *= 1 - AUTHOR_WEIGHT
        score = round(min(SCORE_CAP, 1 - miss), 3)

        evidence = []
        if named_author:
            evidence.append(Evidence(**self._quote(source, named_author, "source")))
        for name in shared[: EVIDENCE_PER_CANDIDATE - len(evidence)]:
            evidence.append(Evidence(**self._quote(source, name, "source"), **self._quote(target, name, "target")))
        return Candidate(
            source_id=source.top.id,
            target_id=target.top.id,
            type="allusion",
            score=score,
            rationale=self._rationale(later, earlier, shared, named_author),
            evidence=evidence,
        )

    @staticmethod
    def _surname(work):
        words = TOKEN.findall(work.author or "")
        return words[-1] if words and work.author.lower() not in NO_AUTHOR else None

    def _author_name(self, unit):
        """The author's surname, for a whole work only: naming Shakespeare does not point to one play."""
        if unit.work is not unit.top:
            return None
        return self._surname(unit.work)

    @staticmethod
    def _quote(unit, name, side):
        passage, start, end = unit.first_use[name]
        return {f"{side}_passage_id": passage.id, f"{side}_quote": snippet(passage.text, start, end)}

    @staticmethod
    def _rationale(later, earlier, shared, author):
        parts = []
        if shared:
            listed = ", ".join(shared[:-1]) + f" and {shared[-1]}" if len(shared) > 1 else shared[0]
            parts.append(f'names {listed} from "{earlier.title}"')
        if author:
            parts.append(f"names its author, {author}")
        return f'"{later.title}" ' + "; ".join(parts) + "."
