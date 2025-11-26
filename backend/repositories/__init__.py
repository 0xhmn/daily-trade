"""
Repository module for data persistence and retrieval.

Handles OpenSearch index management and multimodal search operations.
"""

from .multimodal_opensearch_repository import MultimodalOpenSearchRepository

__all__ = [
    "MultimodalOpenSearchRepository",
]
