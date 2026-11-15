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
