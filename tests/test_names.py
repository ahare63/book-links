"""Allusions found through the names of an earlier work's people and places, or its author's name.
Names survive translation, so these links need no shared wording."""

from conftest import quotes

EPIC = """\
Arms and the man I sing. Aeneas fled the burning city with his father on his back.
The queen Dido welcomed Aeneas to Carthage and gave a feast for the Trojans.
Dido loved him, and when Aeneas sailed for Italy she climbed the pyre.
In Latium the prince Turnus stood against Aeneas, and Turnus fell at the last.
The Sibyl led Aeneas down to the dead, where Dido turned from him in silence.
The gods heard Turnus call on them, and the Sibyl's words came true for Dido and for Turnus.
"""

LATER_POEM = """\
Midway on the road I met a shade, who told me he had sung of Aeneas, the son of Anchises.
Among the lovers in the dark wind I saw Dido, who broke faith with the ashes of her husband.
And there was Camilla, who died for Italy, and the wounds of Turnus.
"""

ONE_NAME = """\
In the long winter evenings the children played at being Aeneas and Dido, and nobody minded the noise.
"""

NAMES_THE_POET = """\
He kept a copy of Virgil on the table by the stove and read a page of it every night.
On Sundays he read Virgil to the children.
"""

PLAIN_NAMES = """\
Hope came down the stairs and Grace met her in the hall. Hope was tired and Grace was not.
Hope opened the door. Grace closed it. Hope laughed at the dog, and Grace fed it.
"""

LATER_PLAIN = """\
Hope was the first to arrive, and Grace came soon after with the flowers for the table.
"""

SCRIPTURE = """\
Now the word came unto Jonah, saying, Arise, go to Nineveh, that great city.
But Jonah rose up to flee unto Tarshish, and went down to Joppa.
And Jonah was in the belly of the fish three days. Then Jonah went unto Nineveh.
So the people of Nineveh believed, and Jonah was displeased, and sat outside Nineveh.
The ship that went to Tarshish was broken, and the men of Tarshish feared exceedingly.
The words of the book of Ruth follow.
Naomi went with Ruth her daughter in law to Bethlehem, and Ruth gleaned in the field of Boaz.
And Boaz took Ruth, and Naomi nursed the child in Bethlehem, and Boaz was glad.
Naomi said unto Ruth, Blessed be Boaz, and Ruth went to Bethlehem with Naomi.
"""

BOOKS = """\
- parent: Scripture
  title: Jonah
  year: -400
  first_line: "Now the word came unto Jonah"
  last_line: "the men of Tarshish feared exceedingly"
- parent: Scripture
  title: Ruth
  year: -500
  first_line: "Naomi went with Ruth"
  last_line: "Ruth went to Bethlehem with Naomi"
"""

SERMON = """\
The preacher took for his text the story of Jonah, who would not go to Nineveh but ran for Tarshish.
"""


def add_epic(corpus):
    corpus.add_text(EPIC, "The Epic", "Virgil", -19, translation_year=1697)


def test_a_later_work_naming_an_earlier_works_people_alludes_to_it(corpus):
    add_epic(corpus)
    corpus.add_text(LATER_POEM, "The Journey", "Dante Alighieri", 1320, translation_year=1814)
    corpus.run("detect")

    link = corpus.export().one("The Journey", "The Epic", "allusion")

    assert "aeneas" in quotes(link, "source") and "dido" in quotes(link, "source")
    assert "aeneas" in quotes(link, "target")
    assert "Aeneas" in link["rationale"] and "Dido" in link["rationale"]


def test_the_original_year_decides_direction_not_the_translation_year(corpus):
    # The translation (1697) is later than the alluding work (1320); the original (-19) is not.
    add_epic(corpus)
    corpus.add_text(LATER_POEM, "The Journey", "Dante Alighieri", 1320)
    corpus.run("detect")

    graph = corpus.export()

    graph.one("The Journey", "The Epic", "allusion")
    assert graph.between("The Epic", "The Journey") == []


def test_two_shared_names_are_not_enough(corpus):
    add_epic(corpus)
    corpus.add_text(ONE_NAME, "Winter Games", "Some Novelist", 1900)
    corpus.run("detect")

    assert corpus.export().touching("Winter Games") == []


def test_naming_the_author_is_enough(corpus):
    add_epic(corpus)
    corpus.add_text(NAMES_THE_POET, "The Stove", "Some Novelist", 1900)
    corpus.run("detect")

    link = corpus.export().one("The Stove", "The Epic", "allusion")

    assert "virgil" in quotes(link, "source")
    assert "Virgil" in link["rationale"]


def test_names_that_are_common_words_are_not_evidence(corpus):
    corpus.add_text(PLAIN_NAMES, "The House", "First Novelist", 1850)
    corpus.add_text(LATER_PLAIN, "The Party", "Second Novelist", 1900)
    corpus.run("detect")

    assert corpus.export().between("The Party", "The House") == []


