from pipeline.detectors.base import Detector


class SignatureDetector(Detector):
    name = "signature"
    version = "1"

    def detect(self, corpus):
        return []
