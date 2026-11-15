"""Adding works: local files, stubs, and single files fetched from Project Gutenberg sites."""

import hashlib
import os
import sys
from pathlib import Path

from pipeline.sources import http, strip

GUTENBERG_URL = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("add-file", help="add a work from a local text file")
    parser.add_argument("path")
    _describe(parser, required_year=True)
    parser.set_defaults(func=add_file)

    parser = commands.add_parser("add-stub", help="add a work that has no text")
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.set_defaults(func=add_stub)

    parser = commands.add_parser("add-book", help="add a work from gutenberg.org by ebook ID")
    parser.add_argument("id")
    parser.add_argument("--title")
    parser.add_argument("--author")
    parser.add_argument("--year", type=int)
    parser.add_argument("--translated", action="store_true")
    parser.set_defaults(func=add_book)

    parser = commands.add_parser("add-url", help="add a work from a single file on gutenberg.net.au")
    parser.add_argument("url")
    _describe(parser, required_year=True)
    parser.set_defaults(func=add_url)


def _describe(parser, required_year):
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--year", type=int, required=required_year)
    parser.add_argument("--translated", action="store_true")


def texts_dir(store):
    path = store.data_dir / "texts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def stripped_text(store, work_id):
    """The licence-stripped text of a full work, or None if it has none.

    Passage positions and subwork ranges are character offsets into this string.
    """
    path = texts_dir(store) / f"{work_id}.txt"
    if not path.exists():
        return None
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def add_file(store, args):
    try:
        raw = Path(args.path).read_bytes()
    except OSError as error:
        return _fail(f"cannot read {args.path}: {error.strerror}")
    _add_full(store, raw, args.title, args.author, args.year, "local-file", str(args.path), args.translated)


def add_stub(store, args):
    store.add_work(args.title, args.author, args.year, "stub", "stub")


def add_book(store, args):
    url = os.environ.get("BOOK_LINKS_GUTENBERG_URL", GUTENBERG_URL).replace("{id}", args.id)
    raw = _cached_download(store, f"gutenberg-us-{args.id}.txt", url)
    if isinstance(raw, int):
        return raw
    text = strip.normalise_newlines(strip.decode(raw))
    title = args.title or strip.header_field(text, "Title")
    author = args.author or strip.header_field(text, "Author")
    if not title or not author:
        return _fail(f"ebook {args.id}: no Title or Author line in the header; pass --title and --author")
    _add_full(store, raw, title, author, args.year, "gutenberg-us", args.id, args.translated)


def add_url(store, args):
    name = "gutenberg-au-" + hashlib.sha1(args.url.encode("utf-8")).hexdigest()[:16] + ".txt"
    raw = _cached_download(store, name, args.url)
    if isinstance(raw, int):
        return raw
    _add_full(store, raw, args.title, args.author, args.year, "gutenberg-au", args.url, args.translated)


def _cached_download(store, name, url):
    """The raw bytes of ``url``, from ``texts/<name>`` if already downloaded; an exit code on failure."""
    path = texts_dir(store) / name
    if path.exists():
        return path.read_bytes()
    try:
        raw = http.fetch(url)
    except http.FetchError as error:
        return _fail(str(error))
    path.write_bytes(raw)
    return raw


def _add_full(store, raw, title, author, year, source, source_ref, translated):
    text = strip.normalise_newlines(strip.decode(raw))
    body, problem = strip.strip_licence(text)
    if problem:
        print(f"warning: {title}: {problem}; check the text by hand", file=sys.stderr)
    work_id = store.add_work(title, author, year, source, "full", source_ref=source_ref, translated=translated)
    with open(texts_dir(store) / f"{work_id}.txt", "w", encoding="utf-8", newline="") as handle:
        handle.write(body)
    store.set_passages(work_id, strip.split_passages(body))


def _fail(message):
    print(f"error: {message}", file=sys.stderr)
    return 1
