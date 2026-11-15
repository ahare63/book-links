"""The gold-list report, and the local review server the viewer talks to."""

import json
import threading
import urllib.request

import pytest

from pipeline.serve import make_server

GOLD = """\
- source: stub-tender
  source_title: Tender Is the Night
  target: 23684
  target_title: Poems Published in 1820
  target_part: Ode to a Nightingale
  type: title-source
  evidence: "tender is the night"
  basis: title is a line of the ode
  certainty: high
- source: 1321
  source_title: The Waste Land
  target: 1122
  target_title: Hamlet
  type: quotation
  evidence: "Good night, ladies"
  basis: Eliot's own note
  certainty: high
- source: 4300
  source_title: Ulysses
  target: 147
  target_title: Common Sense
  type: allusion
  evidence: none; this entry exists to be missed
  basis: test
  certainty: high
- source: 15
  source_title: Moby-Dick
  target: 10
  target_title: King James Bible
  type: allusion
  evidence: neither work is in the corpus
  basis: test
  certainty: high
"""


def test_evaluate_reports_which_gold_links_were_found(seeded, capsys):
    gold = seeded.tmp / "gold.yaml"
    gold.write_text(GOLD, encoding="utf-8")
    seeded.run("detect")
    capsys.readouterr()

    seeded.run("evaluate", gold, "--json")
    report = json.loads(capsys.readouterr().out)

    assert report["total"] == 3, "the entry whose works are not in the corpus is not counted"
    assert report["found"] == 2
    assert [m["source_title"] for m in report["missing"]] == ["Ulysses"]
    assert report["skipped"] == 1
    assert report["by_detector"]["quotation"]["found"] == 1


@pytest.fixture
def server(seeded):
    seeded.run("detect")
    seeded.run("judge")
    httpd = make_server(str(seeded.data), port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def get_graph(base):
    with urllib.request.urlopen(base + "/graph.json") as response:
        return json.loads(response.read())


def post_review(base, payload):
    request = urllib.request.Request(
        base + "/api/review",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return response.status


def find(graph, source_title, target_title):
    titles = {w["id"]: w["title"] for w in graph["works"]}
    return [
        l for l in graph["links"]
        if titles[l["source"]] == source_title and titles[l["target"]] == target_title
    ]


def test_a_review_posted_to_the_server_shows_in_the_served_graph_and_the_export(seeded, server):
    link = find(get_graph(server), "Infinite Jest", "Hamlet")[0]

    status = post_review(server, {"link_id": link["id"], "verdict": "reject", "note": "from the viewer"})

    assert status == 200
    served = find(get_graph(server), "Infinite Jest", "Hamlet")[0]
    assert served["status"] == "rejected" and served["reviewed"] is True
    assert seeded.export().one("Infinite Jest", "Hamlet")["status"] == "rejected"


def test_a_review_for_an_unknown_link_is_refused(server):
    with pytest.raises(urllib.error.HTTPError) as error:
        post_review(server, {"link_id": 987654, "verdict": "accept"})

    assert error.value.code == 404


def test_served_graph_says_it_accepts_reviews(server):
    assert get_graph(server)["reviewable"] is True


def test_term_lookup_names_the_works_that_use_a_word(server):
    graph = get_graph(server)
    titles = {w["id"]: w["title"] for w in graph["works"]}

    with urllib.request.urlopen(server + "/api/term?q=Parallax") as response:
        found = json.loads(response.read())

    assert [titles[w["id"]] for w in found["works"]] == ["Ulysses"]
    assert found["works"][0]["count"] == 2
