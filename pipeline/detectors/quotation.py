from pipeline.detectors.base import Detector


class QuotationDetector(Detector):
    name = "quotation"
    version = "1"

    def detect(self, corpus):
        return []