def test_the_same_author_is_not_said_to_allude_to_themself(corpus):
    add_epic(corpus)
    corpus.add_text(LATER_POEM, "The Georgics", "Virgil", 0)
    corpus.run("detect")

    assert corpus.export().between("The Georgics", "The Epic") == []


def test_names_inside_a_book_of_a_collection_link_to_that_book(corpus):
    paragraphs = "\n\n".join(SCRIPTURE.splitlines())  # passages are paragraphs, so each verse is its own
    corpus.add_text(paragraphs, "Scripture", "Various", -500, translation_year=1611)
    path = corpus.tmp / "books.yaml"
    path.write_text(BOOKS, encoding="utf-8")
    corpus.run("add-subworks", path)
    corpus.add_text(SERMON, "The Whale", "Herman Melville", 1851)
    corpus.run("detect")

    graph = corpus.export()

    link = graph.one("The Whale", "Jonah", "allusion")
    assert "nineveh" in quotes(link, "target")
    assert graph.between("The Whale", "Ruth") == []
    assert graph.between("The Whale", "Scripture") == []


def test_a_name_shared_by_two_books_of_a_collection_counts_for_both(corpus):
    travels = (
        "And Ruth went to Nineveh and Tarshish, and by way of Nineveh and Tarshish back to Nineveh and Tarshish.\n"
    )
    scripture = SCRIPTURE.replace("Naomi said unto Ruth", travels + "Naomi said unto Ruth")
    corpus.add_text("\n\n".join(scripture.splitlines()), "Scripture", "Various", -500, translation_year=1611)
    path = corpus.tmp / "books.yaml"
    path.write_text(BOOKS.replace("year: -500", "year: -900"), encoding="utf-8")
    corpus.run("add-subworks", path)
    corpus.add_text(SERMON, "The Whale", "Herman Melville", 1851)
    corpus.run("detect")

    graph = corpus.export()

    graph.one("The Whale", "Jonah", "allusion")


NOVEL = """\
They called on Mr. Darcy at Pemberley, and Mr. Darcy was not at home.
“We shall go,” Elizabeth said, and Mrs. Bennet sent a note to Pemberley.
At dinner Mr. Darcy spoke of Pemberley to Mrs. Bennet, and “Yes,” Elizabeth replied, and Mrs. Bennet smiled.
In the morning “Lizzy,” Elizabeth heard, and left.
"""

PARODY = """\
The new tenant compared himself to Mr. Darcy, his house to Pemberley, and his landlady to Mrs. Bennet.
"""


def test_names_after_a_title_or_a_closing_quote_count(corpus):
    corpus.add_text(NOVEL, "The Novel", "Jane Austen", 1813)
    corpus.add_text(PARODY, "The Parody", "Some Novelist", 1900)
    corpus.run("detect")

    link = corpus.export().one("The Parody", "The Novel", "allusion")

    assert "Darcy" in link["rationale"] and "Bennet" in link["rationale"]


EXODUS_BOOKS = "\n\n".join(
    f"The book of {book}.\n\nAnd Pharaoh sent to Goshen, and Pharaoh spoke of Midian, and from Goshen to Midian "
    f"went Pharaoh, and Goshen and Midian were glad in {book}."
    for book in ["Exodus", "Numbers", "Deuteronomy", "Joshua"]
)

EXODUS_DECLARATIONS = "\n".join(
    f"""- parent: Law
  title: {book}
  year: -500
  first_line: "The book of {book}."
  last_line: "were glad in {book}."
"""
    for book in ["Exodus", "Numbers", "Deuteronomy", "Joshua"]
)


def test_names_used_across_many_books_of_one_collection_still_count(corpus):
    corpus.add_text(EXODUS_BOOKS, "Law", "Various", -500, translation_year=1611)
    path = corpus.tmp / "law.yaml"
    path.write_text(EXODUS_DECLARATIONS, encoding="utf-8")
    corpus.run("add-subworks", path)
    corpus.add_text("The daughter of Pharaoh lived in Goshen and dreamed of Midian.", "Exile", "Some Novelist", 1900)
    corpus.run("detect")

    graph = corpus.export()

    assert [link for link in graph.touching("Exile") if link["type"] == "allusion"]


def test_the_names_shown_first_are_the_ones_the_earlier_work_uses_most(corpus):
    hero = " ".join(["Then Zephon spoke, and Zephon went on."] * 6)
    corpus.add_text(
        hero + " The guards saw Abaris, Abaris and Abaris. The ship sailed by Corcyra, Corcyra and Corcyra.",
        "The Old Epic",
        "Old Poet",
        -700,
    )
    corpus.add_text("He spoke of Abaris, of Corcyra and of Zephon.", "The New Poem", "New Poet", 1800)
    corpus.run("detect")

    link = corpus.export().one("The New Poem", "The Old Epic", "allusion")

    assert link["rationale"].index("Zephon") < link["rationale"].index("Abaris")
