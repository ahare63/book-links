"""Ingesting an article adds its claimed links and changes what the next detection run finds."""

import sys

import pytest

from conftest import FAKE_ARTICLE_MODEL, FIXTURES, quotes

ARTICLE = FIXTURES / "article_ulysses.txt"


@pytest.fixture
def with_article_model(seeded, monkeypatch):
    monkeypatch.setenv("BOOK_LINKS_MODEL_CMD", f"{sys.executable} {FAKE_ARTICLE_MODEL}")
    return seeded


def add_survey(corpus):
    corpus.add_text(
        "The surveyor corrected for parallax and wrote the figure in his book before the light went.",
        "The Survey", "Field Writer", 1950,
    )


def test_a_link_claimed_by_the_article_appears_with_its_citation(with_article_model):
    corpus = with_article_model
    corpus.run("add-article", ARTICLE)

    graph = corpus.export()

    link = graph.one("Ulysses", "Hamlet", "allusion")
    assert "theory of hamlet" in link["rationale"].lower()
    assert "article_ulysses.txt" in link["article"]


def test_a_claim_about_a_work_not_in_the_corpus_is_left_out(with_article_model):
    corpus = with_article_model
    corpus.run("add-article", ARTICLE)

    graph = corpus.export()

    assert "A Book Nobody Added" not in [w["title"] for w in graph.works]


def test_signature_terms_from_the_article_make_one_word_enough(with_article_model):
    corpus = with_article_model
    add_survey(corpus)
    corpus.run("detect")
    assert corpus.export().between("The Survey", "Ulysses") == []

    corpus.run("add-article", ARTICLE)
    corpus.run("detect")
    graph = corpus.export()

    link = graph.one("The Survey", "Ulysses", "shared-vocabulary")
    assert "parallax" in quotes(link, "source")
    assert "parallax" in quotes(link, "target")


def test_signature_terms_never_link_an_earlier_work_to_a_later_one(with_article_model):
    corpus = with_article_model
    corpus.add_text(
        "The astronomer measured the parallax of the star over six months.",
        "Star Tables", "Victorian Astronomer", 1880,
    )
    corpus.run("add-article", ARTICLE)
    corpus.run("detect")

    graph = corpus.export()

    assert graph.touching("Star Tables") == []


def test_ingesting_the_same_article_twice_changes_nothing(with_article_model):
    corpus = with_article_model
    corpus.run("add-article", ARTICLE)
    once = corpus.export().describe()
    corpus.run("add-article", ARTICLE)

    assert corpus.export().describe() == once


def test_an_article_backing_a_detected_link_is_cited_on_it(with_article_model):
    corpus = with_article_model
    corpus.run("detect")
    corpus.run("add-article", ARTICLE)
    corpus.run("detect")

    link = corpus.export().one("The Waste Land", "Hamlet", "quotation")

    assert "article_ulysses.txt" in link["article"]
    assert "ophelia's farewell" in quotes(link, "source")
    assert "sweet ladies" in quotes(link, "source")
