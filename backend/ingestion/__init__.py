"""
Ingestion module for multimodal document processing.

Handles PDF text extraction, image extraction, embeddings generation,
and cross-reference linking for the RAG system.
"""

from .cross_reference_linker import CrossReferenceLinker, FullPageImage
from .document_ingestion_orchestrator import DocumentIngestionOrchestrator
from .document_processor import DocumentChunk, DocumentMetadata, DocumentProcessor
from .image_processor import (
    ExtractedImage,
    ExtractionMethod,
    ImageAnalysis,
    ImageProcessor,
    ImageReference,
)
from .multimodal_embedder import NovaMultimodalEmbeddingService
from .nova_vision_service import NovaVisionService

__all__ = [
    # Cross-reference linker
    "CrossReferenceLinker",
    "FullPageImage",
    # Document ingestion orchestrator
    "DocumentIngestionOrchestrator",
    # Document processor
    "DocumentChunk",
    "DocumentMetadata",
    "DocumentProcessor",
    # Image processor
    "ExtractionMethod",
    "ExtractedImage",
    "ImageAnalysis",
    "ImageProcessor",
    "ImageReference",
    # Multimodal embedder
    "NovaMultimodalEmbeddingService",
    # Nova vision service
    "NovaVisionService",
]
