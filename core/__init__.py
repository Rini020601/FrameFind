"""
Core package for Screenrecord Manager.
"""
from .database import SearchDatabase
from .ocr import AppleVisionOCR, get_ocr_engine
from .video import VideoProcessor
from .classifier import CaptureClassifier
from .redactor import PrivacyRedactor
from .compressor import VideoCompressor
from .namer import SmartNamer
from .indexer import IndexerPipeline
from .watcher import CaptureWatcher

__all__ = [
    "SearchDatabase",
    "AppleVisionOCR",
    "get_ocr_engine",
    "VideoProcessor",
    "CaptureClassifier",
    "PrivacyRedactor",
    "VideoCompressor",
    "SmartNamer",
    "IndexerPipeline",
    "CaptureWatcher"
]
