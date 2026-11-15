"""Shared helpers. Every test drives the public ``book-links`` command and reads the exported graph."""

import json
import sys
from pathlib import Path

import pytest

from pipeline.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_JUDGE = Path(__file__).parent / "fake_judge.py"
FAKE_ARTICLE_MODEL = Path(__file__).parent / "fake_article_model.py"

# title, author, original publication year, fixture file
FIXTURE_WORKS = [
    ("Poems Published in 1820", "John Keats", 1820, "keats_1820_excerpt.txt"),
    ("Hamlet", "William Shakespeare", 1603, "hamlet_excerpt.txt"),
    ("Ulysses", "James Joyce", 1922, "ulysses_excerpt.txt"),
    ("The Waste Land", "T. S. Eliot", 1922, "waste_land_excerpt.txt"),
    ("Common Sense", "Thomas Paine", 1776, "control_excerpt.txt"),
]


class Corpus:
    """A data directory plus the commands a person would run against it."""

    def __init__(self, data_dir: Path, tmp_path: Path):
        self.data = data_dir
        self.tmp = tmp_path
        self._n = 0

    def run(self, *args, ok=True) -> int:
        code = main(["--data", str(self.data), *[str(a) for a in args]])
        if ok:
            assert code == 0, f"book-links {' '.join(str(a) for a in args)} exited {code}"
        return code

    def add_file(self, path, title, author, year):
        self.run("add-file", path, "--title", title, "--author", author, "--year", year)

    def add_text(self, text, title, author, year):
        """Add a work whose text is written by the test."""
        self._n += 1
        path = self.tmp / f"text_{self._n}.txt"
        path.write_text(text, encoding="utf-8")
        self.add_file(path, title, author, year)

    def add_stub(self, title, author, year):
        self.run("add-stub", "--title", title, "--author", author, "--year", year)

    def add_fixture_works(self):
        for title, author, year, name in FIXTURE_WORKS:
            self.add_file(FIXTURES / name, title, author, year)

    def export(self) -> "Graph":
        out = self.tmp / "graph.json"
        self.run("export", out)
        return Graph(json.loads(out.read_text(encoding="utf-8")))


class Graph:
    """The exported graph, with lookups by work title."""

    def __init__(self, raw: dict):
        self.raw = raw
        self.works = raw["works"]
        self.links = raw["links"]
        self._by_id = {w["id"]: w for w in self.works}

    def work(self, title):
        matches = [w for w in self.works if w["title"] == title]
        assert len(matches) == 1, f"expected exactly one work titled {title!r}, found {len(matches)}"
        return matches[0]

    def title_of(self, work_id):
        return self._by_id[work_id]["title"]

    def year_of(self, work_id):
        return self._by_id[work_id]["year"]

    def between(self, source_title, target_title, type=None):
        """Links whose source and target carry these titles (direction matters)."""
        return [
            link
            for link in self.links
            if self.title_of(link["source"]) == source_title
            and self.title_of(link["target"]) == target_title
            and (type is None or link["type"] == type)
        ]

    def one(self, source_title, target_title, type=None):
        found = self.between(source_title, target_title, type)
        assert len(found) == 1, (
            f"expected one {type or 'any'} link {source_title!r} -> {target_title!r}, found {len(found)}; "
            f"all links: {self.describe()}"
        )
        return found[0]

    def touching(self, title):
        return [
            link
            for link in self.links
            if title in (self.title_of(link["source"]), self.title_of(link["target"]))
        ]

    def describe(self):
        return [
            (self.title_of(l["source"]), self.title_of(l["target"]), l["type"], l["status"], round(l["confidence"], 2))
            for l in self.links
        ]


def quotes(link, side):
    """All evidence quotes on one side ('source' or 'target') of a link, lower-cased and joined."""
    return " ".join((e.get(f"{side}_quote") or "") for e in link["evidence"]).lower()


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """An empty corpus whose model calls go to the recorded-response judge."""
    monkeypatch.setenv("BOOK_LINKS_MODEL_CMD", f"{sys.executable} {FAKE_JUDGE}")
    monkeypatch.setenv("FAKE_MODEL_LOG", str(tmp_path / "model_calls.log"))
    data = tmp_path / "data"
    return Corpus(data, tmp_path)


@pytest.fixture
def seeded(corpus):
    """The five fixture excerpts plus the two stubs the project started from."""
    corpus.add_fixture_works()
    corpus.add_stub("Tender Is the Night", "F. Scott Fitzgerald", 1934)
    corpus.add_stub("Infinite Jest", "David Foster Wallace", 1996)
    return corpus
