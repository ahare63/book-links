"""Each quoted passage in the exported graph carries a citation: play, act and scene, or Bible chapter:verse."""

from conftest import quotes
from test_site import build, viewer_dist  # noqa: F401  (viewer_dist is a fixture)

PLAYS = """\
All the world's a stage, and all the men and women merely players, said the preface.

Hamlet Prince of Denmark

 Contents
 ACT I
 Scene I. Elsinore. A platform before the Castle
 ACT III
 Scene I. A room in the Castle

Dramatis Personae: Hamlet, Claudius, Gertrude and the ghost of Hamlet's father.

ACT I

SCENE I. Elsinore. A platform before the Castle.

BERNARDO. Who is there? Nay, answer me. Stand and unfold yourself.

ACT III.

SCENE I. A room in the Castle.

HAMLET. To be, or not to be, that is the question: whether 'tis nobler in the mind to suffer.

ACT IV

QUEEN. There is a willow grows aslant a brook, that shows his hoary leaves in the glassy stream.

THE END OF HAMLET

The Sonnets Begin

Shall I compare thee to a summer's day? Thou art more lovely and more temperate.

End of the Sonnets
"""

PLAY_DECLARATIONS = """\
- parent: The Plays
  title: Hamlet
  year: 1603
  first_line: "Hamlet Prince of Denmark"
  last_line: "THE END OF HAMLET"
- parent: The Plays
  title: The Sonnets
  year: 1609
  first_line: "The Sonnets Begin"
  last_line: "End of the Sonnets"
"""

NOVEL = """\
Someone said that to be, or not to be, that is the question: whether 'tis nobler in the mind to suffer.

Elsewhere there is a willow grows aslant a brook, that shows his hoary leaves in the glassy stream.

Shall I compare thee to a summer's day? Thou art more lovely and more temperate, he wrote.

All the world's a stage, and all the men and women merely players, she said.
"""

GOSPEL = """\
The Gospel.

Matthew

5:1 And seeing the multitudes, he went up into a mountain: and when he was set,
his disciples came unto him: 5:2 And he opened his mouth, and taught them, saying,
5:3 Blessed are the poor in spirit: for theirs is the kingdom of heaven.

End of Matthew
"""

GOSPEL_DECLARATION = """\
- parent: Scripture
  title: Matthew
  year: 80
  first_line: "Matthew"
  last_line: "End of Matthew"
"""

SERMON = "He preached that blessed are the poor in spirit: for theirs is the kingdom of heaven.\n"


def declare(corpus, name, text):
    path = corpus.tmp / name
    path.write_text(text, encoding="utf-8")
    corpus.run("add-subworks", path)


def labels(link, side):
    return [(e[f"{side}_locator"] or {}).get("label") for e in link["evidence"]]


def add_plays_and_novel(corpus):
    corpus.add_text(PLAYS, "The Plays", "William Shakespeare", 1623)
    declare(corpus, "plays.yaml", PLAY_DECLARATIONS)
    corpus.add_text(NOVEL, "Society Novel", "Some Novelist", 1900)
    corpus.run("detect")
    return corpus.export()


def test_a_quoted_play_is_cited_by_act_and_scene(corpus):
    graph = add_plays_and_novel(corpus)

    link = graph.one("Society Novel", "Hamlet", "quotation")

    assert sorted(labels(link, "target")) == ["Hamlet, Act 3, Scene 1", "Hamlet, Act 4"]
    hamlet = graph.work("Hamlet")["id"]
    assert {e["target_locator"]["work"] for e in link["evidence"]} == {hamlet}


def test_a_quoted_text_that_is_not_a_collection_has_no_locator(corpus):
    graph = add_plays_and_novel(corpus)

    link = graph.one("Society Novel", "Hamlet", "quotation")

    assert [e["source_locator"] for e in link["evidence"]] == [None, None]


def test_a_subwork_without_acts_is_cited_by_its_title(corpus):
    graph = add_plays_and_novel(corpus)

    link = graph.one("Society Novel", "The Sonnets", "quotation")

    assert labels(link, "target") == ["The Sonnets"]


def test_a_quote_outside_every_subwork_has_no_locator(corpus):
    graph = add_plays_and_novel(corpus)

    link = graph.one("Society Novel", "The Plays", "quotation")

    assert "stage" in quotes(link, "target")
    assert link["evidence"] and all(e["target_locator"] is None for e in link["evidence"])


def test_the_quoting_side_is_located_too(corpus):
    corpus.add_text(PLAYS, "The Plays", "William Shakespeare", 1623)
    declare(corpus, "plays.yaml", PLAY_DECLARATIONS)
    corpus.add_text(
        "An essay.\n\nEssay One\n\n" + NOVEL.split("\n\n")[0] + "\nEnd of Essay One\n",
        "Anthology",
        "Many Hands",
        1950,
    )
    declare(
        corpus,
        "anthology.yaml",
        '- parent: Anthology\n  title: Essay One\n  year: 1950\n  first_line: "Essay One"\n  last_line: "End of Essay One"\n',
    )
    corpus.run("detect")

    link = corpus.export().one("Essay One", "Hamlet", "quotation")

    assert labels(link, "source") == ["Essay One"]
    assert labels(link, "target") == ["Hamlet, Act 3, Scene 1"]


def test_a_quoted_bible_verse_is_cited_by_chapter_and_verse(corpus):
    corpus.add_text(GOSPEL, "Scripture", "Various", 100, translation_year=1611)
    declare(corpus, "gospel.yaml", GOSPEL_DECLARATION)
    corpus.add_text(SERMON, "Sermon", "Some Preacher", 1900)
    corpus.run("detect")

    link = corpus.export().one("Sermon", "Matthew", "quotation")

    assert labels(link, "target") == ["Matthew 5:3"]


def test_the_site_keeps_locators_when_it_withholds_a_quote(corpus, viewer_dist):  # noqa: F811
    corpus.add_text(PLAYS, "The Plays", "William Shakespeare", 1623)
    declare(corpus, "plays.yaml", PLAY_DECLARATIONS)
    corpus.add_text(NOVEL, "Society Novel", "Some Novelist", 1900)
    corpus.run("detect")

    graph = build(corpus, corpus.tmp / "site")

    hamlet = next(w["id"] for w in graph["works"] if w["title"] == "Hamlet")
    link = next(link for link in graph["links"] if link["type"] == "quotation" and link["target"] == hamlet)
    assert all(item["target_quote"] is None for item in link["evidence"]), "local-file texts are not quoted"
    assert sorted(labels(link, "target")) == ["Hamlet, Act 3, Scene 1", "Hamlet, Act 4"]
