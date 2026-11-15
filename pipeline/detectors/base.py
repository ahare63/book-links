"""What a detector sees and what it returns.

A detector reads the corpus and proposes candidate links with evidence and a raw score. It never
writes to the store; the runner checks dates, attaches links to subworks and saves them.
"""

from dataclasses import dataclass, field

LINK_TYPES = ["quotation", "title-source", "mention", "allusion", "shared-vocabulary", "theme"]

QUOTE_LIMIT = 300


@dataclass(frozen=True)
class Passage:
    id: int
    position: int
    text: str


@dataclass(frozen=True)
class Work:
    """A top-level work (full text or stub). Stubs have no passages."""

    id: int
    title: str
    author: str
    year: int | None
    kind: str
    translated: bool
    passages: tuple = ()


@dataclass(frozen=True)
class SignatureTerm:
    term: str
    work_id: int
    weight: float


@dataclass(frozen=True)
class Corpus:
    works: tuple
    signature_terms: tuple = ()


@dataclass
class Evidence:
    """One pair of short quotes. Either side may be missing (a stub has no text to quote)."""

    source_passage_id: int | None = None
    target_passage_id: int | None = None
    source_quote: str | None = None
    target_quote: str | None = None


@dataclass
class Candidate:
    """A proposed link: ``source`` (the later work) draws on ``target`` (the earlier one)."""

    source_id: int
    target_id: int
    type: str
    score: float
    rationale: str
    evidence: list = field(default_factory=list)


class Detector:
    """Subclasses set ``name`` and ``version`` and implement ``detect``.

    Bump ``version`` whenever a change would alter what the detector proposes.
    """

    name = ""
    version = "1"

    def detect(self, corpus: Corpus):
        raise NotImplementedError


def dated(earlier: Work, later: Work) -> bool:
    """True when both years are known and ``later`` was not published before ``earlier``."""
    return earlier.year is not None and later.year is not None and later.year >= earlier.year


def snippet(text: str, start: int, end: int, limit: int = QUOTE_LIMIT) -> str:
    """The text around ``text[start:end]``, widened to whole lines and cut to ``limit`` characters."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    if line_end - line_start > limit:
        pad = max(0, (limit - (end - start)) // 2)
        line_start = max(line_start, start - pad)
        line_end = min(line_end, line_start + limit)
    return " ".join(text[line_start:line_end].split())
