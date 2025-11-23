"""
Multimodal OpenSearch Repository for Trading Knowledge Base

Manages three indexes for hybrid multimodal retrieval:
1. text_chunks_index - Text embeddings from document chunks
2. extracted_images_index - Images extracted from PDFs with dual embeddings
3. full_page_images_index - Full page images with dual embeddings
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.helpers import bulk
from requests_aws4auth import AWS4Auth

from backend.utils.aws_credentials import get_credentials_for_opensearch

logger = logging.getLogger(__name__)

# Type hints for domain objects (avoid circular imports)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ingestion.cross_reference_linker import FullPageImage
    from ingestion.document_processor import DocumentChunk
    from ingestion.image_processor import ExtractedImage


class MultimodalOpenSearchRepository:
    """
    Repository for multimodal hybrid search across text, extracted images, and full pages.

    Features:
    - Three specialized indexes for different modalities
    - Dual embeddings (text + multimodal) for image content
    - Cross-reference tracking between modalities
    - Hybrid search with Reciprocal Rank Fusion across all modalities
    - Contextual expansion for comprehensive retrieval
    """

    def __init__(
        self,
        host: str,
        region: str = "us-east-1",
        text_index: str = "text-chunks",
        extracted_images_index: str = "extracted-images",
        full_pages_index: str = "full-page-images",
        use_ssl: bool = True,
        verify_certs: bool = True,
        local_role_arn: Optional[str] = None,
    ):
        """
        Initialize multimodal OpenSearch repository.

        Args:
            host: OpenSearch domain endpoint
            region: AWS region
            text_index: Name of text chunks index
            extracted_images_index: Name of extracted images index
            full_pages_index: Name of full page images index
            use_ssl: Use SSL connection
            verify_certs: Verify SSL certificates
            local_role_arn: Role ARN for local development
        """
        self.text_index = text_index
        self.extracted_images_index = extracted_images_index
        self.full_pages_index = full_pages_index
        self.region = region

        # Initialize credentials
        session = get_credentials_for_opensearch(region=region, local_role_arn=local_role_arn)
        credentials = session.get_credentials()
        if credentials is None:
            raise ValueError("AWS credentials not found")

        awsauth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            region,
            "es",
            session_token=credentials.token,
        )

        # Initialize OpenSearch client
        self.client = OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=awsauth,
            use_ssl=use_ssl,
            verify_certs=verify_certs,
            connection_class=RequestsHttpConnection,
            timeout=120,
            headers={"Host": host},
        )

        logger.info(
            f"Initialized MultimodalOpenSearch: text={text_index}, "
            f"images={extracted_images_index}, pages={full_pages_index}"
        )

    def _get_document_metadata_properties(self) -> Dict[str, Any]:
        """
        Get common document-level metadata properties shared across all indexes.

        Returns:
            Dictionary of OpenSearch property definitions for document metadata
        """
        return {
            "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "author": {"type": "keyword"},
            "strategy_type": {"type": "keyword"},
            "timeframe": {"type": "keyword"},
            "market_conditions": {"type": "keyword"},
            "asset_class": {"type": "keyword"},
            "key_concepts": {"type": "keyword"},
            "source_file": {"type": "keyword"},
            "document_type": {"type": "keyword"},
        }

    def create_indexes(
        self,
        text_dim: int = 1024,
        multimodal_dim: int = 1024,
        force: bool = False,
    ) -> Dict[str, bool]:
        """
        Create all three indexes with appropriate configurations.

        Args:
            text_dim: Dimension of text embeddings
            multimodal_dim: Dimension of multimodal embeddings
            force: Delete existing indexes if True

        Returns:
            Dictionary with creation status for each index
        """
        results = {}

        # Text chunks index
        results["text"] = self._create_text_chunks_index(text_dim, force)

        # Extracted images index
        results["extracted_images"] = self._create_extracted_images_index(
            text_dim, multimodal_dim, force
        )

        # Full page images index
        results["full_pages"] = self._create_full_page_images_index(text_dim, multimodal_dim, force)

        return results

    def _create_text_chunks_index(self, vector_dim: int, force: bool) -> bool:
        """Create text chunks index."""
        if self.client.indices.exists(index=self.text_index):
            if force:
                self.client.indices.delete(index=self.text_index)
            else:
                logger.info(f"Index {self.text_index} already exists")
                return True

        index_body = {
            "settings": {
                "index": {
                    "knn": True,
                    "knn.algo_param.ef_search": 512,
                    "number_of_shards": 2,
                    "number_of_replicas": 1,
                }
            },
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "text_content": {"type": "text", "analyzer": "standard"},
                    "text_embedding": {
                        "type": "knn_vector",
                        "dimension": vector_dim,
                        "method": {
                            "name": "hnsw",
                            "space_type": "l2",
                            "engine": "lucene",
                            "parameters": {"ef_construction": 512, "m": 16},
                        },
                    },
                    "page_number": {"type": "integer"},
                    "chunk_index": {"type": "integer"},
                    "bbox": {
                        "properties": {
                            "x0": {"type": "float"},
                            "y0": {"type": "float"},
                            "x1": {"type": "float"},
                            "y1": {"type": "float"},
                        }
                    },
                    "metadata": {"properties": self._get_document_metadata_properties()},
                    "related_extracted_image_ids": {"type": "keyword"},
                    "full_page_image_id": {"type": "keyword"},
                }
            },
        }

        response = self.client.indices.create(index=self.text_index, body=index_body)
        logger.info(f"Created text chunks index: {self.text_index}")
        return response.get("acknowledged", False)

    def _create_extracted_images_index(
        self, text_dim: int, multimodal_dim: int, force: bool
    ) -> bool:
        """Create extracted images index with dual embeddings."""
        if self.client.indices.exists(index=self.extracted_images_index):
            if force:
                self.client.indices.delete(index=self.extracted_images_index)
            else:
                logger.info(f"Index {self.extracted_images_index} already exists")
                return True

        index_body = {
            "settings": {
                "index": {
                    "knn": True,
                    "knn.algo_param.ef_search": 512,
                    "number_of_shards": 2,
                    "number_of_replicas": 1,
                }
            },
            "mappings": {
                "properties": {
                    "image_id": {"type": "keyword"},
                    "image_type": {"type": "keyword"},  # chart, diagram, table, illustration
                    "multimodal_embedding": {
                        "type": "knn_vector",
                        "dimension": multimodal_dim,
                        "method": {
                            "name": "hnsw",
                            "space_type": "l2",
                            "engine": "lucene",
                            "parameters": {"ef_construction": 512, "m": 16},
                        },
                    },
                    "text_embedding": {
                        "type": "knn_vector",
                        "dimension": text_dim,
                        "method": {
                            "name": "hnsw",
                            "space_type": "l2",
                            "engine": "lucene",
                            "parameters": {"ef_construction": 512, "m": 16},
                        },
                    },
                    "text_description": {"type": "text", "analyzer": "standard"},
                    "s3_uri": {"type": "keyword"},
                    "page_number": {"type": "integer"},
                    "bbox": {
                        "properties": {
                            "x0": {"type": "float"},
                            "y0": {"type": "float"},
                            "x1": {"type": "float"},
                            "y1": {"type": "float"},
                        }
                    },
                    "extraction_method": {"type": "keyword"},
                    "metadata": {
                        "properties": {
                            **self._get_document_metadata_properties(),
                            # Image-specific metadata
                            "width": {"type": "integer"},
                            "height": {"type": "integer"},
                            "file_size_kb": {"type": "float"},
                            "technical_elements": {"type": "keyword"},
                        }
                    },
                    "related_text_chunk_ids": {"type": "keyword"},
                    "full_page_image_id": {"type": "keyword"},
                }
            },
        }

        response = self.client.indices.create(index=self.extracted_images_index, body=index_body)
        logger.info(f"Created extracted images index: {self.extracted_images_index}")
        return response.get("acknowledged", False)

    def _create_full_page_images_index(
        self, text_dim: int, multimodal_dim: int, force: bool
    ) -> bool:
        """Create full page images index with dual embeddings."""
        if self.client.indices.exists(index=self.full_pages_index):
            if force:
                self.client.indices.delete(index=self.full_pages_index)
            else:
                logger.info(f"Index {self.full_pages_index} already exists")
                return True

        index_body = {
            "settings": {
                "index": {
                    "knn": True,
                    "knn.algo_param.ef_search": 512,
                    "number_of_shards": 2,
                    "number_of_replicas": 1,
                }
            },
            "mappings": {
                "properties": {
                    "page_image_id": {"type": "keyword"},
                    "multimodal_embedding": {
                        "type": "knn_vector",
                        "dimension": multimodal_dim,
                        "method": {
                            "name": "hnsw",
                            "space_type": "l2",
                            "engine": "lucene",
                            "parameters": {"ef_construction": 512, "m": 16},
                        },
                    },
                    "text_embedding": {
                        "type": "knn_vector",
                        "dimension": text_dim,
                        "method": {
                            "name": "hnsw",
                            "space_type": "l2",
                            "engine": "lucene",
                            "parameters": {"ef_construction": 512, "m": 16},
                        },
                    },
                    "text_description": {"type": "text", "analyzer": "standard"},
                    "s3_uri": {"type": "keyword"},
                    "page_number": {"type": "integer"},
                    "dpi": {"type": "integer"},
                    "metadata": {
                        "properties": {
                            **self._get_document_metadata_properties(),
                            # Page-specific metadata
                            "width": {"type": "integer"},
                            "height": {"type": "integer"},
                            "file_size_kb": {"type": "float"},
                            "layout_complexity": {"type": "keyword"},
                            "contains_elements": {"type": "keyword"},
                        }
                    },
                    "text_chunk_ids": {"type": "keyword"},
                    "extracted_image_ids": {"type": "keyword"},
                }
            },
        }

        response = self.client.indices.create(index=self.full_pages_index, body=index_body)
        logger.info(f"Created full page images index: {self.full_pages_index}")
        return response.get("acknowledged", False)

    def index_text_chunk(self, chunk_data: Dict[str, Any]) -> bool:
        """
        Index a text chunk.

        Args:
            chunk_data: Dictionary containing chunk_id, text_content, text_embedding,
                       page_number, chunk_index, bbox, metadata, related_extracted_image_ids,
                       full_page_image_id

        Returns:
            True if indexed successfully
        """
        response = self.client.index(
            index=self.text_index,
            id=chunk_data["chunk_id"],
            body=chunk_data,
            params={"refresh": "true"},
        )
        return response.get("result") in ["created", "updated"]

    def index_extracted_image(self, image_data: Dict[str, Any]) -> bool:
        """
        Index an extracted image with dual embeddings.

        Args:
            image_data: Dictionary containing image_id, image_type, multimodal_embedding,
                       text_embedding, text_description, s3_uri, page_number, bbox,
                       extraction_method, metadata, related_text_chunk_ids, full_page_image_id

        Returns:
            True if indexed successfully
        """
        response = self.client.index(
            index=self.extracted_images_index,
            id=image_data["image_id"],
            body=image_data,
            params={"refresh": "true"},
        )
        return response.get("result") in ["created", "updated"]

    def index_full_page_image(self, page_data: Dict[str, Any]) -> bool:
        """
        Index a full page image with dual embeddings.

        Args:
            page_data: Dictionary containing page_image_id, multimodal_embedding,
                      text_embedding, text_description, s3_uri, page_number, dpi,
                      metadata, text_chunk_ids, extracted_image_ids

        Returns:
            True if indexed successfully
        """
        response = self.client.index(
            index=self.full_pages_index,
            id=page_data["page_image_id"],
            body=page_data,
            params={"refresh": "true"},
        )
        return response.get("result") in ["created", "updated"]

    def _chunk_to_dict(self, chunk: "DocumentChunk") -> Dict[str, Any]:
        """Convert DocumentChunk dataclass to dictionary for OpenSearch."""
        return {
            "chunk_id": f"{chunk.metadata['source_file']}_{chunk.chunk_index}",
            "text_content": chunk.text,
            "text_embedding": chunk.text_embedding,
            "page_number": chunk.page_numbers[0] if chunk.page_numbers else 0,
            "chunk_index": chunk.chunk_index,
            "bbox": {},  # Text chunks don't have bbox
            "metadata": chunk.metadata,
            "related_extracted_image_ids": getattr(chunk, "related_extracted_image_ids", []),
            "full_page_image_id": getattr(chunk, "full_page_image_id", ""),
        }

    def _image_to_dict(self, img: "ExtractedImage") -> Dict[str, Any]:
        """Convert ExtractedImage dataclass to dictionary for OpenSearch."""
        # Merge document-level metadata with image-specific metadata
        metadata = {
            **img.document_metadata,  # Document-level fields: title, author, source_file, etc.
            # Image-specific metadata
            "width": img.width,
            "height": img.height,
            "file_size_kb": img.file_size / 1024,
            "technical_elements": [],
        }

        return {
            "image_id": img.image_id,
            "image_type": "chart",  # Default type
            "multimodal_embedding": img.multimodal_embedding,
            "text_embedding": img.text_embedding,
            "text_description": img.extracted_text or "",
            "s3_uri": getattr(img, "s3_uri", ""),
            "page_number": img.page_number,
            "bbox": {
                "x0": img.bbox[0],
                "y0": img.bbox[1],
                "x1": img.bbox[2],
                "y1": img.bbox[3],
            },
            "extraction_method": img.extraction_method,
            "metadata": metadata,
            "related_text_chunk_ids": img.related_text_chunk_ids,
            "full_page_image_id": img.full_page_image_id,
        }

    def _page_to_dict(self, page: "FullPageImage") -> Dict[str, Any]:
        """Convert FullPageImage dataclass to dictionary for OpenSearch."""
        # Merge document-level metadata with page-specific metadata
        metadata = {
            **page.document_metadata,  # Document-level fields: title, author, source_file, etc.
            # Page-specific metadata
            "layout_complexity": "medium",
            "contains_elements": ["text", "images"],
        }

        return {
            "page_image_id": page.page_image_id,
            "multimodal_embedding": page.multimodal_embedding,
            "text_embedding": page.text_embedding,
            "text_description": page.text_description or "",
            "s3_uri": page.s3_uri,
            "page_number": page.page_number,
            "dpi": 150,  # Default DPI
            "metadata": metadata,
            "text_chunk_ids": page.text_chunk_ids,
            "extracted_image_ids": page.extracted_image_ids,
        }

    def bulk_index_text_chunks(self, chunks: List) -> Tuple[int, int]:
        """
        Bulk index text chunks.

        Args:
            chunks: List of DocumentChunk dataclasses or dictionaries

        Returns:
            Tuple of (success_count, failed_count)
        """
        # Convert dataclasses to dictionaries if needed
        chunk_dicts = []
        for chunk in chunks:
            if isinstance(chunk, dict):
                chunk_dicts.append(chunk)
            else:
                chunk_dicts.append(self._chunk_to_dict(chunk))

        actions = [
            {
                "_index": self.text_index,
                "_id": chunk["chunk_id"],
                "_source": chunk,
            }
            for chunk in chunk_dicts
        ]
        success, failed = bulk(self.client, actions, raise_on_error=False, refresh=True)
        logger.info(f"Bulk indexed text chunks: {success} success, {len(failed)} failed")
        return success, len(failed)

    def bulk_index_extracted_images(self, images: List) -> Tuple[int, int]:
        """
        Bulk index extracted images.

        Args:
            images: List of ExtractedImage dataclasses or dictionaries

        Returns:
            Tuple of (success_count, failed_count)
        """
        # Convert dataclasses to dictionaries if needed
        image_dicts = []
        for img in images:
            if isinstance(img, dict):
                image_dicts.append(img)
            else:
                image_dicts.append(self._image_to_dict(img))

        actions = [
            {
                "_index": self.extracted_images_index,
                "_id": img["image_id"],
                "_source": img,
            }
            for img in image_dicts
        ]
        success, failed = bulk(self.client, actions, raise_on_error=False, refresh=True)
        logger.info(f"Bulk indexed extracted images: {success} success, {len(failed)} failed")
        return success, len(failed)

    def bulk_index_full_page_images(self, pages: List) -> Tuple[int, int]:
        """
        Bulk index full page images.

        Args:
            pages: List of FullPageImage dataclasses or dictionaries

        Returns:
            Tuple of (success_count, failed_count)
        """
        # Convert dataclasses to dictionaries if needed
        page_dicts = []
        for page in pages:
            if isinstance(page, dict):
                page_dicts.append(page)
            else:
                page_dicts.append(self._page_to_dict(page))

        actions = [
            {
                "_index": self.full_pages_index,
                "_id": page["page_image_id"],
                "_source": page,
            }
            for page in page_dicts
        ]
        success, failed = bulk(self.client, actions, raise_on_error=False, refresh=True)
        logger.info(f"Bulk indexed full pages: {success} success, {len(failed)} failed")
        return success, len(failed)

    def vector_search_text(self, query_embedding: List[float], k: int = 15) -> List[Dict[str, Any]]:
        """Search text chunks by vector similarity."""
        query = {
            "size": k,
            "query": {"knn": {"text_embedding": {"vector": query_embedding, "k": k}}},
        }
        response = self.client.search(index=self.text_index, body=query)
        return self._format_results(response)

    def vector_search_extracted_images_text(
        self, query_embedding: List[float], k: int = 15
    ) -> List[Dict[str, Any]]:
        """Search extracted images by text embedding."""
        query = {
            "size": k,
            "query": {"knn": {"text_embedding": {"vector": query_embedding, "k": k}}},
        }
        response = self.client.search(index=self.extracted_images_index, body=query)
        return self._format_results(response)

    def vector_search_extracted_images_multimodal(
        self, query_embedding: List[float], k: int = 15
    ) -> List[Dict[str, Any]]:
        """Search extracted images by multimodal embedding."""
        query = {
            "size": k,
            "query": {"knn": {"multimodal_embedding": {"vector": query_embedding, "k": k}}},
        }
        response = self.client.search(index=self.extracted_images_index, body=query)
        return self._format_results(response)

    def vector_search_full_pages_text(
        self, query_embedding: List[float], k: int = 15
    ) -> List[Dict[str, Any]]:
        """Search full page images by text embedding."""
        query = {
            "size": k,
            "query": {"knn": {"text_embedding": {"vector": query_embedding, "k": k}}},
        }
        response = self.client.search(index=self.full_pages_index, body=query)
        return self._format_results(response)

    def vector_search_full_pages_multimodal(
        self, query_embedding: List[float], k: int = 15
    ) -> List[Dict[str, Any]]:
        """Search full page images by multimodal embedding."""
        query = {
            "size": k,
            "query": {"knn": {"multimodal_embedding": {"vector": query_embedding, "k": k}}},
        }
        response = self.client.search(index=self.full_pages_index, body=query)
        return self._format_results(response)

    def get_by_ids(self, ids: List[str], index_type: str = "text") -> List[Dict[str, Any]]:
        """
        Retrieve documents by IDs.

        Args:
            ids: List of document IDs
            index_type: "text", "extracted_images", or "full_pages"

        Returns:
            List of documents
        """
        if index_type == "text":
            index = self.text_index
        elif index_type == "extracted_images":
            index = self.extracted_images_index
        elif index_type == "full_pages":
            index = self.full_pages_index
        else:
            raise ValueError(f"Unknown index type: {index_type}")

        if not ids:
            return []

        query = {"size": len(ids), "query": {"ids": {"values": ids}}}
        response = self.client.search(index=index, body=query)
        return self._format_results(response)

    def _format_results(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format OpenSearch response to standard result format."""
        results = []
        for hit in response["hits"]["hits"]:
            result = {
                "id": hit["_id"],
                "score": hit["_score"],
                **hit["_source"],
            }
            results.append(result)
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for all indexes."""
        stats = {}

        for name, index in [
            ("text", self.text_index),
            ("extracted_images", self.extracted_images_index),
            ("full_pages", self.full_pages_index),
        ]:
            if self.client.indices.exists(index=index):
                count = self.client.count(index=index)
                stats[name] = {
                    "exists": True,
                    "document_count": count["count"],
                }
            else:
                stats[name] = {"exists": False}

        return stats

    def delete_all_indexes(self) -> Dict[str, bool]:
        """Delete all indexes."""
        results = {}
        for name, index in [
            ("text", self.text_index),
            ("extracted_images", self.extracted_images_index),
            ("full_pages", self.full_pages_index),
        ]:
            if self.client.indices.exists(index=index):
                self.client.indices.delete(index=index)
                results[name] = True
                logger.info(f"Deleted index: {index}")
            else:
                results[name] = False
        return results
