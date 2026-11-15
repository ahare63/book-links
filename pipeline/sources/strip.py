"""Licence stripping and passage splitting for Project Gutenberg style texts."""

import re

START = re.compile(r"^[ \t]*\*{3}[ \t]*START OF (?:THE|THIS) PROJECT GUTENBERG\b[^\n]*$", re.I | re.M)
END = re.compile(r"^[ \t]*\*{3}[ \t]*END OF (?:THE|THIS) PROJECT GUTENBERG\b[^\n]*$", re.I | re.M)

AU_NAME = re.compile(r"Project Gutenberg (?:of )?Australia", re.I)
AU_HEADER_LINES = 80
AU_FOOTER_LINES = 30
AU_RULE = re.compile(r"^-{20,}[ \t]*$", re.M)
AU_REPEATED_TITLE = re.compile(
    r"\A\s*A Project Gutenberg of Australia eBook[ \t]*\n(?:\s*Title:[^\n]*\n)?(?:\s*Author:[^\n]*\n)?", re.I
)
AU_END = re.compile(r"^[ \t]*THE END\.?[ \t]*$", re.I | re.M)


def decode(raw):
    """Decode bytes as UTF-8, falling back to Windows-1252 for old Latin-1 files."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def normalise_newlines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def header_field(text, name):
    """The value of a ``Name: value`` line in the header (the text before the START marker)."""
    start = START.search(text)
    header = text[: start.start()] if start else text
    match = re.search(rf"^{name}:[ \t]*(.+?)[ \t]*$", header, re.I | re.M)
    return match.group(1) if match else None


def strip_licence(text):
    """Return (stripped text, problem). ``problem`` is None, or a short note that a boundary was not found.

    ``text`` must already have LF line endings.
    """
    start, end = START.search(text), None
    if start:
        end = END.search(text, start.end())
        body_from = start.end() + 1 if text[start.end():start.end() + 1] == "\n" else start.end()
        return text[body_from : end.start() if end else len(text)], (None if end else "no END marker")
    if AU_NAME.search("\n".join(text.split("\n")[:AU_HEADER_LINES])):
        return _strip_australian(text)
    return text, "no START or END marker"


def _strip_australian(text):
    head_end = 0
    rule = AU_RULE.search(text, 0, _offset_of_line(text, AU_HEADER_LINES))
    if rule:
        head_end = rule.end() + 1
        repeated = AU_REPEATED_TITLE.match(text[head_end:])
        if repeated:
            head_end += repeated.end()
    tail_from = _offset_of_line(text, max(0, text.count("\n") - AU_FOOTER_LINES))
    ends = [m for m in AU_END.finditer(text, tail_from)]
    problems = []
    if not rule:
        problems.append("no header rule")
    if not ends:
        problems.append("no THE END line")
    body_to = ends[-1].start() if ends else len(text)
    return text[head_end:body_to], ("; ".join(problems) or None)


def _offset_of_line(text, line_number):
    offset = 0
    for _ in range(line_number):
        found = text.find("\n", offset)
        if found == -1:
            return len(text)
        offset = found + 1
    return offset


PARAGRAPH = re.compile(r"\S[^\n]*(?:\n[ \t]*\S[^\n]*)*")


def split_passages(text):
    """Paragraphs separated by blank lines, as (character offset of first character, text)."""
    return [(m.start(), m.group().rstrip()) for m in PARAGRAPH.finditer(text)]
