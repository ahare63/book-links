from pipeline.detectors.base import Detector


class MentionDetector(Detector):
    name = "mention"
    version = "1"

    def detect(self, corpus):
        return []
