"""
Hybrid Multimodal Search Service

Implements 5-stream hybrid search with Reciprocal Rank Fusion:
1. Text-to-Text
2. Text-to-Extracted-Image (Text embeddings)
3. Text-to-Extracted-Image (Multimodal embeddings)
4. Text-to-Full-Page (Text embeddings)
5. Text-to-Full-Page (Multimodal embeddings)

Plus contextual expansion for comprehensive retrieval.

TODO: Current Limitations (Future Enhancements)
- [ ] Add keyword/lexical search (BM25) alongside vector search
- [ ] Add metadata filters (strategy_type, asset_class, date ranges, etc.)
- [ ] Add recency boosting for time-sensitive content
- [ ] Add configurable stream weights for RRF (currently equal weighting)
- [x] Add parallel execution for 5-stream search (using asyncio TaskGroup)
- [ ] Add caching for frequently used query embeddings
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Set

from ..ingestion.multimodal_embedder import NovaMultimodalEmbeddingService
from ..repositories.multimodal_opensearch_repository import MultimodalOpenSearchRepository

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Unified search result across all modalities."""

    id: str
    score: float
    result_type: str  # "text_chunk", "extracted_image", "full_page"
    content: Dict[str, Any]  # Full source data


class HybridMultimodalSearch:
    """
    Hybrid multimodal search with RRF and contextual expansion.

    Features:
    - 5-stream parallel search
    - Reciprocal Rank Fusion for result combination
    - Contextual expansion (adding related content)
    - Deduplication while preserving order
    """

    def __init__(
        self,
        repository: MultimodalOpenSearchRepository,
        embedder: NovaMultimodalEmbeddingService,
        rrf_k: int = 60,
    ):
        """
        Initialize hybrid search service.

        Args:
            repository: MultimodalOpenSearchRepository instance
            embedder: NovaMultimodalEmbeddingService instance
            rrf_k: RRF constant (default 60 is standard)
        """
        self.repository = repository
        self.embedder = embedder
        self.rrf_k = rrf_k

        logger.info(f"Initialized HybridMultimodalSearch with RRF k={rrf_k}")

    async def search(
        self,
        query: str,
        top_k: int = 10,
        retrieval_k: int = 15,
        expand_context: bool = True,
        max_expanded: int = 20,
    ) -> List[SearchResult]:
        """
        Perform hybrid multimodal search with 5 parallel streams.

        Args:
            query: Search query text
            top_k: Number of final results to return
            retrieval_k: Number to retrieve from each stream
            expand_context: Whether to add related content
            max_expanded: Maximum results after expansion

        Returns:
            List of SearchResult objects ordered by relevance
        """
        logger.info(f"Hybrid search for query: '{query[:50]}...'")

        # Generate query embeddings
        query_text_emb = self.embedder.generate_text_embedding(query, purpose="GENERIC_RETRIEVAL")

        # Parallel 5-stream search using asyncio TaskGroup
        logger.info(f"Executing 5-stream parallel search (k={retrieval_k} each)...")

        stream_results: Dict[str, List[Dict[str, Any]]] = {}

        async with asyncio.TaskGroup() as tg:

            async def run_search(name: str, search_func, k: int):
                result = await asyncio.to_thread(search_func, query_text_emb, k)
                stream_results[name] = result

            tg.create_task(run_search("text", self.repository.vector_search_text, retrieval_k))
            tg.create_task(
                run_search(
                    "img_text", self.repository.vector_search_extracted_images_text, retrieval_k
                )
            )
            tg.create_task(
                run_search(
                    "img_mm", self.repository.vector_search_extracted_images_multimodal, retrieval_k
                )
            )
            tg.create_task(
                run_search("page_text", self.repository.vector_search_full_pages_text, retrieval_k)
            )
            tg.create_task(
                run_search(
                    "page_mm", self.repository.vector_search_full_pages_multimodal, retrieval_k
                )
            )

        logger.info(
            f"Retrieved: text={len(stream_results.get('text', []))}, "
            f"img_text={len(stream_results.get('img_text', []))}, "
            f"img_mm={len(stream_results.get('img_mm', []))}, "
            f"page_text={len(stream_results.get('page_text', []))}, "
            f"page_mm={len(stream_results.get('page_mm', []))}"
        )

        # Convert to SearchResult objects
        results_1 = [
            SearchResult(id=r["id"], score=r["score"], result_type="text_chunk", content=r)
            for r in stream_results.get("text", [])
        ]
        results_2 = [
            SearchResult(id=r["id"], score=r["score"], result_type="extracted_image", content=r)
            for r in stream_results.get("img_text", [])
        ]
        results_3 = [
            SearchResult(id=r["id"], score=r["score"], result_type="extracted_image", content=r)
            for r in stream_results.get("img_mm", [])
        ]
        results_4 = [
            SearchResult(id=r["id"], score=r["score"], result_type="full_page", content=r)
            for r in stream_results.get("page_text", [])
        ]
        results_5 = [
            SearchResult(id=r["id"], score=r["score"], result_type="full_page", content=r)
            for r in stream_results.get("page_mm", [])
        ]

        # Apply Reciprocal Rank Fusion
        fused_results = self._reciprocal_rank_fusion(
            [results_1, results_2, results_3, results_4, results_5],
            top_k=top_k,
        )

        logger.info(f"RRF produced {len(fused_results)} fused results")

        # Contextual expansion
        if expand_context and len(fused_results) > 0:
            expanded = self._expand_context(fused_results, max_results=max_expanded)
            logger.info(f"Contextual expansion: {len(fused_results)} → {len(expanded)}")
            return expanded

        return fused_results

    def _reciprocal_rank_fusion(
        self,
        result_streams: List[List[SearchResult]],
        top_k: int,
    ) -> List[SearchResult]:
        """
        Combine results using Reciprocal Rank Fusion.

        RRF formula: score(d) = Σ 1/(k + rank(d)) across all streams

        Args:
            result_streams: List of result lists from different searches
            top_k: Number of top results to return

        Returns:
            Fused and ranked results
        """
        # Calculate RRF scores
        rrf_scores: Dict[str, float] = defaultdict(float)
        result_map: Dict[str, SearchResult] = {}

        for stream_results in result_streams:
            for rank, result in enumerate(stream_results, start=1):
                doc_id = result.id
                rrf_score = 1.0 / (self.rrf_k + rank)
                rrf_scores[doc_id] += rrf_score

                # Store result (any occurrence is fine, they should be same content)
                if doc_id not in result_map:
                    result_map[doc_id] = result

        # Sort by RRF score
        sorted_ids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        # Create final results with RRF scores
        fused_results = []
        for doc_id, rrf_score in sorted_ids:
            result = result_map[doc_id]
            # Update score to RRF score
            result.score = rrf_score
            fused_results.append(result)

        return fused_results

    def _expand_context(
        self,
        core_results: List[SearchResult],
        max_results: int = 20,
    ) -> List[SearchResult]:
        """
        Expand results with related content.

        Strategy:
        - For text chunks: Add related extracted images + full page
        - For extracted images: Add related text chunks + full page
        - For full pages: Add top extracted images + text chunks from page

        Args:
            core_results: Core search results to expand
            max_results: Maximum total results after expansion

        Returns:
            Expanded results (deduplicated, ordered by relevance)
        """
        expanded = []
        seen_ids: Set[str] = set()

        for result in core_results:
            # Add the core result itself
            if result.id not in seen_ids:
                expanded.append(result)
                seen_ids.add(result.id)

            # Stop if we've reached max
            if len(expanded) >= max_results:
                break

            # Add related content based on type
            if result.result_type == "text_chunk":
                related = self._expand_text_chunk(result, seen_ids, max_results)
            elif result.result_type == "extracted_image":
                related = self._expand_extracted_image(result, seen_ids, max_results)
            elif result.result_type == "full_page":
                related = self._expand_full_page(result, seen_ids, max_results)
            else:
                related = []

            # Add related items
            for item in related:
                if len(expanded) >= max_results:
                    break
                if item.id not in seen_ids:
                    expanded.append(item)
                    seen_ids.add(item.id)

        return expanded

    def _expand_text_chunk(
        self,
        result: SearchResult,
        seen_ids: Set[str],
        max_results: int,
    ) -> List[SearchResult]:
        """Expand text chunk with related images and full page."""
        related = []

        # Get related extracted images
        image_ids = result.content.get("related_extracted_image_ids", [])
        if image_ids:
            images = self.repository.get_by_ids(image_ids, "extracted_images")
            for img in images:
                if img["id"] not in seen_ids:
                    related.append(
                        SearchResult(
                            id=img["id"],
                            score=result.score * 0.8,  # Slightly lower score
                            result_type="extracted_image",
                            content=img,
                        )
                    )

        # Get full page image
        page_id = result.content.get("full_page_image_id")
        if page_id and page_id not in seen_ids:
            pages = self.repository.get_by_ids([page_id], "full_pages")
            if pages:
                related.append(
                    SearchResult(
                        id=pages[0]["id"],
                        score=result.score * 0.7,  # Lower score for full page
                        result_type="full_page",
                        content=pages[0],
                    )
                )

        return related

    def _expand_extracted_image(
        self,
        result: SearchResult,
        seen_ids: Set[str],
        max_results: int,
    ) -> List[SearchResult]:
        """Expand extracted image with related text and full page."""
        related = []

        # Get related text chunks
        chunk_ids = result.content.get("related_text_chunk_ids", [])
        if chunk_ids:
            chunks = self.repository.get_by_ids(chunk_ids, "text")
            for chunk in chunks:
                if chunk["id"] not in seen_ids:
                    related.append(
                        SearchResult(
                            id=chunk["id"],
                            score=result.score * 0.8,
                            result_type="text_chunk",
                            content=chunk,
                        )
                    )

        # Get full page image
        page_id = result.content.get("full_page_image_id")
        if page_id and page_id not in seen_ids:
            pages = self.repository.get_by_ids([page_id], "full_pages")
            if pages:
                related.append(
                    SearchResult(
                        id=pages[0]["id"],
                        score=result.score * 0.7,
                        result_type="full_page",
                        content=pages[0],
                    )
                )

        return related

    def _expand_full_page(
        self,
        result: SearchResult,
        seen_ids: Set[str],
        max_results: int,
    ) -> List[SearchResult]:
        """Expand full page with extracted images and text chunks."""
        related = []

        # Get extracted images (top 3)
        image_ids = result.content.get("extracted_image_ids", [])[:3]
        if image_ids:
            images = self.repository.get_by_ids(image_ids, "extracted_images")
            for img in images:
                if img["id"] not in seen_ids:
                    related.append(
                        SearchResult(
                            id=img["id"],
                            score=result.score * 0.8,
                            result_type="extracted_image",
                            content=img,
                        )
                    )

        # Get text chunks (top 5)
        chunk_ids = result.content.get("text_chunk_ids", [])[:5]
        if chunk_ids:
            chunks = self.repository.get_by_ids(chunk_ids, "text")
            for chunk in chunks:
                if chunk["id"] not in seen_ids:
                    related.append(
                        SearchResult(
                            id=chunk["id"],
                            score=result.score * 0.8,
                            result_type="text_chunk",
                            content=chunk,
                        )
                    )

        return related


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Initialize components (requires actual OpenSearch endpoint)
    # repository = MultimodalOpenSearchRepository(
    #     host="search-xxx.us-east-1.es.amazonaws.com"
    # )
    # embedder = NovaMultimodalEmbeddingService()
    # search = HybridMultimodalSearch(repository, embedder)

    # Perform search
    # results = search.search(
    #     query="Explain RSI divergence patterns",
    #     top_k=10,
    #     expand_context=True
    # )

    # Display results
    # for i, result in enumerate(results, 1):
    #     print(f"{i}. [{result.result_type}] {result.id}")
    #     print(f"   Score: {result.score:.4f}")
    #     if result.result_type == "text_chunk":
    #         print(f"   Text: {result.content['text_content'][:100]}...")
    #     elif result.result_type == "extracted_image":
    #         print(f"   Image: {result.content['text_description'][:100]}...")
    #     elif result.result_type == "full_page":
    #         print(f"   Page: {result.content['text_description'][:100]}...")

    print("HybridMultimodalSearch initialized")
