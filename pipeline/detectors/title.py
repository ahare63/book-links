from pipeline.detectors.base import Detector


class TitleDetector(Detector):
    name = "title"
    version = "1"

    def detect(self, corpus):
        return []
