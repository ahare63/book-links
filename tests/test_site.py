"""build-site: the read-only copy of the viewer and graph that is published to GitHub Pages."""

import json

import pytest

from conftest import quotes
from test_sources import site  # noqa: F401  (the stand-in for gutenberg.org)


@pytest.fixture
def viewer_dist(tmp_path, monkeypatch):
    dist = tmp_path / "viewer_dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>viewer</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setenv("BOOK_LINKS_VIEWER_DIST", str(dist))
    return dist


def build(corpus, out):
    corpus.run("build-site", "--out", out)
    return json.loads((out / "graph.json").read_text(encoding="utf-8"))


def test_the_site_graph_is_read_only_and_leaves_out_rejected_links(seeded, viewer_dist):
    seeded.run("detect")
    seeded.run("judge")
    before = seeded.export()
    victim = before.one("Infinite Jest", "Hamlet")
    seeded.run("review", victim["id"], "--verdict", "reject")

    graph = build(seeded, seeded.tmp / "site")

    assert graph["reviewable"] is False
    assert graph["links"], "accepted and proposed links stay"
    assert all(link["status"] != "rejected" for link in graph["links"])
    assert victim["id"] not in {link["id"] for link in graph["links"]}
    assert {link["id"] for link in graph["links"]} == {link["id"] for link in before.links} - {victim["id"]}


def test_the_site_graph_leaves_out_review_notes(seeded, viewer_dist):
    seeded.run("detect")
    link = seeded.export().one("Infinite Jest", "Hamlet")
    seeded.run("review", link["id"], "--verdict", "accept", "--note", "my private note")

    graph = build(seeded, seeded.tmp / "site")

    assert "my private note" not in json.dumps(graph)


def test_the_site_graph_quotes_both_sides_whichever_site_the_text_came_from(corpus, site, viewer_dist):  # noqa: F811
    corpus.run("add-book", "23684", "--year", "1820")
    corpus.add_text(
        "Already with thee! tender is the night, And haply the Queen-Moon is on her throne,",
        "Tender Is the Night",
        "F. Scott Fitzgerald",
        1934,
    )
    corpus.run("detect")

    graph = build(corpus, corpus.tmp / "site")

    links = [link for link in graph["links"] if link["type"] == "quotation"]
    assert links
    assert "queen-moon" in quotes(links[0], "target")
    assert "tender is the night" in quotes(links[0], "source")


def test_the_site_contains_the_built_viewer(seeded, viewer_dist):
    out = seeded.tmp / "site"
    build(seeded, out)

    assert (out / "index.html").read_text(encoding="utf-8") == "<html>viewer</html>"
    assert (out / "assets" / "app.js").is_file()


def test_build_site_without_a_built_viewer_says_how_to_build_it(seeded, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOOK_LINKS_VIEWER_DIST", str(tmp_path / "missing"))
    out = tmp_path / "site"

    code = seeded.run("build-site", "--out", out, ok=False)

    assert code != 0
    assert "npm run build" in capsys.readouterr().err
    assert not out.exists()
