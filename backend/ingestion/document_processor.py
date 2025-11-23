"""
Document Processor for Trading Knowledge Base

Handles PDF text extraction, chunking, and metadata management.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pdfplumber
import PyPDF2

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """Represents a processed document chunk."""

    text: str
    chunk_index: int
    metadata: Dict[str, Any]
    page_numbers: List[int]
    related_extracted_image_ids: List[str] = field(default_factory=list)
    full_page_image_id: str = ""
    text_embedding: List[float] = field(default_factory=list)


@dataclass
class DocumentMetadata:
    """Metadata for a trading document."""

    title: str
    author: Optional[str]
    strategy_type: str  # swing_trading, technical_analysis, risk_management
    timeframe: str  # 3-7 days, 7-14 days, etc.
    market_conditions: List[str]  # trending, ranging, volatile
    asset_class: List[str]  # equities, forex, commodities
    key_concepts: List[str]
    source_file: str
    document_type: str  # test_doc, ebook, article etc.
    page_count: Optional[int] = None


class DocumentProcessor:
    """
    Processes trading documents for RAG system.

    Features:
    - PDF text extraction (PyPDF2 or pdfplumber)
    - Intelligent chunking with overlap
    - Sentence boundary preservation
    - Metadata extraction and tagging
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100,
    ):
        """
        Initialize document processor.

        Args:
            chunk_size: Target size for each chunk (characters)
            chunk_overlap: Overlap between chunks (characters)
            min_chunk_size: Minimum chunk size to keep
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def extract_text_from_pdf(self, pdf_path: Path) -> tuple[List[tuple[str, int]], int]:
        """
        Extract text from PDF file with page tracking.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Tuple of (list of (text, page_number) tuples, page_count)
        """
        logger.info(f"Extracting text from: {pdf_path}")

        # Try pdfplumber first (better text extraction)
        try:
            return self._extract_with_pdfplumber(pdf_path)
        except Exception as e:
            logger.warning(f"pdfplumber failed: {e}, falling back to PyPDF2")
            return self._extract_with_pypdf2(pdf_path)

    def _extract_with_pdfplumber(self, pdf_path: Path) -> tuple[List[tuple[str, int]], int]:
        """
        Extract text using pdfplumber with page tracking.

        Returns:
            Tuple of (list of (text, page_number) tuples, page_count)
        """
        text_with_pages = []
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    text_with_pages.append((text, page_num))

        return text_with_pages, page_count

    def _extract_with_pypdf2(self, pdf_path: Path) -> tuple[List[tuple[str, int]], int]:
        """
        Extract text using PyPDF2 with page tracking.

        Returns:
            Tuple of (list of (text, page_number) tuples, page_count)
        """
        text_with_pages = []
        with open(pdf_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            page_count = len(pdf_reader.pages)

            for page_num, page in enumerate(pdf_reader.pages, start=1):
                text = page.extract_text()
                if text:
                    text_with_pages.append((text, page_num))

        return text_with_pages, page_count

    def clean_text(self, text: str) -> str:
        """
        Clean extracted text.

        Args:
            text: Raw extracted text

        Returns:
            Cleaned text
        """
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # Remove page numbers (common patterns)
        text = re.sub(r"\n\s*\d+\s*\n", "\n", text)

        # Remove headers/footers (heuristic)
        lines = text.split("\n")
        cleaned_lines = [line.strip() for line in lines if len(line.strip()) > 20]

        return "\n".join(cleaned_lines)

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences.

        Uses simple heuristic for sentence boundaries.
        """
        # Split on period, exclamation, question mark followed by space
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _create_chunk_metadata(
        self, doc_metadata: DocumentMetadata, chunk_index: int
    ) -> Dict[str, Any]:
        """Create metadata for a chunk."""
        return {
            "title": doc_metadata.title,
            "author": doc_metadata.author,
            "strategy_type": doc_metadata.strategy_type,
            "timeframe": doc_metadata.timeframe,
            "market_conditions": doc_metadata.market_conditions,
            "asset_class": doc_metadata.asset_class,
            "key_concepts": doc_metadata.key_concepts,
            "source_file": doc_metadata.source_file,
            "chunk_index": chunk_index,
            "document_type": doc_metadata.document_type,
        }

    def chunk_text_with_pages(
        self, text_with_pages: List[tuple[str, int]], metadata: DocumentMetadata
    ) -> List[DocumentChunk]:
        """
        Split page-tracked text into overlapping chunks while preserving page numbers.

        Args:
            text_with_pages: List of (text, page_number) tuples
            metadata: Document metadata

        Returns:
            List of DocumentChunk objects with page numbers tracked
        """
        # Create list of (sentence, page_number) tuples
        sentences_with_pages = []
        for page_text, page_num in text_with_pages:
            cleaned_text = self.clean_text(page_text)
            sentences = self._split_into_sentences(cleaned_text)
            for sentence in sentences:
                sentences_with_pages.append((sentence, page_num))

        chunks = []
        current_chunk = []
        current_pages = set()
        current_size = 0
        chunk_index = 0

        for sentence, page_num in sentences_with_pages:
            sentence_size = len(sentence)

            # Check if adding this sentence exceeds chunk size
            if current_size + sentence_size > self.chunk_size and current_chunk:
                # Create chunk
                chunk_text = " ".join([s for s, _ in current_chunk])
                if len(chunk_text) >= self.min_chunk_size:
                    chunks.append(
                        DocumentChunk(
                            text=chunk_text,
                            chunk_index=chunk_index,
                            metadata=self._create_chunk_metadata(metadata, chunk_index),
                            page_numbers=sorted(list(current_pages)),
                        )
                    )
                    chunk_index += 1

                # Keep overlap sentences
                overlap_size = 0
                overlap_sentences = []
                overlap_pages = set()
                for sent, pg in reversed(current_chunk):
                    if overlap_size + len(sent) < self.chunk_overlap:
                        overlap_sentences.insert(0, (sent, pg))
                        overlap_pages.add(pg)
                        overlap_size += len(sent)
                    else:
                        break

                current_chunk = overlap_sentences
                current_pages = overlap_pages
                current_size = overlap_size

            current_chunk.append((sentence, page_num))
            current_pages.add(page_num)
            current_size += sentence_size

        # Add final chunk
        if current_chunk:
            chunk_text = " ".join([s for s, _ in current_chunk])
            if len(chunk_text) >= self.min_chunk_size:
                chunks.append(
                    DocumentChunk(
                        text=chunk_text,
                        chunk_index=chunk_index,
                        metadata=self._create_chunk_metadata(metadata, chunk_index),
                        page_numbers=sorted(list(current_pages)),
                    )
                )

        logger.info(f"Created {len(chunks)} chunks from document with page tracking")
        return chunks

    def process_document(self, pdf_path: Path, metadata: DocumentMetadata) -> List[DocumentChunk]:
        """
        Process a complete document with page tracking.

        Args:
            pdf_path: Path to PDF file
            metadata: Document metadata

        Returns:
            List of processed chunks with page numbers
        """
        # Extract text with page tracking
        text_with_pages, page_count = self.extract_text_from_pdf(pdf_path)
        metadata.page_count = page_count

        # Chunk text with page tracking
        chunks = self.chunk_text_with_pages(text_with_pages, metadata)

        logger.info(f"Processed {pdf_path.name}: {page_count} pages, {len(chunks)} chunks")

        return chunks


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example metadata
    metadata = DocumentMetadata(
        title="Technical Analysis of the Financial Markets",
        author="John Murphy",
        strategy_type="technical_analysis",
        timeframe="swing_trading",
        market_conditions=["trending", "ranging"],
        asset_class=["equities"],
        key_concepts=["chart_patterns", "indicators", "trend_analysis"],
        document_type="ebook",
        source_file="technical_analysis_murphy.pdf",
    )

    processor = DocumentProcessor(chunk_size=1000, chunk_overlap=200)

    # Process document
    pdf_path = Path("data/knowledge_base/technical_analysis/sample.pdf")
    if pdf_path.exists():
        chunks = processor.process_document(pdf_path, metadata)
        print(f"Created {len(chunks)} chunks")
        print(f"First chunk: {chunks[0].text[:200]}...")
