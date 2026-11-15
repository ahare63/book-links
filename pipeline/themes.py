"""Label works with themes by asking the model, then merge labels that word the same theme differently.

The labels come from the model's knowledge of each work, not from its text, so a theme link says
so in its rationale. Each work is labelled on its own terms; showing the model the labels already in
use made it force them onto works they did not fit.
"""

import os
import sys

from pipeline.model import DEFAULT_COMMAND, ModelError, ask_json

BATCH = 10

LABEL_PROMPT = """\
For each work below, list 3 to 5 of its themes. Make each theme specific enough to tell works
apart: "a wager between God and the devil over a righteous man" or "revenge commanded by a
father's ghost", not "love", "death" or "identity". Keep each under ten words, and list only
themes the work is known for.

For each theme add a note: one sentence on how this work treats it.

Works:
{works}

Reply with one JSON object and nothing else:
{{"works": [{{"id": the work's number, "themes": [{{"theme": "...", "note": "..."}}]}}]}}
"""

MERGE_PROMPT = """\
Below are theme labels written for different literary works. Group labels that state the same
theme in different words, so that a scholar would call them one theme. Do not group labels that
are only related or that share a broad subject; most labels belong in no group. For each group,
give the clearest label as "theme" and list every label in it exactly as written.

Labels:
{labels}

Reply with one JSON object and nothing else:
{{"groups": [{{"theme": "...", "labels": ["...", "..."]}}]}}
"""


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("themes", help="label works that have no themes yet, using the model")
    parser.set_defaults(func=label_themes)


def label_themes(store, args):
    model = os.environ.get("BOOK_LINKS_MODEL_CMD", DEFAULT_COMMAND)
    labelled = {row[0] for row in store.conn.execute("SELECT DISTINCT work_id FROM themes")}
    pending = [w for w in store.works() if w["id"] not in labelled]
    if not pending:
        return 0
    done = 0
    for start in range(0, len(pending), BATCH):
        batch = pending[start : start + BATCH]
        try:
            reply = ask_json(_label_prompt(store, batch), "works")
        except ModelError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        done += _store_labels(store, batch, reply, model)
        store.conn.commit()
        print(f"labelled {done} of {len(pending)} works")
    try:
        merged = _merge(store)
    except ModelError as error:
        print(f"error while merging labels: {error}", file=sys.stderr)
        return 1
    print(f"merged {merged} labels into other wordings of the same theme")
    return 0


def _store_labels(store, batch, reply, model):
    known = {w["id"] for w in batch}
    stored = 0
    for item in reply.get("works") or []:
        if not isinstance(item, dict):
            continue
        try:
            work_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if work_id not in known:
            continue
        rows = 0
        for theme in item.get("themes") or []:
            label, note = (theme.get("theme"), theme.get("note", "")) if isinstance(theme, dict) else (theme, "")
            label = " ".join(str(label or "").split()).lower()
            if label:
                store.conn.execute(
                    "INSERT OR IGNORE INTO themes (work_id, theme, note, model) VALUES (?, ?, ?, ?)",
                    (work_id, label, str(note or "").strip(), model),
                )
                rows += 1
        stored += 1 if rows else 0
    return stored


def _merge(store):
    labels = [row[0] for row in store.conn.execute("SELECT DISTINCT theme FROM themes ORDER BY theme")]
    reply = ask_json(MERGE_PROMPT.format(labels="\n".join(f"- {label}" for label in labels)), "groups")
    known = set(labels)
    store.conn.execute("UPDATE themes SET canonical = NULL")
    merged = 0
    for group in reply.get("groups") or []:
        if not isinstance(group, dict):
            continue
        members = [" ".join(str(m).split()).lower() for m in group.get("labels") or []]
        members = [m for m in members if m in known]
        if len(members) < 2:
            continue
        canonical = " ".join(str(group.get("theme") or members[0]).split()).lower()
        for member in members:
            if member != canonical:
                merged += store.conn.execute(
                    "UPDATE themes SET canonical = ? WHERE theme = ?", (canonical, member)
                ).rowcount
    store.conn.commit()
    return merged


def _label_prompt(store, batch):
    works = []
    for work in batch:
        year = work["year"] if work["year"] is not None else "year unknown"
        line = f'- {work["id"]}: "{work["title"]}" by {work["author"]}, {year}'
        if work["parent_id"] is not None:
            line += f' (part of "{store.work(work["parent_id"])["title"]}")'
        works.append(line)
    return LABEL_PROMPT.format(works="\n".join(works))
