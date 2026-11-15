"""Stands in for the model when an article is ingested: prints the recorded extraction for
tests/fixtures/article_ulysses.txt regardless of the prompt."""

import json
import sys

sys.stdin.read()

print(
    json.dumps(
        {
            "links": [
                {
                    "source": "Ulysses",
                    "target": "Hamlet",
                    "type": "allusion",
                    "quote": "Stephen Dedalus carries Hamlet with him through the day",
                    "rationale": "The article says Stephen's theory of Hamlet structures the library episode.",
                },
                {
                    "source": "Ulysses",
                    "target": "A Book Nobody Added",
                    "type": "allusion",
                    "quote": "an unnamed pamphlet",
                    "rationale": "Names a work that is not in the corpus.",
                },
            ],
            "signature_terms": [
                {"work": "Ulysses", "term": "parallax", "weight": 0.9},
                {"work": "Ulysses", "term": "metempsychosis", "weight": 0.9},
            ],
        }
    )
)
