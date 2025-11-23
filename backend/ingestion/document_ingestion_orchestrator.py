"""
Document Ingestion Orchestrator for Multimodal RAG

Coordinates the end-to-end ingestion pipeline:
1. Extract text and images from PDFs
2. Generate image descriptions with Nova Vision
3. Generate embeddings for all content
4. Create cross-references
5. Index to OpenSearch (3 indexes)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from .cross_reference_linker import CrossReferenceLinker, FullPageImage
from .document_processor import DocumentMetadata, DocumentProcessor
from .image_processor import ExtractedImage, ExtractionMethod, ImageProcessor
from .multimodal_embedder import NovaMultimodalEmbeddingService
from .nova_vision_service import NovaVisionService

logger = logging.getLogger(__name__)


class DocumentIngestionOrchestrator:
    """
    Orchestrates the complete multimodal document ingestion pipeline.

    Pipeline:
    1. Extract text chunks (DocumentProcessor)
    2. Extract embedded images (ImageProcessor)
    3. Convert pages to full-page images (PyMuPDF)
    4. Generate image descriptions (Nova Vision)
    5. Generate text embeddings (Nova Embeddings)
    6. Generate dual embeddings for images (Nova Embeddings)
    7. Create cross-references (CrossReferenceLinker)
    8. Bulk index to OpenSearch (3 indexes)
    """

    def __init__(
        self,
        s3_bucket: str,
        region_name: str = "us-east-1",
        embedding_dimension: int = 1024,
        image_extraction_method: ExtractionMethod = ExtractionMethod.GET_DRAWINGS,
        full_page_dpi: int = 150,
    ):
        """
        Initialize ingestion orchestrator.

        Args:
            s3_bucket: S3 bucket for image storage
            opensearch_host: OpenSearch endpoint
            region_name: AWS region
            embedding_dimension: Nova embedding dimension (3072, 1024, 384, 256)
            image_extraction_method: Method for extracting embedded images (charts/diagrams)
            full_page_dpi: DPI for full-page image rendering
        """
        self.s3_bucket = s3_bucket
        self.region_name = region_name
        self.full_page_dpi = full_page_dpi

        # Initialize components
        self.doc_processor = DocumentProcessor(chunk_size=1000, chunk_overlap=200)

        # Two image processors: one for embedded images, one for full pages
        # using GET_DRAWINGS
        self.image_processor = ImageProcessor(
            s3_bucket=s3_bucket,
            region_name=region_name,
            extraction_method=image_extraction_method,
            dpi=150,
            min_file_size_kb=20.0,
            drawing_type_filter="f",
            drawing_fill_filter=(1.0, 1.0, 1.0),
        )

        self.full_page_processor = ImageProcessor(
            s3_bucket=s3_bucket,
            region_name=region_name,
            extraction_method=ExtractionMethod.GET_FULL_PAGE,
            dpi=full_page_dpi,
        )

        self.vision_service = NovaVisionService(region_name=region_name)
        self.embedder = NovaMultimodalEmbeddingService(
            embedding_dimension=embedding_dimension, region_name=region_name
        )
        self.linker = CrossReferenceLinker(spatial_threshold=0.2)

        # OpenSearch repository will be passed in during ingest
        logger.info(
            f"Initialized DocumentIngestionOrchestrator with bucket: {s3_bucket}, "
            f"embedded image method: {image_extraction_method.value}, "
            f"full page DPI: {full_page_dpi}"
        )

    async def ingest_document(
        self,
        pdf_path: Path,
        metadata: DocumentMetadata,
        repository: Any,  # MultimodalOpenSearchRepository
    ) -> Dict[str, Any]:
        """
        Complete end-to-end document ingestion.

        Args:
            pdf_path: Path to PDF file
            metadata: Document metadata
            repository: MultimodalOpenSearchRepository instance

        Returns:
            Dictionary with ingestion results
        """
        logger.info(f"Starting ingestion for: {pdf_path}")
        document_id = metadata.source_file.replace(".pdf", "")

        try:
            # Phase 1: Extract content
            logger.info("Phase 1: Extracting content...")
            text_chunks = self._extract_text(pdf_path, metadata)
            extracted_images = self._extract_images(pdf_path, document_id, metadata)
            full_page_images = self._extract_full_pages(pdf_path, document_id, metadata)

            logger.info(
                f"Extracted: {len(text_chunks)} chunks, "
                f"{len(extracted_images)} images, "
                f"{len(full_page_images)} pages"
            )

            # Phase 2: Generate image descriptions
            logger.info("Phase 2: Generating image descriptions...")
            extracted_images = self._describe_images(extracted_images, "chart")
            full_page_images = self._describe_pages(full_page_images)

            # Phase 3: Generate embeddings
            logger.info("Phase 3: Generating embeddings...")
            text_chunks = self._embed_text_chunks(text_chunks)
            extracted_images = self._embed_images(extracted_images)
            full_page_images = self._embed_full_pages(full_page_images)

            # Phase 4: Cross-reference linking
            logger.info("Phase 4: Creating cross-references...")
            linked_chunks, linked_images, linked_pages = self.linker.link_content(
                text_chunks, extracted_images, full_page_images, document_id
            )

            # Phase 5: Bulk index to OpenSearch
            logger.info("Phase 5: Indexing to OpenSearch...")
            index_results = self._index_to_opensearch(
                repository, linked_chunks, linked_images, linked_pages
            )

            results = {
                "document_id": document_id,
                "status": "success",
                "chunks_indexed": len(linked_chunks),
                "images_indexed": len(linked_images),
                "pages_indexed": len(linked_pages),
                "total_indexed": len(linked_chunks) + len(linked_images) + len(linked_pages),
                "index_results": index_results,
            }

            logger.info(f"Ingestion complete: {results['total_indexed']} documents indexed")
            return results

        except Exception as e:
            logger.error(f"Ingestion failed for {pdf_path}: {e}")
            raise

    def _extract_text(self, pdf_path: Path, metadata: DocumentMetadata) -> List:
        """Extract and chunk text from PDF."""
        return self.doc_processor.process_document(pdf_path, metadata)

    def _extract_images(
        self, pdf_path: Path, document_id: str, metadata: DocumentMetadata
    ) -> List[ExtractedImage]:
        """Extract embedded images from PDF."""
        images = self.image_processor.extract_images_from_pdf(pdf_path, document_id)

        # Set document metadata on each image
        metadata_dict = {
            "title": metadata.title,
            "author": metadata.author,
            "strategy_type": metadata.strategy_type,
            "timeframe": metadata.timeframe,
            "market_conditions": metadata.market_conditions,
            "asset_class": metadata.asset_class,
            "key_concepts": metadata.key_concepts,
            "source_file": metadata.source_file,
            "document_type": metadata.document_type,
        }

        for image in images:
            image.document_metadata = metadata_dict

        # Upload to S3 with "extracted_images" subfolder
        if images:
            result = self.image_processor.batch_upload_to_s3(
                images, document_id, s3_subfolder="extracted_images", save_metadata=False
            )
            # Store S3 URIs in ExtractedImage objects
            for image in images:
                if image.image_id in result["uploaded_uris"]:
                    image.s3_uri = result["uploaded_uris"][image.image_id]

        return images

    def _extract_full_pages(
        self, pdf_path: Path, document_id: str, metadata: DocumentMetadata
    ) -> List[FullPageImage]:
        """Convert each PDF page to an image using ImageProcessor."""
        # Extract full page images using the full_page_processor
        images = self.full_page_processor.extract_images_from_pdf(pdf_path, document_id)

        # Set document metadata dictionary
        metadata_dict = {
            "title": metadata.title,
            "author": metadata.author,
            "strategy_type": metadata.strategy_type,
            "timeframe": metadata.timeframe,
            "market_conditions": metadata.market_conditions,
            "asset_class": metadata.asset_class,
            "key_concepts": metadata.key_concepts,
            "source_file": metadata.source_file,
            "document_type": metadata.document_type,
        }

        # Upload to S3 with "full_pages" subfolder using unified method
        if images:
            result = self.full_page_processor.batch_upload_to_s3(
                images, document_id, s3_subfolder="full_pages", save_metadata=False
            )

            # Convert ExtractedImage objects to FullPageImage objects with S3 URIs and metadata
            full_pages = []
            for image in images:
                s3_uri = result["uploaded_uris"].get(image.image_id, "")
                full_page = FullPageImage(
                    page_image_id=image.image_id,
                    page_number=image.page_number,
                    image_bytes=image.image_bytes,
                    s3_uri=s3_uri,
                    document_metadata=metadata_dict,
                )
                full_pages.append(full_page)

            logger.info(f"Extracted and uploaded {len(full_pages)} full-page images")
            return full_pages

        return []

    def _describe_images(
        self, images: List[ExtractedImage], image_type: str = "chart"
    ) -> List[ExtractedImage]:
        """Generate descriptions for extracted images using Nova Vision."""
        for image in images:
            try:
                desc = self.vision_service.describe_chart(
                    image.image_bytes, image.image_format.lower()
                )
                image.extracted_text = desc["description"]
            except Exception as e:
                logger.error(f"Failed to describe image {image.image_id}: {e}")
                image.extracted_text = "Chart or diagram from trading document"

        return images

    def _describe_pages(self, pages: List[FullPageImage]) -> List[FullPageImage]:
        """Generate descriptions for full page images using Nova Vision."""
        for page in pages:
            try:
                desc = self.vision_service.describe_page(page.image_bytes, "png", page.page_number)
                page.text_description = desc["description"]
            except Exception as e:
                logger.error(f"Failed to describe page {page.page_number}: {e}")
                page.text_description = f"Page {page.page_number} from trading document"

        return pages

    def _embed_text_chunks(self, chunks: List) -> List:
        """Generate text embeddings for chunks."""
        for chunk in chunks:
            try:
                chunk.text_embedding = self.embedder.generate_text_embedding(chunk.text)
            except Exception as e:
                logger.error(f"Failed to embed chunk {chunk.chunk_index}: {e}")
                raise

        return chunks

    def _embed_images(self, images: List[ExtractedImage]) -> List[ExtractedImage]:
        """Generate dual embeddings (text + multimodal) for extracted images."""
        for image in images:
            try:
                # Text embedding from description
                if image.extracted_text:
                    image.text_embedding = self.embedder.generate_text_embedding(
                        image.extracted_text
                    )

                # Multimodal embedding from image bytes
                image.multimodal_embedding = self.embedder.generate_image_embedding(
                    image.image_bytes
                )

            except Exception as e:
                logger.error(f"Failed to embed image {image.image_id}: {e}")
                raise

        return images

    def _embed_full_pages(self, pages: List[FullPageImage]) -> List[FullPageImage]:
        """Generate dual embeddings (text + multimodal) for full page images."""
        for page in pages:
            try:
                # Text embedding from description
                if page.text_description:
                    page.text_embedding = self.embedder.generate_text_embedding(
                        page.text_description
                    )

                # Multimodal embedding from page image
                page.multimodal_embedding = self.embedder.generate_image_embedding(page.image_bytes)

            except Exception as e:
                logger.error(f"Failed to embed page {page.page_number}: {e}")
                raise

        return pages

    def _index_to_opensearch(
        self, repository: Any, chunks: List, images: List, pages: List
    ) -> Dict[str, Any]:
        """
        Bulk index all content to OpenSearch.

        Repository handles conversion from dataclasses to dictionaries.
        """
        results = {}

        try:
            # Pass dataclasses directly - repository handles conversion
            chunk_result = repository.bulk_index_text_chunks(chunks)
            results["text_chunks"] = chunk_result

            image_result = repository.bulk_index_extracted_images(images)
            results["extracted_images"] = image_result

            page_result = repository.bulk_index_full_page_images(pages)
            results["full_page_images"] = page_result

            return results

        except Exception as e:
            logger.error(f"Failed to index to OpenSearch: {e}")
            raise


# Example usage
if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)

    from ..repositories.multimodal_opensearch_repository import MultimodalOpenSearchRepository

    async def main():
        # Initialize orchestrator
        orchestrator = DocumentIngestionOrchestrator(
            s3_bucket="daily-trade-images",
            region_name="us-east-1",
            embedding_dimension=1024,
        )

        # Initialize repository
        repository = MultimodalOpenSearchRepository(
            host="localhost:9200", use_ssl=False, verify_certs=False
        )

        # Create indexes
        repository.create_indexes()

        # Example metadata
        metadata = DocumentMetadata(
            title="Technical Analysis of the Financial Markets",
            author="John Murphy",
            strategy_type="technical_analysis",
            timeframe="swing_trading",
            market_conditions=["trending", "ranging"],
            asset_class=["equities"],
            key_concepts=["chart_patterns", "indicators"],
            document_type="ebook",
            source_file="technical_analysis_murphy.pdf",
        )

        # Ingest document
        pdf_path = Path("data/knowledge_base/technical_analysis/sample.pdf")
        if pdf_path.exists():
            results = await orchestrator.ingest_document(pdf_path, metadata, repository)
            print(f"\nIngestion Results:")
            print(f"  Text chunks: {results['chunks_indexed']}")
            print(f"  Images: {results['images_indexed']}")
            print(f"  Pages: {results['pages_indexed']}")
            print(f"  Total: {results['total_indexed']}")

    asyncio.run(main())
