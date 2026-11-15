"""Stands in for the model at the command-line boundary.

Reads the judge prompt on stdin and prints a recorded verdict. A candidate is accepted when its
prompt carries one of the phrases below (each is the evidence of a link that really exists);
everything else is rejected. Each call is logged so tests can count calls.
"""

import json
import os
import sys

ACCEPT = {
    "tender is the night": 0.95,
    "infinite jest": 0.95,
    "sweet ladies": 0.9,
    "metempsychosis": 0.8,
    "season of mists": 0.9,
}

prompt = sys.stdin.read().lower()

log = os.environ.get("FAKE_MODEL_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("call\n")

for phrase, confidence in ACCEPT.items():
    if phrase in prompt:
        print("Here is my assessment.")
        print(json.dumps({"verdict": "accept", "confidence": confidence, "rationale": f"The phrase '{phrase}' is shared."}))
        break
else:
    print(json.dumps({"verdict": "reject", "confidence": 0.9, "rationale": "A common word, not a reference."}))
