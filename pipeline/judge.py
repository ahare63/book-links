"""Ask the model whether each candidate link is real. Verdicts are cached by evidence."""

import sys
from concurrent.futures import ThreadPoolExecutor

from pipeline.model import DEFAULT_MODEL, ModelError, ask_json

MAX_CONSECUTIVE_FAILURES = 3
WORKERS = 4
# Shared names leave the judge only its knowledge of the two works to go on, and Haiku too often
# calls a real allusion (the Aeneid's Trojans, Hamlet's Aeneas and Dido) a shared tradition.
MODELS = {"names": "sonnet"}


def model_for(link) -> str:
    return MODELS.get(link["detector"], DEFAULT_MODEL)


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

When the evidence is shared names of people and places, the names only point to a possible link,
and no shared wording is expected (the works may be in different languages). Accept when, from what
you know, the later work engages with this particular earlier work: it retells, imitates or answers
it, reworks its characters or episodes, or discusses it. Reject when the names come from history,
geography or a common tradition that the later work could have taken from elsewhere.

Reply with one JSON object and nothing else:
{{"verdict": "accept" or "reject", "confidence": a number from 0 to 1 for how sure you are of the verdict, "rationale": "one or two sentences"}}
"""


def describe(work) -> str:
    year = work["year"] if work["year"] is not None else "year unknown"
    return f"{work['title']} by {work['author']} ({year})"


def build_prompt(store, link) -> str:
    lines = []
    for number, row in enumerate(
        store.conn.execute(
            "SELECT source_quote, target_quote FROM evidence WHERE link_id = ? ORDER BY id", (link["id"],)
        ),
        start=1,
    ):
        lines.append(
            f"{number}. In the later work: {row['source_quote'] or '(no text available; only the title is known)'}"
        )
        lines.append(f"   In the earlier work: {row['target_quote'] or '(no text available)'}")
    return PROMPT.format(
        source=describe(store.work(link["source_id"])),
        target=describe(store.work(link["target_id"])),
        type=link["type"],
        rationale=link["rationale"],
        evidence="\n".join(lines) or "(none)",
    )


def ask_about(prompt, model):
    """The model's verdict on one prompt as ``(verdict, confidence, rationale)``, or the error."""
    try:
        reply = ask_json(prompt, "verdict", model)
        verdict = reply["verdict"]
        if verdict not in ("accept", "reject"):
            raise ModelError(f"unexpected verdict {verdict!r}")
        confidence = max(0.0, min(1.0, float(reply.get("confidence", 0.5))))
    except (ModelError, TypeError, ValueError) as error:
        return error
    return verdict, confidence, str(reply.get("rationale", ""))


def judge(store, args=None):
    judged_by = dict(store.conn.execute("SELECT evidence_key, model FROM judgements"))
    # A verdict from another model than the one a link is now sent to is asked again.
    pending = [
        link
        for link in store.conn.execute("SELECT * FROM links ORDER BY id")
        if judged_by.get(link["evidence_key"]) != model_for(link)
    ]
    judged = failed = streak = 0
    # The model calls run a few at a time; results are saved here, in link order, as they finish.
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(ask_about, build_prompt(store, link), model_for(link)) for link in pending]
        for link, future in zip(pending, futures, strict=True):
            result = future.result()
            if isinstance(result, Exception):
                failed += 1
                streak += 1
                print(f"judge: link {link['id']} not judged: {result}", file=sys.stderr)
                if streak >= MAX_CONSECUTIVE_FAILURES:
                    print("judge: stopping after repeated failures", file=sys.stderr)
                    for waiting in futures:
                        waiting.cancel()
                    break
                continue
            streak = 0
            judged += 1
            verdict, confidence, rationale = result
            store.conn.execute(
                "INSERT OR REPLACE INTO judgements (evidence_key, verdict, confidence, rationale, model)"
                " VALUES (?, ?, ?, ?, ?)",
                (link["evidence_key"], verdict, confidence, rationale, model_for(link)),
            )
            store.conn.commit()
    print(f"judged {judged} of {len(pending)} links not yet judged by their model")
    return 1 if failed else 0


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("judge", help="ask the model about every link it has not judged yet")
    parser.set_defaults(func=judge)
