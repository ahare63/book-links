# Book Links Implementation Plan

**Goal:** Build a growing, reviewable graph of links between books (quotation, allusion, shared vocabulary, theme), each with evidence and a confidence level, shown in an interactive visual.

**Architecture:** A Python pipeline ingests books into SQLite, runs pluggable detectors that propose candidate links with evidence passages, and has a language model judge only those candidates. A static web viewer reads an exported JSON graph; run locally, the same viewer accepts human verdicts, which feed confidence and a regression set.

**Tech Stack:** Python 3.10+ with pytest, SQLite (standard library), scikit-learn (TF-IDF), the `claude` command-line tool in headless mode with Haiku as the judge, and sigma.js with graphology built with Vite. Ask the owner before installing anything.

---

## What the project is for

The owner wants to start as broad as possible and expects the matching criteria to change as results come in. Examples of links the finished system should show:

- Novels that use "parallax" and "metempsychosis" link to *Ulysses*.
- *Tender Is the Night* links to Keats's "Ode to a Nightingale" (the title is a line from the poem).
- *Infinite Jest* links to *Hamlet* (the title is from Yorick's speech).

Requirements agreed with the owner:

- Every link has a type, a direction, a confidence level and the evidence behind it.
- Books and references can be added continually, one at a time.
- Articles that explain themes or commonalities can be ingested; they add links and update the data that drives matching.
- A human reviews early results, starting with novels the owner knows well.
- The graph has an interesting interactive visual.

## Known limits (decided, not open)

- **Single rare words are weak evidence.** "Parallax" also appears in astronomy texts, and a book published before 1922 cannot allude to *Ulysses*. A lone shared rare word produces a low-confidence candidate at most. Knowledge that a term is a signature of a work comes from ingested articles and human review.
- **Articles update data, not code.** Ingesting an article changes signature terms, known links, and the examples shown to the judge. Detector code changes only by deliberate edits.
- **US Project Gutenberg stops at about 1930.** Later works enter as stubs or from other sources (see below).

## Sources of text

A work enters through one of four sources. The source is recorded on the work.

| Source | What it is | Notes |
|---|---|---|
| `gutenberg-us` | gutenberg.org | Default. Fetch by ebook ID from `https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt`, two seconds between requests, cached locally. The site forbids crawling; do not follow links or loop over ID ranges. Past about 1,000 books, switch to an rsync mirror (`gutenberg.pglaf.org::gutenberg`). |
| `gutenberg-au` | gutenberg.net.au | For works out of copyright in Australia but not on the US site. Fetch a single file by URL the owner supplies. Check per work that a text file is actually hosted; the Fitzgerald author page listed *Tender Is the Night* without a link on 2026-11-14. |
| `local-file` | A text file the owner supplies | Any text the owner already has. |
| `stub` | Title, author and year only | For works with no obtainable text. A stub can still receive links through its title, through mentions of it in other texts, and through articles. |

Rules that apply to every source:

- Full texts live in `data/`, which is git-ignored. The repository is public; never commit a book's text.
- The exported graph contains only short evidence quotes (a few lines per link), never whole passages or chapters.
- Works from `gutenberg-au` and `local-file` may be under US copyright. The owner decides per work whether to add them; the pipeline never fetches them unprompted.

## Seed corpus

About 50 works the owner has read and that are on gutenberg.org, matched from the owner's reading list on 2026-11-14 (IDs are gutenberg.org ebook numbers):

15 Moby-Dick · 20 Paradise Lost · 61 The Communist Manifesto · 84 Frankenstein · 135 Les Misérables · 140 The Jungle · 145 Middlemarch · 147 Common Sense · 150 The Republic · 174 The Picture of Dorian Gray · 175 The Phantom of the Opera · 209 The Turn of the Screw · 228 The Aeneid · 768 Wuthering Heights · 805 This Side of Paradise · 1122 Hamlet · 1232 The Prince · 1260 Jane Eyre · 1280 Spoon River Anthology · 1321 The Waste Land · 1342 Pride and Prejudice · 1533 Macbeth · 1600 Symposium · 1845 Zuleika Dobson · 2199 The Iliad · 2527 The Sorrows of Young Werther · 2680 Meditations · 2814 Dubliners · 3160 The Odyssey · 4217 A Portrait of the Artist as a Young Man · 4300 Ulysses · 4584 Mont-Saint-Michel and Chartres · 7142 History of the Peloponnesian War · 7178 Swann's Way · 8129 A Dreamer's Tales · 8800 The Divine Comedy · 11231 Bartleby · 14460 Faust · 35330 The Spanish Tragedy · 52617 The Decameron · 60962 The Vegetable · 64317 The Great Gatsby · 66057 The Tale of Genji · 67098 Winnie-the-Pooh · 67138 The Sun Also Rises · 71865 Mrs Dalloway · 73011 The House at Pooh Corner · 75011 All Quiet on the Western Front · 75170 The Sound and the Fury · 77600 The Maltese Falcon · 78221 Civilization and Its Discontents

Added as allusion targets: 10 King James Bible · 100 Complete Works of Shakespeare · 23684 Keats, Poems Published in 1820. Verify these three IDs against `pg_catalog.csv` before fetching.

Stubs to add at the start: *Tender Is the Night* (Fitzgerald, 1934) and *Infinite Jest* (Wallace, 1996).

Poem nodes to declare at the start: "Ode to a Nightingale" inside 23684.

The match was by exact title and author surname, so it undercounts. Widening the seed set is a later step.

## Data model

One SQLite file, `data/book_links.db`.

- **works**: id, title, author, original publication year, source, source id or URL, kind (`full`, `stub`, or `subwork`), parent work id (for a subwork), and start and end positions in the parent text (for a subwork).
- **passages**: work id, sequence number, position in the text, text. Paragraph-sized.
- **links**: source work, target work, type, direction, confidence (0 to 1), status (`proposed`, `accepted`, `rejected`), detector name, detector version, rationale.
- **evidence**: link id, passage ids on each side, the short quotes.
- **reviews**: link id, verdict, corrected type if any, note, date.
- **articles**: citation, URL or file, date added.
- **signature_terms**: term, work id, weight, where it came from (article id or review id).

Link types to start with: `quotation`, `title-source`, `mention`, `allusion`, `shared-vocabulary`, `theme`. The list is expected to grow.

A subwork (a poem inside a collection) is declared by hand in `works/subworks.yaml` with its parent ID, title, and the first and last lines that bound it. Evidence that falls inside a subwork's range attaches the link to the subwork, not the parent.

Original publication years come from Wikidata, joined on property P2034 (Project Gutenberg ebook ID), taking P577. The Gutenberg catalog has only author life dates and the ebook release date.

## Testing Plan

- An integration test runs the whole pipeline on small real excerpts committed as fixtures: a stanza of "Ode to a Nightingale" containing "tender is the night", a *Ulysses* passage, the Yorick speech from *Hamlet*, and an unrelated control text. It asserts that the stub *Tender Is the Night* links to the Keats text with the matching line as evidence, that the stub *Infinite Jest* links to the *Hamlet* excerpt, and that the control text gets no link.
- Per-detector tests use the same fixtures: a known quotation is found, and a common phrase shared by two texts is not reported.
- A subwork test declares the ode as a subwork of a fixture collection and asserts the link lands on the ode.
- A direction test asserts that a link never claims a work alludes to one published after it.
- A confidence test checks that a rejected link never exports as confirmed, and that an accepted link outranks an unreviewed one.
- An article-ingestion test feeds a short saved article and asserts that its claimed link and terms show up in the next run's output. The model call is replaced at the command-line boundary with a recorded response; the assertions are on pipeline output.
- A slower acceptance check, run on demand, runs the real seed corpus against `gold/known_links.yaml` and reports recall and precision per detector. This is the measure for every later change to the criteria.

NOTE: I will write *all* tests before I add any implementation behavior.

## Tasks

Each task names the agent that can do it. "Main session" means the lead Claude Code session on the strongest model; the rest can be delegated to cheaper subagents. Pass the model explicitly when spawning. Tests for a task are written, and seen to fail, before its implementation.

| # | Task | Files | Depends on | Agent |
|---|---|---|---|---|
| 1 | Skeleton: package layout, `pyproject.toml`, pytest config, `.gitignore`, empty command-line entry point `book-links` | `pipeline/`, `tests/`, `pyproject.toml` | — | `general-purpose` on Haiku |
| 2 | Fixtures: the four excerpts above, trimmed from public-domain texts, plus a fixture collection containing the ode | `tests/fixtures/` | 1 | `general-purpose` on Haiku |
| 3 | Gold list: 30 to 40 well-known links among the seed works, each with a one-line source | `gold/known_links.yaml` | — | `general-purpose` on Sonnet, then owner review |
| 4 | Store: schema and read and write functions for the data model | `pipeline/store.py` | 1 | `general-purpose` on Sonnet |
| 5 | Ingest: `add-book`, `add-stub`, `add-file`, licence header and footer stripping, passage splitting, source adapters for the four sources | `pipeline/ingest.py`, `pipeline/sources/` | 4 | `general-purpose` on Sonnet |
| 6 | Subworks: read `works/subworks.yaml`, create subwork nodes, map passages to them | `pipeline/subworks.py` | 5 | `general-purpose` on Sonnet |
| 7 | Publication years from Wikidata | `pipeline/metadata.py` | 4 | `general-purpose` on Haiku |
| 8 | Detector interface and runner: a detector takes the store and returns candidates with evidence and a raw score; the runner records detector name and version | `pipeline/detectors/base.py`, `pipeline/run.py` | 4 | Main session |
| 9 | Detector: a work's title found inside another text | `pipeline/detectors/title_source.py` | 8 | `general-purpose` on Sonnet |
| 10 | Detector: shared word sequences (quotation), using a word five-gram index with common phrases filtered out | `pipeline/detectors/quotation.py` | 8 | `general-purpose` on Sonnet |
| 11 | Detector: mentions of another work's author, title or characters | `pipeline/detectors/mention.py` | 8 | `general-purpose` on Sonnet |
| 12 | Detector: clusters of distinctive shared vocabulary, with a floor on how many works use a term and a minimum cluster size | `pipeline/detectors/vocabulary.py` | 8 | `general-purpose` on Sonnet |
| 13 | Detector: signature terms from the `signature_terms` table | `pipeline/detectors/signature.py` | 8, 18 | `general-purpose` on Sonnet |
| 14 | Judge: prompt, call to `claude -p --model haiku`, parsing, cache keyed on the evidence, date veto on impossible directions | `pipeline/judge.py` | 8 | Main session |
| 15 | Confidence: combine detector score, judge score and reviews; recalibrate bands to measured precision per detector once enough reviews exist | `pipeline/confidence.py` | 14 | Main session |
| 16 | Export: write the graph JSON the viewer reads, with short quotes only | `pipeline/export.py` | 15 | `general-purpose` on Sonnet |
| 17 | Viewer: graph, filters, evidence panel, timeline layout, term lens (details below) | `viewer/` | 16 | Main session for design; `general-purpose` on Sonnet for components |
| 18 | Review loop: `book-links serve` runs the viewer locally with accept, reject and retype controls that write to `reviews` | `pipeline/serve.py`, `viewer/` | 17 | `general-purpose` on Sonnet |
| 19 | **Checkpoint: the owner reviews links on the seed corpus.** Nothing after this starts until the review is done | — | 18 | Owner |
| 20 | Articles: `add-article <url or file>` extracts claimed links, quotes and signature terms, stored with the citation | `pipeline/articles.py` | 14 | `general-purpose` on Sonnet; main session writes the extraction prompt |
| 21 | Themes: passage embeddings and theme labels. Scope is set from what the checkpoint shows the earlier detectors miss | `pipeline/detectors/theme.py` | 19 | Main session |
| 22 | Acceptance check against the gold list, with a per-detector report | `pipeline/evaluate.py` | 9–12, 3 | `general-purpose` on Sonnet |
| 23 | Code review of each merged group of tasks | — | each group | `nori-code-reviewer` |
| 24 | Documentation: README with setup, the commands, and how to add a book, a stub, a poem and an article | `README.md` | 18 | `nori-initial-documenter` |

Tasks 9 to 12 are independent of each other and can run in parallel, as can 2, 3 and 7.

### Viewer details (task 17)

- Force-directed graph. Node size by number of links, node colour by era.
- Edge colour by link type, thickness and opacity by confidence. Rejected links are hidden; proposed links are dashed.
- A confidence slider and link-type checkboxes.
- Clicking an edge opens both passages side by side with the rationale, detector and confidence.
- Clicking a node shows only that work and its neighbours.
- A timeline layout with publication year on the horizontal axis, so direction of influence is readable.
- A term lens: type a word and highlight every work that uses it.
- Subworks draw as small nodes attached to their parent.

## Edge cases

- Several editions or translations of one work on Gutenberg: keep one per work in the seed set; record the chosen ID.
- The Complete Shakespeare contains *Hamlet* and *Macbeth*, which are also separate seed works: exclude self-overlap between a collection and its separately held parts.
- Two works both quoting a third (usually the Bible): link each to the third, not to each other.
- Shared boilerplate, common idioms and stock phrases: filter by how many works contain the sequence.
- Titles that are common words or phrases ("Ulysses" inside a text about Homer's hero; "Common Sense"): the title detector needs the judge and a low prior for short titles.
- Translations: a translator's word choice is not the author's vocabulary. Record translation status on the work and down-weight vocabulary links for translated texts.
- Very long works dominate raw counts: normalise by length.
- Stubs have no text, so they can only be the source side of a title match or the target of a mention.
- Old Gutenberg files with non-standard header and footer wording: fall back to a looser pattern and report the work for a manual check.
- Missing Wikidata year: fall back to the author's death year as an upper bound and mark the year as approximate.

## Compatibility notes

- Every link stores the detector version that produced it. When a detector changes, re-run it and compare against the gold list and existing reviews before replacing old links.
- Human reviews are never deleted by a re-run. A review attaches to the pair of works and the link type, so it survives regenerated evidence.

**Testing Details** Tests run real excerpts through the public commands and assert on the links that come out (present, absent, attached to the right node, ordered by confidence), never on internal structures. The only replaced component is the model call, at the command-line boundary.

**Implementation Details**

- Every link keeps its evidence and the detector version that produced it.
- Detectors only propose; nothing reaches the graph as confirmed without the judge or the owner.
- Adding a work compares it against existing works only; nothing is recomputed for pairs already judged with the same detector versions.
- The judge runs through the `claude` command-line tool in headless mode, so it uses the owner's logged-in account and needs no API key. Check the tool's current flags before writing task 14.
- Measure judge usage on five works before running the full seed set.
- The quotation matcher is written here, not taken from a library: the existing tools are either Spark-based (passim) or unmaintained (text-matcher).
- The licence stripper is written here: the dedicated package was last released in 2019.
- Full texts stay in `data/` and are never committed; exports carry short quotes only.
- The viewer is a static site and can later be embedded elsewhere.
- Development machine is an Intel Mac with Python 3.10 and Node 20; check that any embedding library chosen in task 21 still ships Intel Mac builds.

**Question**

- Is the seed corpus right, including the Bible, Shakespeare and Keats additions and the two stubs?
- For `gutenberg-au` texts under US copyright, is the owner content to fetch them for local analysis, with only short quotes published?
- How many reviewed links should the checkpoint cover before confidence bands are recalibrated? The working assumption is at least 100.
- Should the public viewer be hosted (GitHub Pages) once the checkpoint passes, or stay local?

---
