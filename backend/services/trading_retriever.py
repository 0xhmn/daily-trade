"""
Trading Retriever - LangChain BaseRetriever Wrapper

Wraps HybridMultimodalSearch to provide standard LangChain retriever interface.
Enables future integration with GraphRAG and other LangChain components while
maintaining custom control over prompting and parsing.
"""

import logging
from typing import List, Optional

from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from .hybrid_multimodal_search import HybridMultimodalSearch, SearchResult

logger = logging.getLogger(__name__)


class MultimodalOpenSearchRetriever(BaseRetriever):
    """
    LangChain-compatible retriever for trading knowledge base.

    Wraps HybridMultimodalSearch to provide BaseRetriever interface while
    preserving multimodal context (text + images + citations).

    Features:
    - 5-stream hybrid search (kNN + BM25 + RRF)
    - Multimodal results (text chunks, extracted images, full pages)
    - Contextual expansion for comprehensive retrieval
    - Preserved metadata for citations and image references
    """

    # Configure Pydantic v2 to allow extra fields
    model_config = {"extra": "allow", "arbitrary_types_allowed": True}

    def __init__(
        self,
        search_service: HybridMultimodalSearch,
        top_k: int = 10,
        retrieval_k: int = 15,
        expand_context: bool = True,
        max_expanded: int = 20,
        **kwargs,
    ):
        """
        Initialize retriever with search service.

        Args:
            search_service: HybridMultimodalSearch instance
            top_k: Number of final results to return
            retrieval_k: Number to retrieve from each search stream
            expand_context: Whether to add related content
            max_expanded: Maximum results after expansion
            **kwargs: Additional arguments for BaseRetriever
        """
        # Initialize BaseRetriever (don't pass our custom fields to it)
        super().__init__(**kwargs)

        # Set our custom fields after Pydantic initialization
        self.search_service = search_service
        self.top_k = top_k
        self.retrieval_k = retrieval_k
        self.expand_context = expand_context
        self.max_expanded = max_expanded

        logger.info(
            f"Initialized MultimodalOpenSearchRetriever "
            f"(top_k={top_k}, retrieval_k={retrieval_k})"
        )

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[CallbackManagerForRetrieverRun] = None,
    ) -> List[Document]:
        """
        Retrieve relevant documents for the given query.

        This is the main method required by BaseRetriever interface.
        Performs hybrid multimodal search and converts results to LangChain Documents.

        Args:
            query: Search query text
            run_manager: Optional callback manager for retrieval runs

        Returns:
            List of LangChain Document objects with preserved metadata
        """
        logger.info(f"Retrieving documents for query: '{query[:50]}...'")

        # Perform hybrid search
        search_results = self.search_service.search(
            query=query,
            top_k=self.top_k,
            retrieval_k=self.retrieval_k,
            expand_context=self.expand_context,
            max_expanded=self.max_expanded,
        )

        # Convert to LangChain Documents
        documents = [self._convert_to_document(result) for result in search_results]

        logger.info(f"Retrieved {len(documents)} documents")
        return documents

    def _convert_to_document(self, result: SearchResult) -> Document:
        """
        Convert SearchResult to LangChain Document.

        Preserves all multimodal metadata:
        - Source file and page information
        - Image references and descriptions
        - Related content IDs
        - Result type and score

        Args:
            result: SearchResult from hybrid search

        Returns:
            LangChain Document with page_content and metadata
        """
        content = result.content

        # Determine page content based on result type
        if result.result_type == "text_chunk":
            page_content = content.get("text_content", "")
        elif result.result_type == "extracted_image":
            # For images, use the vision analysis description
            page_content = content.get("text_description", "")
        elif result.result_type == "full_page":
            # For full pages, use the page-level description
            page_content = content.get("text_description", "")
        else:
            page_content = str(content)

        # Build comprehensive metadata
        metadata = {
            # Core identification
            "id": result.id,
            "result_type": result.result_type,
            "score": result.score,
            # Source information
            "source_file": content.get("source_file", ""),
            "page_number": content.get("page_number", 0),
            "chunk_id": content.get("chunk_id", ""),
            # Content metadata
            "section_hierarchy": content.get("section_hierarchy", ""),
            "chunk_index": content.get("chunk_index", 0),
            # Multimodal references
            "image_references": content.get("image_references", []),
            "related_extracted_image_ids": content.get("related_extracted_image_ids", []),
            "related_text_chunk_ids": content.get("related_text_chunk_ids", []),
            "full_page_image_id": content.get("full_page_image_id", ""),
            # Image-specific metadata (for extracted_image type)
            "image_id": content.get("image_id", ""),
            "s3_key": content.get("s3_key", ""),
            "bbox": content.get("bbox", {}),
            # Full page metadata (for full_page type)
            "extracted_image_ids": content.get("extracted_image_ids", []),
            "text_chunk_ids": content.get("text_chunk_ids", []),
            # Combined content (text + image descriptions)
            "combined_content": content.get("combined_content", ""),
            # Document metadata
            "document_type": content.get("document_type", ""),
            "author": content.get("author", ""),
            "title": content.get("title", ""),
            "publish_date": content.get("publish_date", ""),
            "topics": content.get("topics", []),
        }

        # Create Document with page_content and metadata
        document = Document(page_content=page_content, metadata=metadata)

        return document

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[AsyncCallbackManagerForRetrieverRun] = None,
    ) -> List[Document]:
        """
        Async version of _get_relevant_documents.

        Currently calls sync version. Can be optimized later if needed.

        Args:
            query: Search query text
            run_manager: Optional async callback manager for retrieval runs

        Returns:
            List of LangChain Document objects with preserved metadata
        """
        # Note: run_manager is async type, but we're calling sync method
        # For now, we pass None to sync method since we can't use async manager with sync code
        return self._get_relevant_documents(query, run_manager=None)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example initialization (requires actual services)
    # from ..repositories.multimodal_opensearch_repository import MultimodalOpenSearchRepository
    # from ..ingestion.multimodal_embedder import NovaMultimodalEmbeddingService
    #
    # repository = MultimodalOpenSearchRepository(host="...")
    # embedder = NovaMultimodalEmbeddingService()
    # search_service = HybridMultimodalSearch(repository, embedder)
    #
    # retriever = MultimodalOpenSearchRetriever(
    #     search_service=search_service,
    #     top_k=10
    # )
    #
    # # Retrieve documents
    # docs = retriever.get_relevant_documents("RSI divergence patterns")
    #
    # for i, doc in enumerate(docs, 1):
    #     print(f"\n{i}. [{doc.metadata['result_type']}]")
    #     print(f"   Source: {doc.metadata['source_file']}, p.{doc.metadata['page_number']}")
    #     print(f"   Score: {doc.metadata['score']:.4f}")
    #     print(f"   Content: {doc.page_content[:100]}...")

    print("MultimodalOpenSearchRetriever initialized")
