"""Poems declared inside a collection become their own nodes and receive the links."""

from conftest import quotes

SUBWORKS = """\
- parent: Poems Published in 1820
  title: Ode to a Nightingale
  year: 1819
  first_line: "My heart aches, and a drowsy numbness pains"
  last_line: "Fled is that music:--Do I wake or sleep?"
"""


def declare(corpus):
    path = corpus.tmp / "subworks.yaml"
    path.write_text(SUBWORKS, encoding="utf-8")
    corpus.run("add-subworks", path)


def test_link_lands_on_the_poem_not_the_collection(seeded):
    declare(seeded)
    seeded.run("detect")

    graph = seeded.export()

    link = graph.one("Tender Is the Night", "Ode to a Nightingale", "title-source")
    assert "tender is the night" in quotes(link, "target")
    assert graph.between("Tender Is the Night", "Poems Published in 1820") == []


def test_poem_node_belongs_to_its_collection(seeded):
    declare(seeded)

    graph = seeded.export()

    ode = graph.work("Ode to a Nightingale")
    assert ode["kind"] == "subwork"
    assert ode["parent"] == graph.work("Poems Published in 1820")["id"]
    assert ode["author"] == "John Keats"
    assert ode["year"] == 1819


def test_evidence_outside_the_poem_stays_on_the_collection(seeded):
    # "Season of mists and mellow fruitfulness" opens "To Autumn", which is not declared.
    declare(seeded)
    seeded.add_stub("Season of Mists", "Some Novelist", 1950)
    seeded.run("detect")

    graph = seeded.export()

    graph.one("Season of Mists", "Poems Published in 1820", "title-source")
    assert graph.between("Season of Mists", "Ode to a Nightingale") == []


def test_declaring_a_poem_after_detection_moves_the_link_on_the_next_run(seeded):
    seeded.run("detect")
    declare(seeded)
    seeded.run("detect")

    graph = seeded.export()

    graph.one("Tender Is the Night", "Ode to a Nightingale", "title-source")
    assert graph.between("Tender Is the Night", "Poems Published in 1820") == []


def test_a_boundary_line_missing_from_the_parent_is_an_error(seeded):
    path = seeded.tmp / "bad.yaml"
    path.write_text(SUBWORKS.replace("My heart aches", "My heart breaks"), encoding="utf-8")

    code = seeded.run("add-subworks", path, ok=False)

    assert code != 0
    assert [w for w in seeded.export().works if w["kind"] == "subwork"] == []


def test_a_review_follows_its_link_onto_a_newly_declared_poem(seeded):
    seeded.run("detect")
    link = seeded.export().one("Tender Is the Night", "Poems Published in 1820", "title-source")
    seeded.run("review", link["id"], "--verdict", "accept", "--note", "Keats")

    declare(seeded)
    seeded.run("detect")

    moved = seeded.export().one("Tender Is the Night", "Ode to a Nightingale", "title-source")
    assert moved["reviewed"] is True
    assert moved["status"] == "accepted"
    assert moved["note"] == "Keats"


def test_a_later_text_naming_a_poem_links_to_the_poem(seeded):
    declare(seeded)
    seeded.add_text(
        "She read the Ode to a Nightingale aloud twice, and then put the book down by the window.",
        "A Reader",
        "Later Novelist",
        1925,
    )
    seeded.run("detect")

    graph = seeded.export()

    link = graph.one("A Reader", "Ode to a Nightingale", "mention")
    assert "ode to a nightingale" in quotes(link, "source")
    assert graph.between("A Reader", "Poems Published in 1820") == []


def test_a_poem_is_never_said_to_name_its_own_collection(seeded):
    # A different author and a year no earlier than the collection's, so only the parent rule stops it.
    path = seeded.tmp / "subworks.yaml"
    path.write_text(SUBWORKS.replace("year: 1819", "year: 1820\n  author: Another Poet"), encoding="utf-8")
    seeded.run("add-subworks", path)
    seeded.run("detect")

    graph = seeded.export()

    assert graph.between("Poems Published in 1820", "Ode to a Nightingale") == []
    assert graph.between("Ode to a Nightingale", "Poems Published in 1820") == []


