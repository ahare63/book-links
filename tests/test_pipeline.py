"""The whole pipeline on real excerpts: add works, detect, judge, export."""

from conftest import quotes


def run_all(corpus):
    corpus.run("detect")
    corpus.run("judge")
    return corpus.export()


def test_title_taken_from_a_poem_links_the_stub_to_the_poems_text(seeded):
    graph = run_all(seeded)

    link = graph.one("Tender Is the Night", "Poems Published in 1820", "title-source")
    assert "tender is the night" in quotes(link, "target")
    assert link["status"] == "accepted"


def test_infinite_jest_stub_links_to_hamlet(seeded):
    graph = run_all(seeded)

    link = graph.one("Infinite Jest", "Hamlet", "title-source")
    assert "infinite jest" in quotes(link, "target")


def test_a_line_quoted_from_hamlet_links_the_waste_land_to_it(seeded):
    graph = run_all(seeded)

    link = graph.one("The Waste Land", "Hamlet", "quotation")
    assert "sweet ladies" in quotes(link, "source")
    assert "sweet ladies" in quotes(link, "target")


def test_unrelated_text_gets_no_links(seeded):
    graph = run_all(seeded)

    assert graph.touching("Common Sense") == []


def test_licence_boilerplate_never_counts_as_book_text(seeded):
    # Every fixture's Gutenberg footer contains "Updated editions will replace the previous one".
    seeded.add_stub("The Previous One", "Nobody", 2001)
    seeded.add_stub("Project Gutenberg", "Nobody", 2002)

    graph = run_all(seeded)

    assert graph.touching("The Previous One") == []
    assert graph.touching("Project Gutenberg") == []


def test_header_without_spaces_around_the_marker_is_still_stripped(corpus):
    corpus.add_text(
        "Produced by volunteers of the Lantern Fish Society.\n\n"
        "***START OF THE PROJECT GUTENBERG EBOOK AN OLD FILE***\n\n"
        "The river ran slowly past the mill and the miller slept.\n\n"
        "***END OF THE PROJECT GUTENBERG EBOOK AN OLD FILE***\n\n"
        "Donations to the Lantern Fish Society are welcome.\n",
        "An Old File", "Old Author", 1850,
    )
    corpus.add_stub("Lantern Fish Society", "Nobody", 2001)
    corpus.add_stub("The Miller Slept", "Nobody", 2002)
    corpus.run("detect")

    graph = corpus.export()

    assert graph.touching("Lantern Fish Society") == []
    assert len(graph.between("The Miller Slept", "An Old File")) == 1


def test_exported_quotes_are_short(seeded):
    graph = run_all(seeded)

    assert graph.links, "expected some links to check"
    for link in graph.links:
        for evidence in link["evidence"]:
            for side in ("source_quote", "target_quote"):
                assert len(evidence.get(side) or "") <= 400


def test_adding_the_same_work_twice_keeps_one_node(seeded):
    seeded.add_fixture_works()
    seeded.add_stub("Infinite Jest", "David Foster Wallace", 1996)

    graph = seeded.export()

    assert len(graph.works) == 7


def test_no_link_claims_a_work_draws_on_a_later_one(seeded):
    seeded.add_text(
        "All that winter I read Ulysses by the stove, and when the snow went I began it again.",
        "A Winter Notebook", "Mary Reader", 1950,
    )
    seeded.add_stub("The Glass Orchard", "Old Novelist", 1850)
    seeded.add_text(
        "My aunt kept a copy of The Glass Orchard on the shelf above the piano.",
        "Piano Lessons", "Later Writer", 1900,
    )

    graph = run_all(seeded)

    assert graph.links
    for link in graph.links:
        assert graph.year_of(link["source"]) >= graph.year_of(link["target"]), graph.describe()


def test_a_later_text_naming_an_earlier_title_is_a_mention_of_it(corpus):
    corpus.add_stub("The Glass Orchard", "Old Novelist", 1850)
    corpus.add_text(
        "My aunt kept a copy of The Glass Orchard on the shelf above the piano.",
        "Piano Lessons", "Later Writer", 1900,
    )
    corpus.run("detect")

    graph = corpus.export()

    link = graph.one("Piano Lessons", "The Glass Orchard", "mention")
    assert "the glass orchard" in quotes(link, "source")
    assert graph.between("The Glass Orchard", "Piano Lessons") == []
