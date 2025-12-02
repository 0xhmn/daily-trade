"""
Trading RAG Service - Context Orchestration

Orchestrates retrieval and context preparation for trading signal generation.
Combines market data with retrieved trading knowledge to create comprehensive
context for LLM-based signal generation.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from langchain_core.documents import Document

from .trading_retriever import MultimodalOpenSearchRetriever

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """Citation information from retrieved documents."""

    source_file: str
    page_number: int
    content_snippet: str
    result_type: str  # "text_chunk", "extracted_image", "full_page"
    relevance_score: float
    image_id: Optional[str] = None
    s3_key: Optional[str] = None


@dataclass
class RAGContext:
    """Prepared context for LLM prompt."""

    formatted_context: str
    citations: List[Citation]
    total_documents: int
    document_types: Dict[str, int]  # Count by result_type
    has_images: bool
    market_state: Optional[Dict] = None


class TradingRAGService:
    """
    Service for trading knowledge retrieval and context preparation.

    Responsibilities:
    - Query trading knowledge base via retriever
    - Filter results by relevance threshold
    - Extract and format citations
    - Prepare comprehensive context for LLM
    - Combine market data with retrieved knowledge
    """

    def __init__(
        self,
        retriever: MultimodalOpenSearchRetriever,
        min_relevance_score: float = 0.5,
        max_context_length: int = 8000,
    ):
        """
        Initialize RAG service.

        Args:
            retriever: MultimodalOpenSearchRetriever instance
            min_relevance_score: Minimum score threshold for including results
            max_context_length: Maximum character length for context
        """
        self.retriever = retriever
        self.min_relevance_score = min_relevance_score
        self.max_context_length = max_context_length

        logger.info(
            f"Initialized TradingRAGService "
            f"(min_score={min_relevance_score}, max_length={max_context_length})"
        )

    def prepare_context(
        self,
        query: str,
        market_state: Optional[Dict] = None,
        max_documents: int = 10,
    ) -> RAGContext:
        """
        Prepare comprehensive context for signal generation.

        Args:
            query: Trading analysis query (e.g., "RSI divergence support bounce")
            market_state: Optional market data (price, indicators, patterns)
            max_documents: Maximum number of documents to include

        Returns:
            RAGContext with formatted context and citations
        """
        logger.info(f"Preparing context for query: '{query[:50]}...'")

        # Retrieve relevant documents using LangChain retriever interface
        documents = self.retriever.invoke(query)
        logger.info(f"Retrieved {len(documents)} documents from knowledge base")

        # Filter by relevance score
        filtered_docs = self._filter_by_relevance(documents)
        logger.info(
            f"Filtered to {len(filtered_docs)} documents " f"(score >= {self.min_relevance_score})"
        )

        # Limit to max documents
        selected_docs = filtered_docs[:max_documents]

        # Extract citations
        citations = self._extract_citations(selected_docs)

        # Format context
        formatted_context = self._format_context(selected_docs, market_state, citations)

        # Calculate statistics
        doc_types = self._count_document_types(selected_docs)
        has_images = any(
            doc.metadata.get("result_type") in ["extracted_image", "full_page"]
            for doc in selected_docs
        )

        rag_context = RAGContext(
            formatted_context=formatted_context,
            citations=citations,
            total_documents=len(selected_docs),
            document_types=doc_types,
            has_images=has_images,
            market_state=market_state,
        )

        logger.info(
            f"Context prepared: {len(selected_docs)} docs, "
            f"{len(citations)} citations, "
            f"{len(formatted_context)} chars"
        )

        return rag_context

    def _filter_by_relevance(self, documents: List[Document]) -> List[Document]:
        """
        Filter documents by minimum relevance score.

        Args:
            documents: List of retrieved documents

        Returns:
            Filtered list of documents
        """
        filtered = [
            doc for doc in documents if doc.metadata.get("score", 0) >= self.min_relevance_score
        ]
        return filtered

    def _extract_citations(self, documents: List[Document]) -> List[Citation]:
        """
        Extract citation information from documents.

        Args:
            documents: List of documents to extract citations from

        Returns:
            List of Citation objects
        """
        citations = []

        for doc in documents:
            metadata = doc.metadata
            content_snippet = doc.page_content[:200]  # First 200 chars

            citation = Citation(
                source_file=metadata.get("source_file", "Unknown"),
                page_number=metadata.get("page_number", 0),
                content_snippet=content_snippet,
                result_type=metadata.get("result_type", "text_chunk"),
                relevance_score=metadata.get("score", 0.0),
                image_id=metadata.get("image_id"),
                s3_key=metadata.get("s3_key"),
            )
            citations.append(citation)

        return citations

    def _format_context(
        self,
        documents: List[Document],
        market_state: Optional[Dict],
        citations: List[Citation],
    ) -> str:
        """
        Format documents and market state into LLM-ready context.

        Args:
            documents: Retrieved documents
            market_state: Market data (if provided)
            citations: Citation information

        Returns:
            Formatted context string
        """
        sections = []

        # Market state section (if provided)
        if market_state:
            market_section = self._format_market_state(market_state)
            sections.append(market_section)

        # Retrieved knowledge section
        knowledge_section = self._format_knowledge_base_content(documents, citations)
        sections.append(knowledge_section)

        # Combine sections
        formatted = "\n\n".join(sections)

        # Truncate if exceeds max length
        if len(formatted) > self.max_context_length:
            logger.warning(
                f"Context truncated from {len(formatted)} to {self.max_context_length} chars"
            )
            formatted = formatted[: self.max_context_length] + "\n...(truncated)"

        return formatted

    def _format_market_state(self, market_state: Dict) -> str:
        """
        Format market data into readable section.

        Args:
            market_state: Market data dictionary

        Returns:
            Formatted market state string
        """
        lines = ["=== MARKET STATE ==="]

        # Basic info
        symbol = market_state.get("symbol", "Unknown")
        price = market_state.get("current_price", 0.0)
        lines.append(f"Symbol: {symbol}")
        lines.append(f"Current Price: ${price:.2f}")

        # Technical indicators
        indicators = market_state.get("indicators", {})
        if indicators:
            lines.append("\nTechnical Indicators:")
            for name, value in indicators.items():
                if isinstance(value, float):
                    lines.append(f"  {name}: {value:.2f}")
                else:
                    lines.append(f"  {name}: {value}")

        # Support/Resistance levels
        support = market_state.get("support_levels", [])
        resistance = market_state.get("resistance_levels", [])
        if support:
            levels = ", ".join([f"${s:.2f}" for s in support])
            lines.append(f"\nSupport Levels: {levels}")
        if resistance:
            levels = ", ".join([f"${r:.2f}" for r in resistance])
            lines.append(f"Resistance Levels: {levels}")

        # Patterns detected
        patterns = market_state.get("patterns", [])
        if patterns:
            lines.append(f"\nDetected Patterns: {', '.join(patterns)}")

        return "\n".join(lines)

    def _format_knowledge_base_content(
        self, documents: List[Document], citations: List[Citation]
    ) -> str:
        """
        Format retrieved knowledge base content.

        Args:
            documents: Retrieved documents
            citations: Citation information

        Returns:
            Formatted knowledge section
        """
        lines = ["=== TRADING KNOWLEDGE ==="]
        lines.append("(From your ingested trading books and resources)")
        lines.append("")

        for i, (doc, citation) in enumerate(zip(documents, citations), 1):
            # Citation header
            result_type = citation.result_type.replace("_", " ").title()
            lines.append(
                f"[{i}] {result_type} from {citation.source_file}, "
                f"p.{citation.page_number} (relevance: {citation.relevance_score:.2f})"
            )

            # Content
            content = doc.page_content.strip()
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(content)

            # Image reference (if applicable)
            if citation.image_id:
                lines.append(f"   [Image: {citation.image_id}]")

            lines.append("")  # Blank line between entries

        return "\n".join(lines)

    def _count_document_types(self, documents: List[Document]) -> Dict[str, int]:
        """
        Count documents by type.

        Args:
            documents: List of documents

        Returns:
            Dictionary mapping result_type to count
        """
        counts: Dict[str, int] = {}
        for doc in documents:
            result_type = doc.metadata.get("result_type", "unknown")
            counts[result_type] = counts.get(result_type, 0) + 1
        return counts


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example initialization (requires actual services)
    # from ..repositories.multimodal_opensearch_repository import MultimodalOpenSearchRepository
    # from ..ingestion.multimodal_embedder import NovaMultimodalEmbeddingService
    # from .hybrid_multimodal_search import HybridMultimodalSearch
    #
    # repository = MultimodalOpenSearchRepository(host="...")
    # embedder = NovaMultimodalEmbeddingService()
    # search_service = HybridMultimodalSearch(repository, embedder)
    # retriever = MultimodalOpenSearchRetriever(search_service=search_service)
    #
    # rag_service = TradingRAGService(retriever=retriever)
    #
    # # Prepare context with mock market state
    # mock_market_state = {
    #     "symbol": "AAPL",
    #     "current_price": 180.50,
    #     "indicators": {
    #         "RSI": 42,
    #         "SMA_20": 175.20,
    #         "MACD": -1.2,
    #     },
    #     "support_levels": [178.00, 175.50],
    #     "resistance_levels": [185.00, 190.00],
    #     "patterns": ["support_bounce"],
    # }
    #
    # context = rag_service.prepare_context(
    #     query="RSI divergence support bounce swing trade",
    #     market_state=mock_market_state
    # )
    #
    # print(f"\n=== Context Prepared ===")
    # print(f"Total Documents: {context.total_documents}")
    # print(f"Citations: {len(context.citations)}")
    # print(f"Has Images: {context.has_images}")
    # print(f"\n{context.formatted_context[:500]}...")

    print("TradingRAGService initialized")
