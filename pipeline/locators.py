"""Citations for quoted passages: the play, act and scene, or the Bible book, chapter and verse."""

import re
from bisect import bisect_right

from pipeline.ingest import stripped_text
from pipeline.subworks import subwork_at, subwork_ranges

QUOTE_PREFIX = 60  # characters of a quote used to find it in the text
SEARCH_SLACK = 200  # how far past the end of its passage a quote is looked for

_ACT = re.compile(r"^ACT ([IVXL]+)\.?[ \t]*$", re.MULTILINE)
_SCENE = re.compile(r"^SCENE ([IVXL]+)\b", re.MULTILINE)
_VERSE = re.compile(r"(?<!\S)(\d+:\d+)(?=\s)")
_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}


def _roman(numeral):
    total = 0
    values = [_ROMAN[char] for char in numeral]
    for value, following in zip(values, values[1:] + [0], strict=True):
        total += -value if following > value else value
    return total


def _last_before(markers, offset):
    """The last ``(position, value)`` of a sorted list that is at or before ``offset``, or None."""
    index = bisect_right(markers, offset, key=lambda marker: marker[0])
    return markers[index - 1] if index else None


class _Headings:
    """The act and scene headings, or chapter:verse markers, inside one subwork."""

    def __init__(self, text, start, end):
        self.acts = [(m.start(), _roman(m.group(1))) for m in _ACT.finditer(text, start, end)]
        self.scenes = [(m.start(), _roman(m.group(1))) for m in _SCENE.finditer(text, start, end)]
        self.verses = [(m.start(), m.group(1)) for m in _VERSE.finditer(text, start, end)]

    def label(self, title, offset):
        act = _last_before(self.acts, offset)
        if act is not None:
            scene = _last_before(self.scenes, offset)
            if scene is not None and scene[0] > act[0]:
                return f"{title}, Act {act[1]}, Scene {scene[1]}"
            return f"{title}, Act {act[1]}"
        verse = _last_before(self.verses, offset)
        return title if verse is None else f"{title} {verse[1]}"


class Locators:
    """Works out a citation for each quoted passage from its position in the collection's text."""

    def __init__(self, store):
        self.store = store
        self.ranges = subwork_ranges(store)
        self.subworks = {row["id"]: row for row in store.works() if row["kind"] == "subwork"}
        self.texts = {}
        self.headings = {}

    def locate(self, passage_id, quote):
        """``{"work": subwork id, "label": citation}`` for a passage, or None outside every subwork."""
        if passage_id is None:
            return None
        passage = self.store.conn.execute(
            "SELECT work_id, position, text FROM passages WHERE id = ?", (passage_id,)
        ).fetchone()
        subwork_id = subwork_at(self.ranges, passage["work_id"], passage["position"])
        if subwork_id is None:
            return None
        subwork = self.subworks[subwork_id]
        text = self._text(passage["work_id"])
        if text is None:
            return {"work": subwork_id, "label": subwork["title"]}
        offset = self._offset(text, passage, quote)
        if not subwork["start_pos"] <= offset < subwork["end_pos"]:
            offset = passage["position"]
        return {"work": subwork_id, "label": self._headings(subwork_id, text).label(subwork["title"], offset)}

    def _text(self, work_id):
        if work_id not in self.texts:
            self.texts[work_id] = stripped_text(self.store, work_id)
        return self.texts[work_id]

    def _headings(self, subwork_id, text):
        if subwork_id not in self.headings:
            row = self.subworks[subwork_id]
            self.headings[subwork_id] = _Headings(text, row["start_pos"], row["end_pos"])
        return self.headings[subwork_id]

    @staticmethod
    def _offset(text, passage, quote):
        """Where the quote starts in the text, or the passage position when it cannot be found."""
        words = (quote or "")[:QUOTE_PREFIX].split()
        if not words:
            return passage["position"]
        pattern = re.compile(r"\s+".join(re.escape(word) for word in words))
        found = pattern.search(text, passage["position"], passage["position"] + len(passage["text"]) + SEARCH_SLACK)
        return found.start() if found else passage["position"]
