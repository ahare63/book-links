"""Ask the model whether each candidate link is real. Verdicts are cached by evidence."""

import sys

from pipeline.model import ModelError, ask_json

MAX_CONSECUTIVE_FAILURES = 3

PROMPT = """\
You are checking a candidate link between two literary works for a reference graph.
A program proposed the link from the evidence below. Decide whether the later work really
draws on the earlier one in the way proposed, or whether the match is a coincidence
(a common word or phrase, a shared stock expression, a different thing with the same name).

Later work (source): {source}
Earlier work (target): {target}
Proposed link type: {type}
Why the program proposed it: {rationale}

Evidence:
{evidence}

Use what you know about both works. A title that is a distinctive phrase found in the earlier
text is usually a real title source; a single everyday word is usually a coincidence.

Reply with one JSON object and nothing else:
{{"verdict": "accept" or "reject", "confidence": a number from 0 to 1 for how sure you are of the verdict, "rationale": "one or two sentences"}}
"""


def describe(work) -> str:
    year = work["year"] if work["year"] is not None else "year unknown"
    return f"{work['title']} by {work['author']} ({year})"


def build_prompt(store, link) -> str:
    lines = []
    for number, row in enumerate(
        store.conn.execute("SELECT source_quote, target_quote FROM evidence WHERE link_id = ? ORDER BY id", (link["id"],)),
        start=1,
    ):
        lines.append(f"{number}. In the later work: {row['source_quote'] or '(no text available; only the title is known)'}")
        lines.append(f"   In the earlier work: {row['target_quote'] or '(no text available)'}")
    return PROMPT.format(
        source=describe(store.work(link["source_id"])),
        target=describe(store.work(link["target_id"])),
        type=link["type"],
        rationale=link["rationale"],
        evidence="\n".join(lines) or "(none)",
    )


def judge(store, args=None):
    pending = store.conn.execute(
        "SELECT * FROM links WHERE evidence_key NOT IN (SELECT evidence_key FROM judgements) ORDER BY id"
    ).fetchall()
    judged = failed = streak = 0
    for link in pending:
        try:
            reply = ask_json(build_prompt(store, link), "verdict")
            verdict = reply["verdict"]
            if verdict not in ("accept", "reject"):
                raise ModelError(f"unexpected verdict {verdict!r}")
            confidence = max(0.0, min(1.0, float(reply.get("confidence", 0.5))))
        except (ModelError, TypeError, ValueError) as error:
            failed += 1
            streak += 1
            print(f"judge: link {link['id']} not judged: {error}", file=sys.stderr)
            if streak >= MAX_CONSECUTIVE_FAILURES:
                print("judge: stopping after repeated failures", file=sys.stderr)
                break
            continue
        streak = 0
        judged += 1
        store.conn.execute(
            "INSERT OR REPLACE INTO judgements (evidence_key, verdict, confidence, rationale) VALUES (?, ?, ?, ?)",
            (link["evidence_key"], verdict, confidence, str(reply.get("rationale", ""))),
        )
        store.conn.commit()
    print(f"judged {judged} of {len(pending)} unjudged links")
    return 1 if failed else 0


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("judge", help="ask the model about every link it has not judged yet")
    parser.set_defaults(func=judge)
