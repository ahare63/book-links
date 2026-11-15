from pipeline.detectors.base import Detector


class VocabularyDetector(Detector):
    name = "vocabulary"
    version = "1"

    def detect(self, corpus):
        return []
