"""Fetching works and publication years over HTTP, against a local server standing in for the sites."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conftest import FIXTURES, quotes

KEATS = (FIXTURES / "keats_1820_excerpt.txt").read_text(encoding="utf-8")
GUTENBERG_FILE = "Title: Keats: Poems Published in 1820\n\nAuthor: John Keats\n\n" + KEATS
HAMLET = (FIXTURES / "hamlet_excerpt.txt").read_text(encoding="utf-8")

SPARQL = {
    "results": {
        "bindings": [
            {"pg": {"value": "23684"}, "year": {"value": "1820"}},
        ]
    }
}


class Site:
    """Serves a fixed set of paths and records every request."""

    def __init__(self, pages):
        self.pages = pages
        self.requests = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                site.requests.append(self.path)
                path = self.path.split("?")[0]
                if path not in site.pages:
                    self.send_response(404)
                    self.end_headers()
                    return
                body = site.pages[path].encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def site(monkeypatch):
    site = Site(
        {
            "/cache/epub/23684/pg23684.txt": GUTENBERG_FILE,
            "/ebooks03/0301261.txt": HAMLET,
            "/sparql": json.dumps(SPARQL),
            "/cache/epub/777/pg777.txt": "<html><body>Too many requests</body></html>",
        }
    )
    monkeypatch.setenv("BOOK_LINKS_GUTENBERG_URL", site.url + "/cache/epub/{id}/pg{id}.txt")
    monkeypatch.setenv("BOOK_LINKS_WIKIDATA_URL", site.url + "/sparql")
    monkeypatch.setenv("BOOK_LINKS_FETCH_DELAY", "0")
    yield site
    site.close()


def test_add_book_fetches_by_id_and_reads_title_and_author_from_the_file(corpus, site):
    corpus.run("add-book", "23684", "--year", "1820")
    corpus.add_stub("Tender Is the Night", "F. Scott Fitzgerald", 1934)
    corpus.run("detect")

    graph = corpus.export()

    work = graph.work("Keats: Poems Published in 1820")
    assert work["author"] == "John Keats"
    assert work["source"] == "gutenberg-us"
    link = graph.one("Tender Is the Night", "Keats: Poems Published in 1820", "title-source")
    assert "tender is the night" in quotes(link, "target")


def test_add_book_twice_downloads_once(corpus, site):
    corpus.run("add-book", "23684", "--year", "1820")
    corpus.run("add-book", "23684", "--year", "1820")

    assert len([r for r in site.requests if "pg23684" in r]) == 1
    assert len(corpus.export().works) == 1


def test_add_book_for_a_missing_id_fails_without_adding_a_work(corpus, site):
    code = corpus.run("add-book", "999999", ok=False)

    assert code != 0
    assert corpus.export().works == []


def test_add_url_takes_a_text_from_the_australian_site(corpus, site, monkeypatch):
    corpus.run(
        "add-url", site.url + "/ebooks03/0301261.txt",
        "--title", "Borrowed Text", "--author", "Some Author", "--year", "1934",
    )
    corpus.add_stub("Infinite Jest", "David Foster Wallace", 1996)
    corpus.run("detect")

    graph = corpus.export()

    assert graph.work("Borrowed Text")["source"] == "gutenberg-au"
    graph.one("Infinite Jest", "Borrowed Text", "title-source")


def test_years_fills_in_missing_publication_years_from_wikidata(corpus, site):
    corpus.run("add-book", "23684")
    assert corpus.export().work("Keats: Poems Published in 1820")["year"] is None

    corpus.run("years")

    assert corpus.export().work("Keats: Poems Published in 1820")["year"] == 1820


def test_years_keeps_a_year_the_owner_gave(corpus, site):
    corpus.run("add-book", "23684", "--year", "1819")

    corpus.run("years")

    assert corpus.export().work("Keats: Poems Published in 1820")["year"] == 1819


def test_a_work_with_no_known_year_is_not_given_a_direction_it_cannot_support(corpus, site):
    corpus.run("add-book", "23684")
    corpus.add_stub("Tender Is the Night", "F. Scott Fitzgerald", 1934)
    corpus.run("detect")

    graph = corpus.export()

    assert graph.touching("Keats: Poems Published in 1820") == []


def test_a_page_that_is_not_a_gutenberg_text_is_refused_and_not_kept(corpus, site):
    code = corpus.run("add-book", "777", "--year", "1900", ok=False)
    site.pages["/cache/epub/777/pg777.txt"] = GUTENBERG_FILE

    assert code != 0
    assert corpus.export().works == []
    corpus.run("add-book", "777", "--year", "1820")
    assert len([r for r in site.requests if "pg777" in r]) == 2


def test_add_book_refuses_an_id_that_is_not_a_number(corpus, site):
    code = corpus.run("add-book", "../23684", ok=False)

    assert code != 0
    assert site.requests == []