SCRIPTURE = """\
The words of the prophet.

Daniel was cast into the den of lions, and the lions did him no harm.

Daniel prayed three times a day, and the king feared the God of Daniel.

The end of the prophet.
"""

DANIEL = """\
- parent: Scripture
  title: Daniel
  year: -165
  first_line: "Daniel was cast into the den"
  last_line: "the king feared the God of Daniel"
"""


def add_scripture(corpus):
    corpus.add_text(SCRIPTURE, "Scripture", "Various", 110, translation_year=1611)
    path = corpus.tmp / "daniel.yaml"
    path.write_text(DANIEL, encoding="utf-8")
    corpus.run("add-subworks", path)


def test_a_one_word_book_title_used_as_a_name_is_not_a_mention(corpus):
    add_scripture(corpus)
    corpus.add_text("Daniel came home late and put the kettle on.", "Kettle", "Some Novelist", 1900)
    corpus.run("detect")

    assert corpus.export().between("Kettle", "Daniel", "mention") == []


def test_a_one_word_book_title_after_book_of_is_a_mention(corpus):
    add_scripture(corpus)
    corpus.add_text("He read the Book of Daniel by the fire.", "Fireside", "Some Novelist", 1900)
    corpus.run("detect")

    link = corpus.export().one("Fireside", "Daniel", "mention")
    assert "book of daniel" in quotes(link, "source")


def test_a_one_word_book_title_in_italics_is_a_mention(corpus):
    add_scripture(corpus)
    corpus.add_text("He read _Daniel_ by the fire.", "Fireside", "Some Novelist", 1900)
    corpus.run("detect")

    corpus.export().one("Fireside", "Daniel", "mention")


PLAYS = """The plays.

KING RICHARD. Now is the winter of our discontent made glorious summer by this sun of York.

The last words of the history.

PROSPERO. Our revels now are ended. These our actors were all spirits and are melted into air.

The last words of the romance.
"""

PLAY_DECLARATIONS = """- parent: The Plays
  title: Richard III
  year: 1593
  first_line: "Now is the winter of our discontent"
  last_line: "The last words of the history."
- parent: The Plays
  title: The Tempest
  year: 1611
  first_line: "Our revels now are ended"
  last_line: "The last words of the romance."
"""


def add_plays(corpus):
    corpus.add_text(PLAYS, "The Plays", "William Shakespeare", 1623)
    path = corpus.tmp / "plays.yaml"
    path.write_text(PLAY_DECLARATIONS, encoding="utf-8")
    corpus.run("add-subworks", path)


def test_a_play_named_for_a_king_is_not_mentioned_by_naming_the_king(corpus):
    add_plays(corpus)
    corpus.add_text("In the reign of Richard III the abbey was rebuilt.", "Abbeys", "Some Historian", 1900)
    corpus.run("detect")

    assert corpus.export().touching("Abbeys") == []


def test_a_play_named_for_a_king_is_mentioned_alongside_its_author(corpus):
    add_plays(corpus)
    corpus.add_text("We saw Shakespeare's Richard III at the Lyceum.", "Theatre Notes", "Some Critic", 1900)
    corpus.run("detect")

    corpus.export().one("Theatre Notes", "Richard III", "mention")


def test_a_storm_is_not_a_mention_of_the_tempest_and_the_tempest_takes_no_title_from_a_storm(corpus):
    add_plays(corpus)
    corpus.add_text("After the Tempest the ship lay still.", "Voyage", "Some Sailor", 1900)
    corpus.add_text("And there arose a great tempest in the sea.", "Old Book", "Various", 1500)
    corpus.run("detect")

    graph = corpus.export()

    assert graph.touching("Voyage") == []
    assert graph.touching("Old Book") == []
