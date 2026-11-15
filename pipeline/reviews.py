"""The owner's verdicts. A review belongs to a pair of works and a link type, so it survives re-runs."""

import sys
from datetime import datetime, timezone

from pipeline.detectors.base import LINK_TYPES


def record_review(store, link_id, verdict, corrected_type=None, note=None) -> bool:
    """Save a verdict for the link with this id. Returns False if there is no such link."""
    link = store.conn.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
    if link is None:
        return False
    store.conn.execute(
        "INSERT INTO reviews (source_id, target_id, type, verdict, corrected_type, note, created)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (source_id, target_id, type) DO UPDATE SET"
        " verdict = excluded.verdict, corrected_type = excluded.corrected_type,"
        " note = excluded.note, created = excluded.created",
        (
            link["source_id"],
            link["target_id"],
            link["type"],
            verdict,
            corrected_type,
            note,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )
    store.conn.commit()
    return True


def review(store, args):
    if not record_review(store, args.link_id, args.verdict, args.type, args.note):
        print(f"review: no link with id {args.link_id}", file=sys.stderr)
        return 1


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("review", help="accept or reject a link")
    parser.add_argument("link_id", type=int, help="the link's id, as shown in the exported graph")
    parser.add_argument("--verdict", required=True, choices=["accept", "reject"])
    parser.add_argument("--type", choices=LINK_TYPES, help="the correct link type, if the detected one is wrong")
    parser.add_argument("--note")
    parser.set_defaults(func=review)
