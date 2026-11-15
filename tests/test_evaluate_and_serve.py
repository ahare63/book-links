"""The gold-list report, and the local review server the viewer talks to."""

import http.client
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
- source: 100
  source_title: Infinite Jest
  target: 100
  target_title: Complete Works of Shakespeare
  target_part: Hamlet
  type: title-source
  evidence: the collection is not in the corpus, but the play inside it is
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

    assert report["total"] == 4, "the entry whose works are not in the corpus is not counted"
    assert report["found"] == 3
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
        link
        for link in graph["links"]
        if titles[link["source"]] == source_title and titles[link["target"]] == target_title
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


def test_evaluate_does_not_count_a_link_the_judge_rejected(seeded, capsys):
    seeded.add_stub("Hemlock", "Some Novelist", 1990)
    gold = seeded.tmp / "gold.yaml"
    gold.write_text(
        "- source: x\n  source_title: Hemlock\n  target: y\n  target_title: Poems Published in 1820\n"
        "  type: title-source\n  evidence: none\n  basis: test\n  certainty: high\n",
        encoding="utf-8",
    )
    seeded.run("detect")
    seeded.run("judge")
    capsys.readouterr()

    seeded.run("evaluate", gold, "--json")
    report = json.loads(capsys.readouterr().out)

    assert report["found"] == 0


def raw_request(base, method, path, body=b"", headers=None):
    """Send a request with exactly these headers; returns the status code."""
    host, port = base.removeprefix("http://").split(":")
    connection = http.client.HTTPConnection(host, int(port))
    connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    for name, value in (headers or {}).items():
        connection.putheader(name, value)
    connection.endheaders(body)
    status = connection.getresponse().status
    connection.close()
    return status


def review_body(graph):
    link = find(graph, "Infinite Jest", "Hamlet")[0]
    return json.dumps({"link_id": link["id"], "verdict": "reject"}).encode()


def test_a_review_posted_without_a_json_content_type_is_refused(server):
    host = server.removeprefix("http://")
    body = review_body(get_graph(server))

    status = raw_request(
        server,
        "POST",
        "/api/review",
        body,
        {"Host": host, "Content-Type": "text/plain", "Content-Length": str(len(body))},
    )

    assert status == 403
    assert find(get_graph(server), "Infinite Jest", "Hamlet")[0]["reviewed"] is False


def test_a_request_for_another_host_name_is_refused(server):
    port = server.rsplit(":", 1)[1]
    body = review_body(get_graph(server))

    post = raw_request(
        server,
        "POST",
        "/api/review",
        body,
        {"Host": f"attacker.example:{port}", "Content-Type": "application/json", "Content-Length": str(len(body))},
    )
    get = raw_request(server, "GET", "/graph.json", headers={"Host": f"attacker.example:{port}"})

    assert (post, get) == (403, 403)
    assert find(get_graph(server), "Infinite Jest", "Hamlet")[0]["reviewed"] is False


def test_a_review_with_a_bad_length_is_refused(server):
    host = server.removeprefix("http://")

    status = raw_request(
        server, "POST", "/api/review", b"", {"Host": host, "Content-Type": "application/json", "Content-Length": "-1"}
    )

    assert status == 400


def test_static_files_outside_the_viewer_are_not_served(server):
    host = server.removeprefix("http://")

    statuses = {
        raw_request(server, "GET", path, headers={"Host": host})
        for path in ("/../pyproject.toml", "/%2e%2e/pyproject.toml", "/..%2fpyproject.toml", "/%00")
    }

    assert statuses == {404}
