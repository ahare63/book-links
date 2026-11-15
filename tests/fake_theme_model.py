"""Stands in for the model for `book-links themes`.

Labelling prompts list works as `- 12: "Title" by Author, year`; the reply gives recorded themes for
each. Merge prompts list labels as `- label`; the reply groups the two wordings of the wager theme.
Each call is logged, with the prompt, so tests can count calls and see what was asked."""

import json
import os
import re
import sys

WAGER = "a wager between god and the devil over a righteous man"
HEAVENLY_WAGER = "a heavenly bet on whether a good man will curse god"

THEMES = {
    "The Wager": [
        (WAGER, "God lets Mephistopheles tempt Faust."),
        ("the limits of human knowledge", "Faust despairs of his learning."),
        ("seduction and ruin of an innocent", "Gretchen is destroyed."),
    ],
    "The Sufferer": [
        (HEAVENLY_WAGER, "Satan wagers that Job will curse God."),
        ("the limits of human knowledge", "God answers Job from the whirlwind."),
        ("undeserved suffering", "Job loses everything."),
    ],
    "The Doctor": [
        ("the limits of human knowledge", "A doctor fails to cure a fever."),
        ("a country practice", "Rounds in the rain."),
    ],
    "Twin One": [("twins parted at birth", "x."), ("a shipwreck on a strange coast", "x.")],
    "Twin Two": [("twins parted at birth", "x."), ("a shipwreck on a strange coast", "x.")],
    "Sea One": [("the sea as fate", "x."), ("whaling", "x."), ("a mad captain", "x.")],
    "Sea Two": [("the sea as fate", "x."), ("whaling", "x."), ("a storm", "x.")],
    "Sea Three": [("the sea as fate", "x."), ("whaling", "x."), ("a lighthouse", "x.")],
    "Sea Four": [("the sea as fate", "x."), ("whaling", "x."), ("a shipwreck", "x.")],
}

prompt = sys.stdin.read()

log = os.environ.get("FAKE_MODEL_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("call\n" + prompt + "\nend of call\n")

if "Labels:" in prompt:
    labels = re.findall(r"^- (.+)$", prompt.split("Labels:", 1)[1], re.MULTILINE)
    groups = [{"theme": WAGER, "labels": [WAGER, HEAVENLY_WAGER]}] if HEAVENLY_WAGER in labels else []
    print(json.dumps({"groups": groups}))
    sys.exit()

works = []
for work_id, title in re.findall(r'^- (\d+): "(.+?)"', prompt, re.MULTILINE):
    if title == "Odd Reply":  # ids as strings and a theme as a bare string, as models sometimes reply
        works.append({"id": work_id, "themes": ["a bare label", {"theme": "a proper label", "note": "n."}]})
        continue
    themes = [{"theme": theme, "note": note} for theme, note in THEMES.get(title, [])]
    works.append({"id": int(work_id), "themes": themes})
print(json.dumps({"works": works}))
