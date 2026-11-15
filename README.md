# Book Links

A growing, reviewable graph of links between books: quotations, titles taken from earlier works,
mentions, and shared rare vocabulary. Every link has its evidence, a confidence from 0 to 1, and a
status (proposed, accepted or rejected).

Programs propose candidate links from the texts. A language model judges each candidate. You
review the results in a local viewer, and your verdicts outrank both.

The design and the task list are in [PLAN.md](PLAN.md).

## Setup

Requires Python 3.10 or later, Node 20 or later, and the `claude` command-line tool logged in
(used as the judge).

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd viewer && npm install && npm run build && cd ..
```

## Build the seed corpus

```sh
sh works/seed.sh                 # fetches about 55 texts, one every two seconds, into data/
.venv/bin/book-links detect      # propose candidate links (about a minute)
.venv/bin/book-links judge       # ask the model about each new candidate
.venv/bin/book-links serve       # open http://127.0.0.1:8765 to browse and review
```

`data/` holds the database and the full texts. It is git-ignored and must stay that way: some
texts are in copyright in the United States.

## Reviewing

In the viewer, click a link (in the graph or the list on the right) to see both passages side by
side with the reason it was proposed. Accept or reject it, correct its type if needed, and move to
the next unreviewed link. A review belongs to the pair of works and the link type, so it survives
later detection runs.

The same thing from the command line:

```sh
.venv/bin/book-links export graph.json
.venv/bin/book-links review 42 --verdict accept --type allusion --note "epigraph"
```

## Adding things

| To add | Command |
|---|---|
| A book on gutenberg.org | `book-links add-book 4300 --title "Ulysses" --author "James Joyce" --year 1922` |
| A translation | the same, plus `--translation-year 1898` (the year the translation was made) |
| A text from another site | `book-links add-url URL --title T --author A --year Y` |
| A text file you have | `book-links add-file PATH --title T --author A --year Y` |
| A book with no available text | `book-links add-stub --title "Infinite Jest" --author "David Foster Wallace" --year 1996` |
| A poem inside a collection | add an entry to `works/subworks.yaml`, then `book-links add-subworks` |
| An article about links or themes | `book-links add-article PATH_OR_URL` |

After adding anything, run `detect` and `judge` again. Only new candidates are sent to the model.

Give every work its original publication year (negative for BC). `--title` and `--author` are
optional for `add-book`, but Gutenberg's own titles often carry subtitles that stop title matching,
so short clean titles work better.

A stub has no text, so it can only be linked through its title (found in an earlier text), through
later texts that name it, and through articles.

An article adds the links it claims and the *signature terms* it names (for example "parallax" for
*Ulysses*). After that, a later book that uses a signature term gets a candidate link to that
work, even from a single word.

## How links are found

| Detector | Proposes | Link type |
|---|---|---|
| `title` | a work's title found in an earlier text | `title-source` |
| `mention` | a later text that names an earlier work, capitalised as a title | `mention` |
| `quotation` | a run of seven or more words shared with an earlier text by another author | `quotation` |
| `vocabulary` | two works sharing far more rare words than chance predicts | `shared-vocabulary` |
| `signature` | a later work using a term recorded as a signature of an earlier one | `shared-vocabulary` |
| `article` | a link claimed by an ingested article | any |

A link always runs from the later work to the earlier one it draws on. A link that would run
backwards in time is never stored. For a translation, the English wording dates from the
translation year, so text matches against it are dated accordingly.

Confidence: a candidate nobody has judged scores at most 0.5; one the model accepted scores between
0.5 and 0.9; one you accepted scores 0.95 or more; anything rejected scores near zero.

## Measuring changes

```sh
.venv/bin/python -m pytest -q                              # tests, on short excerpts in tests/fixtures
.venv/bin/book-links evaluate gold/known_links.yaml        # recall against known links
```

`gold/known_links.yaml` lists well-known links among the seed works. Run `evaluate` before and
after changing a detector. Each detector has a `version`; raise it when a change alters what the
detector proposes.

## The model

The judge and the article reader call the command in `BOOK_LINKS_MODEL_CMD`, which must read a
prompt on standard input and print a reply containing JSON. The default is headless `claude` on
Haiku with tools and settings turned off; it uses your logged-in Claude Code account, and calls
count against that plan's limits. Verdicts are cached, so a link is only judged again when its
evidence changes.

## Layout

```
pipeline/            the command-line tool
  detectors/         one file per detector
  sources/           fetching and licence stripping
viewer/              the graph viewer (sigma.js, built with Vite)
works/               the seed corpus script and the poem declarations
gold/                known links used to measure recall
tests/               tests and the excerpts they run on
data/                database and full texts (not in git)
```
