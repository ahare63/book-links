"""How the judge's verdicts and the owner's reviews show up in the exported graph."""

import sqlite3
import sys
from collections import Counter

from conftest import FAKE_JUDGE
from test_names import LATER_POEM, add_epic


def calls(corpus):
    log = corpus.tmp / "model_calls.log"
    return len(log.read_text().splitlines()) if log.exists() else 0


def detect_and_judge(corpus):
    corpus.run("detect")
    corpus.run("judge")
    return corpus.export()


def test_judge_rejects_a_coincidental_word_match(seeded):
    seeded.add_stub("Hemlock", "Some Novelist", 1990)

    graph = detect_and_judge(seeded)

    link = graph.one("Hemlock", "Poems Published in 1820", "title-source")
    assert link["status"] == "rejected"
    assert link["rationale"]


def test_judged_accept_ranks_above_the_same_link_before_judging(seeded):
    seeded.run("detect")
    before = seeded.export().one("Infinite Jest", "Hamlet", "title-source")
    seeded.run("judge")
    after = seeded.export().one("Infinite Jest", "Hamlet", "title-source")

    assert before["status"] == "proposed" and after["status"] == "accepted"
    assert after["confidence"] > before["confidence"]


def test_judging_twice_does_not_ask_the_model_again(seeded):
    seeded.run("detect")
    seeded.run("judge")
    first = calls(seeded)
    seeded.run("detect")
    seeded.run("judge")

    assert first > 0
    assert calls(seeded) == first


def test_adding_a_work_only_judges_the_new_candidates(seeded):
    detect_and_judge(seeded)
    before = calls(seeded)
    seeded.add_stub("Season of Mists", "Some Novelist", 1950)
    detect_and_judge(seeded)

    assert calls(seeded) == before + 1


def test_unusable_model_output_leaves_links_proposed(seeded, monkeypatch):
    monkeypatch.setenv("BOOK_LINKS_MODEL_CMD", f"{sys.executable} -c \"print('I cannot help with that.')\"")
    seeded.run("detect")

    code = seeded.run("judge", ok=False)

    assert code != 0
    assert {link["status"] for link in seeded.export().links} == {"proposed"}


def with_named_models(corpus, monkeypatch):
    """Point the judge at the fake, passing it the model each link is sent to."""
    monkeypatch.setenv("BOOK_LINKS_MODEL_CMD", f"{sys.executable} {FAKE_JUDGE} --model {{model}}")
    add_epic(corpus)
    corpus.add_text(LATER_POEM, "The Journey", "Dante Alighieri", 1320, translation_year=1814)


def models_asked(corpus):
    return Counter(line.removeprefix("call ") for line in (corpus.tmp / "model_calls.log").read_text().splitlines())


def test_name_based_links_go_to_the_stronger_model_and_the_rest_to_the_cheaper(seeded, monkeypatch):
    with_named_models(seeded, monkeypatch)
    seeded.run("detect")
    links = seeded.export().links
    names = sum(link["detector"] == "names" for link in links)
    assert names, "the epic and the poem give a name-based link"

    seeded.run("judge")

    assert models_asked(seeded) == {"sonnet": names, "haiku": len(links) - names}


def test_name_based_links_judged_before_the_model_was_recorded_are_asked_again(seeded, monkeypatch):
    with_named_models(seeded, monkeypatch)
    seeded.run("detect")
    seeded.run("judge")
    before = models_asked(seeded)
    names = sum(link["detector"] == "names" for link in seeded.export().links)
    # A database from before verdicts recorded their model: every verdict there came from Haiku.
    with sqlite3.connect(seeded.data / "book_links.db") as conn:
        conn.executescript(
            "CREATE TABLE old AS SELECT evidence_key, verdict, confidence, rationale FROM judgements;"
            "DROP TABLE judgements; ALTER TABLE old RENAME TO judgements;"
        )

    seeded.run("judge")
    seeded.run("judge")

    assert names
    assert models_asked(seeded) - before == {"sonnet": names}, "only the name-based links, once"


def test_owner_rejection_overrides_the_judge_and_survives_a_rerun(seeded):
    graph = detect_and_judge(seeded)
    link = graph.one("Tender Is the Night", "Poems Published in 1820", "title-source")
    assert link["status"] == "accepted"

    seeded.run("review", link["id"], "--verdict", "reject", "--note", "testing")
    assert seeded.export().one("Tender Is the Night", "Poems Published in 1820")["status"] == "rejected"

    again = detect_and_judge(seeded).one("Tender Is the Night", "Poems Published in 1820")
    assert again["status"] == "rejected"
    assert again["reviewed"] is True


def test_owner_accepted_link_outranks_every_unreviewed_link(seeded):
    graph = detect_and_judge(seeded)
    link = graph.one("The Waste Land", "Hamlet", "quotation")

    seeded.run("review", link["id"], "--verdict", "accept")
    graph = seeded.export()

    accepted = graph.one("The Waste Land", "Hamlet", "quotation")
    assert accepted["status"] == "accepted" and accepted["reviewed"] is True
    others = [link for link in graph.links if not link["reviewed"]]
    assert others
    assert all(accepted["confidence"] > other["confidence"] for other in others)


def test_owner_can_accept_a_link_the_judge_rejected(seeded):
    seeded.add_stub("Hemlock", "Some Novelist", 1990)
    link = detect_and_judge(seeded).one("Hemlock", "Poems Published in 1820")

    seeded.run("review", link["id"], "--verdict", "accept")

    assert seeded.export().one("Hemlock", "Poems Published in 1820")["status"] == "accepted"


def test_owner_can_correct_the_link_type(seeded):
    link = detect_and_judge(seeded).one("Infinite Jest", "Hamlet", "title-source")

    seeded.run("review", link["id"], "--verdict", "accept", "--type", "allusion")
    graph = detect_and_judge(seeded)

    graph.one("Infinite Jest", "Hamlet", "allusion")
    assert graph.between("Infinite Jest", "Hamlet", "title-source") == []
