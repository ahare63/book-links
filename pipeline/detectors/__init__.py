"""The detectors that run on every ``book-links detect``."""

from pipeline.detectors.mention import MentionDetector
from pipeline.detectors.names import NamesDetector
from pipeline.detectors.quotation import QuotationDetector
from pipeline.detectors.signature import SignatureDetector
from pipeline.detectors.theme import ThemeDetector
from pipeline.detectors.title import TitleDetector
from pipeline.detectors.vocabulary import VocabularyDetector

DETECTORS = [
    TitleDetector(),
    QuotationDetector(),
    MentionDetector(),
    VocabularyDetector(),
    SignatureDetector(),
    NamesDetector(),
    ThemeDetector(),
]
