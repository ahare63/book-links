"""Works that share uncommon themes, from the labels in the themes table.

The labels are the model's reading of each work, so the evidence is the model's notes, not quotes.
"""

from collections import defaultdict

from pipeline.detectors.base import Candidate, Detector, Evidence

MIN_SHARED = 2
MAX_HOLDERS = 0.1  # a theme held by more than this share of labelled works says little
MIN_LIMIT = 3
THEME_WEIGHT = 0.2
SCORE_CAP = 0.4


class ThemeDetector(Detector):
    name = "theme"
    version = "2"

    def detect(self, corpus):
        notes = defaultdict(dict)  # work id -> theme -> note
        for label in corpus.themes:
            notes[label.work_id][label.theme] = label.note
        holders = defaultdict(int)
        for themes in notes.values():
            for theme in themes:
                holders[theme] += 1
        limit = max(MIN_LIMIT, MAX_HOLDERS * len(notes))
        works = {work.id: work for work in corpus.works}

        candidates = []
        for later_id, later_themes in sorted(notes.items()):
            for earlier_id, earlier_themes in sorted(notes.items()):
                later, earlier = works.get(later_id), works.get(earlier_id)
                if later is None or earlier is None or not self._comparable(later, earlier):
                    continue
                shared = sorted(
                    (t for t in later_themes if t in earlier_themes and holders[t] <= limit),
                    key=lambda t: (holders[t], t),
                )
                if len(shared) < MIN_SHARED:
                    continue
                miss = 1.0
                for theme in shared:
                    miss *= 1 - THEME_WEIGHT * (1 - (holders[theme] - 2) / limit)
                listed = "; ".join(f'"{t}"' for t in shared)
                candidates.append(
                    Candidate(
                        source_id=later.id,
                        target_id=earlier.id,
                        type="theme",
                        score=round(min(SCORE_CAP, 1 - miss), 3),
                        rationale=f'"{later.title}" and "{earlier.title}" share the themes {listed}'
                        " (labels from the model's knowledge of the works, not from their text).",
                        evidence=[
                            Evidence(
                                source_quote=f"{t}: {later_themes[t]}",
                                target_quote=f"{t}: {earlier_themes[t]}",
                            )
                            for t in shared
                        ],
                    )
                )
        return candidates

    @staticmethod
    def _comparable(later, earlier):
        if later.id == earlier.id or later.author == earlier.author:
            return False
        if later.year == earlier.year and later.id < earlier.id:
            return False  # a theme has no direction, so same-year works get one link, not two
        if later.parent_id is not None and later.parent_id in (earlier.id, earlier.parent_id):
            return False
        if earlier.parent_id == later.id:
            return False
        return later.year is not None and earlier.year is not None and later.year >= earlier.year
