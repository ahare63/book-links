"""What each detector proposes, seen through `detect` and the exported graph (no judge)."""

from conftest import quotes

PSALM = (
    "The lantern of the drowned sailor burns green beneath the harbour wall, "
    "and no fisherman of that coast will cast a net within sight of it."
)


def test_two_works_quoting_a_third_link_to_it_and_not_to_each_other(corpus):
    corpus.add_text(f"An old chronicle of the coast.\n\n{PSALM}\n\nSo the chronicle ends.", "Coast Chronicle", "Anon Monk", 1611)
    corpus.add_text(
        f"My grandmother had the saying by heart.\n\n{PSALM}\n\nShe would say it shelling peas.",
        "Shelling Peas", "First Borrower", 1850,
    )
    corpus.add_text(
        f"The pilot muttered something as we came in.\n\n{PSALM}\n\nThen he spat over the rail.",
        "Coming In", "Second Borrower", 1900,
    )
    corpus.run("detect")

    graph = corpus.export()

    first = graph.one("Shelling Peas", "Coast Chronicle", "quotation")
    assert "drowned sailor" in quotes(first, "source")
    assert "drowned sailor" in quotes(first, "target")
    graph.one("Coming In", "Coast Chronicle", "quotation")
    assert graph.between("Coming In", "Shelling Peas") == []
    assert graph.between("Shelling Peas", "Coming In") == []


def test_a_shared_run_of_function_words_is_not_a_quotation(corpus):
    corpus.add_text(
        "The harvest failed twice. And it was not as if he had been one of them at all. The barns stood empty.",
        "Barns", "Farm Writer", 1850,
    )
    corpus.add_text(
        "The regiment marched south. And it was not as if he had been one of them at all. Drums kept time.",
        "Drums", "War Writer", 1900,
    )
    corpus.run("detect")

    graph = corpus.export()

    assert graph.links == []


def test_an_author_repeating_their_own_passage_is_not_a_quotation(corpus):
    corpus.add_text(f"First printing.\n\n{PSALM}", "Collected Tales", "Same Hand", 1850)
    corpus.add_text(f"Second printing, revised.\n\n{PSALM}", "Selected Tales", "Same Hand", 1870)
    corpus.run("detect")

    graph = corpus.export()

    assert [l for l in graph.links if l["type"] == "quotation"] == []


def test_two_rare_shared_words_link_a_later_text_to_ulysses(corpus):
    corpus.add_fixture_works()
    corpus.add_text(
        "The lecturer spoke about parallax for an hour, and afterwards my sister asked "
        "whether metempsychosis was a thing one could catch from the cat.",
        "The Long Orbit", "Later Novelist", 1950,
    )
    corpus.run("detect")

    graph = corpus.export()

    link = graph.one("The Long Orbit", "Ulysses", "shared-vocabulary")
    assert "parallax" in quotes(link, "source") and "metempsychosis" in quotes(link, "source")
    assert "parallax" in quotes(link, "target") and "metempsychosis" in quotes(link, "target")


def test_one_rare_shared_word_alone_is_not_a_vocabulary_link(corpus):
    corpus.add_fixture_works()
    corpus.add_text(
        "The surveyor corrected for parallax and wrote the figure in his book before the light went.",
        "The Survey", "Field Writer", 1950,
    )
    corpus.run("detect")

    graph = corpus.export()

    assert graph.between("The Survey", "Ulysses") == []


def test_everyday_shared_words_are_not_a_vocabulary_link(corpus):
    corpus.add_fixture_works()
    corpus.run("detect")

    graph = corpus.export()

    assert [l for l in graph.links if l["type"] == "shared-vocabulary"] == []


def test_naming_an_author_and_their_book_is_a_mention(corpus):
    corpus.add_fixture_works()
    corpus.add_text(
        "All that winter I read Ulysses by the stove. James Joyce, I decided, had never been cold.",
        "A Winter Notebook", "Mary Reader", 1950,
    )
    corpus.run("detect")

    graph = corpus.export()

    link = graph.one("A Winter Notebook", "Ulysses", "mention")
    assert "ulysses" in quotes(link, "source")


def test_a_one_word_title_match_is_trusted_less_than_a_whole_phrase(seeded):
    # "hemlock" is in the ode ("as though of hemlock I had drunk"), as is "tender is the night".
    seeded.add_stub("Hemlock", "Some Novelist", 1990)
    seeded.run("detect")

    graph = seeded.export()

    phrase = graph.one("Tender Is the Night", "Poems Published in 1820", "title-source")
    word = graph.one("Hemlock", "Poems Published in 1820", "title-source")
    assert word["confidence"] < phrase["confidence"]
    assert phrase["status"] == "proposed" and word["status"] == "proposed"


def test_a_translation_cannot_be_quoted_before_it_was_made(corpus):
    # The English words of an ancient work are its translator's. A 1611 text that shares a
    # sentence with an 1871 translation did not take it from the ancient author, and the
    # ancient author did not take it from 1611.
    corpus.add_text(f"The dialogue opens.\n\n{PSALM}\n\nThe dialogue closes.", "Old Dialogue", "Ancient Sage", -400,
                    translation_year=1871)
    corpus.add_text(f"An old chronicle of the coast.\n\n{PSALM}\n\nSo the chronicle ends.", "Coast Chronicle", "Anon Monk", 1611)
    corpus.run("detect")

    graph = corpus.export()

    assert graph.links == []


def test_a_later_work_quoting_a_translation_links_to_the_translated_work(corpus):
    corpus.add_text(f"The dialogue opens.\n\n{PSALM}\n\nThe dialogue closes.", "Old Dialogue", "Ancient Sage", -400,
                    translation_year=1871)
    corpus.add_text(f"The pilot muttered something as we came in.\n\n{PSALM}\n\nThen he spat.", "Coming In", "Second Borrower", 1900)
    corpus.run("detect")

    graph = corpus.export()

    graph.one("Coming In", "Old Dialogue", "quotation")
    assert graph.work("Old Dialogue")["translated"] is True


def test_a_short_stock_phrase_is_not_a_quotation(corpus):
    corpus.add_text("The garrison held for a week and then fell into the hands of the enemy at dawn.", "Siege", "War Writer", 1850)
    corpus.add_text("Her letters, she feared, fell into the hands of the enemy she had made at court.", "Court", "Court Writer", 1900)
    corpus.run("detect")

    graph = corpus.export()

    assert graph.links == []


def test_matching_chapter_headings_are_not_a_quotation(corpus):
    contents = "CHAPTER I\nCHAPTER II\nCHAPTER III\nCHAPTER IV\nCHAPTER V\nCHAPTER VI\nCHAPTER VII\nCHAPTER VIII"
    corpus.add_text(f"{contents}\n\nThe harvest failed twice that decade.", "Barns", "Farm Writer", 1850)
    corpus.add_text(f"{contents}\n\nThe regiment marched south in the rain.", "Drums", "War Writer", 1900)
    corpus.run("detect")

    graph = corpus.export()

    assert graph.links == []
