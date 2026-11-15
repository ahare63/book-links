"""Theme labels from the model, and the theme links the next detection run builds from them."""

import sys
from pathlib import Path

import pytest

from conftest import quotes

FAKE_THEME_MODEL = Path(__file__).parent / "fake_theme_model.py"


@pytest.fixture
def themed(corpus, monkeypatch):
    monkeypatch.setenv("BOOK_LINKS_MODEL_CMD", f"{sys.executable} {FAKE_THEME_MODEL}")
    corpus.add_stub("The Sufferer", "Anonymous", -500)
    corpus.add_stub("The Wager", "Johann Wolfgang von Goethe", 1808)
    corpus.add_stub("The Doctor", "Some Novelist", 1900)
    return corpus


def calls(corpus):
    log = corpus.tmp / "model_calls.log"
    return log.read_text(encoding="utf-8").count("end of call") if log.exists() else 0


def test_works_sharing_specific_themes_are_linked_by_theme(themed):
    # The two works word the wager differently; the merge step finds they are the same theme.
    themed.run("themes")
    themed.run("detect")

    link = themed.export().one("The Wager", "The Sufferer", "theme")

    assert "a wager between god and the devil over a righteous man" in link["rationale"].lower()
    assert "mephistopheles" in quotes(link, "source")
    assert "satan wagers" in quotes(link, "target")


def test_one_shared_theme_is_not_enough(themed):
    themed.run("themes")
    themed.run("detect")

    graph = themed.export()

    assert graph.between("The Doctor", "The Sufferer") == []
    assert graph.between("The Doctor", "The Wager") == []


def test_an_earlier_work_is_never_said_to_share_a_later_works_theme_as_its_source(themed):
    themed.run("themes")
    themed.run("detect")

    assert themed.export().between("The Sufferer", "The Wager") == []


def test_themes_held_by_too_many_works_are_not_evidence(corpus, monkeypatch):
    monkeypatch.setenv("BOOK_LINKS_MODEL_CMD", f"{sys.executable} {FAKE_THEME_MODEL}")
    for n, title in enumerate(["Sea One", "Sea Two", "Sea Three", "Sea Four"]):
        corpus.add_stub(title, f"Author {n}", 1850 + n)
    corpus.run("themes")
    corpus.run("detect")

    assert [link for link in corpus.export().links if link["type"] == "theme"] == []


def test_labelling_again_asks_only_about_works_without_themes(themed):
    themed.run("themes")
    first = calls(themed)
    themed.run("themes")
    assert calls(themed) == first

    themed.add_stub("Sea One", "Author 0", 1850)
    themed.run("themes")

    prompts = (themed.tmp / "model_calls.log").read_text(encoding="utf-8").split("end of call")
    labelling = prompts[-3]
    assert '"Sea One"' in labelling and '"The Wager"' not in labelling
    assert "seduction and ruin" not in labelling.lower(), "labelling is not steered towards existing labels"
    assert "whaling" in prompts[-2], "the merge step sees every label, old and new"


def test_works_of_the_same_year_get_one_theme_link_not_two(corpus, monkeypatch):
    monkeypatch.setenv("BOOK_LINKS_MODEL_CMD", f"{sys.executable} {FAKE_THEME_MODEL}")
    corpus.add_stub("Twin One", "Author One", 1600)
    corpus.add_stub("Twin Two", "Author Two", 1600)
    corpus.run("themes")
    corpus.run("detect")

    graph = corpus.export()

    assert len(graph.between("Twin One", "Twin Two") + graph.between("Twin Two", "Twin One")) == 1


def test_a_reply_with_string_ids_and_bare_labels_is_still_stored(corpus, monkeypatch):
    monkeypatch.setenv("BOOK_LINKS_MODEL_CMD", f"{sys.executable} {FAKE_THEME_MODEL}")
    corpus.add_stub("Odd Reply", "Some Author", 1900)
    corpus.run("themes")
    first = calls(corpus)
    corpus.run("themes")

    assert calls(corpus) == first, "the work was labelled, so it is not asked about again"
