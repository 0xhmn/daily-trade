"""
Document Ingestion Orchestrator for Multimodal RAG

Coordinates the end-to-end ingestion pipeline:
1. Extract text and images from PDFs
2. Generate image descriptions with Nova Vision
3. Generate embeddings for all content
4. Create cross-references
5. Index to OpenSearch (3 indexes)

Features checkpointing for resumable ingestion of large documents.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from .checkpoint import IngestionCheckpoint
from .cross_reference_linker import CrossReferenceLinker, FullPageImage
from .document_processor import DocumentChunk, DocumentMetadata, DocumentProcessor
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
        embedded_image_dpi: int = 300,
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
        self.embedded_image_dpi = embedded_image_dpi
        self.full_page_dpi = full_page_dpi

        # Initialize components
        self.doc_processor = DocumentProcessor(chunk_size=1000, chunk_overlap=200)

        # Two image processors: one for embedded images, one for full pages
        # using GET_DRAWINGS
        self.embedded_image_processor = ImageProcessor(
            s3_bucket=s3_bucket,
            region_name=region_name,
            extraction_method=image_extraction_method,
            dpi=embedded_image_dpi,
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
        reset_checkpoint: bool = False,
    ) -> Dict[str, Any]:
        """
        Complete end-to-end document ingestion with checkpoint support.

        Args:
            pdf_path: Path to PDF file
            metadata: Document metadata
            repository: MultimodalOpenSearchRepository instance
            reset_checkpoint: If True, ignore existing checkpoint and start fresh

        Returns:
            Dictionary with ingestion results
        """
        pdf_path = Path(pdf_path)
        pdf_dir = pdf_path.parent
        document_id = metadata.source_file.replace(".pdf", "")

        logger.info(f"Starting ingestion for: {pdf_path}")

        # Initialize checkpoint
        checkpoint = IngestionCheckpoint(pdf_path)
        if reset_checkpoint and checkpoint.checkpoint_file.exists():
            logger.info("Resetting checkpoint...")
            checkpoint.reset()

        # Display checkpoint status
        logger.info("\n" + checkpoint.get_summary())

        try:
            # Phase 1: Extract text
            if not checkpoint.is_phase_completed("extract_text"):
                logger.info("\n[Phase 1/10] Extracting text...")
                checkpoint.mark_phase_started("extract_text")
                text_chunks = self._extract_text(pdf_path, metadata)
                self._save_text_chunks(text_chunks, pdf_dir)
                checkpoint.mark_phase_completed("extract_text", {"chunks": len(text_chunks)})
            else:
                logger.info("\n[Phase 1/10] Loading text from checkpoint...")
                text_chunks = self._load_text_chunks(pdf_dir)

            # Phase 2: Extract images
            if not checkpoint.is_phase_completed("extract_images"):
                logger.info("\n[Phase 2/10] Extracting embedded images...")
                checkpoint.mark_phase_started("extract_images")
                extracted_images = self._extract_images(pdf_path, document_id, metadata, pdf_dir)
                self._save_images_manifest(extracted_images, pdf_dir, "extracted_images")
                checkpoint.mark_phase_completed("extract_images", {"images": len(extracted_images)})
            else:
                logger.info("\n[Phase 2/10] Loading images from checkpoint...")
                extracted_images = self._load_images_manifest(pdf_dir, "extracted_images")

            # Phase 3: Extract full pages
            if not checkpoint.is_phase_completed("extract_full_pages"):
                logger.info("\n[Phase 3/10] Extracting full-page images...")
                checkpoint.mark_phase_started("extract_full_pages")
                full_page_images = self._extract_full_pages(
                    pdf_path, document_id, metadata, pdf_dir
                )
                self._save_pages_manifest(full_page_images, pdf_dir)
                checkpoint.mark_phase_completed(
                    "extract_full_pages", {"pages": len(full_page_images)}
                )
            else:
                logger.info("\n[Phase 3/10] Loading full pages from checkpoint...")
                full_page_images = self._load_pages_manifest(pdf_dir)

            logger.info(
                f"\nExtracted: {len(text_chunks)} chunks, "
                f"{len(extracted_images)} images, {len(full_page_images)} pages"
            )

            # Phase 4: Describe images
            if not checkpoint.is_phase_completed("describe_images"):
                logger.info("\n[Phase 4/10] Generating image descriptions...")
                checkpoint.mark_phase_started("describe_images")
                extracted_images = self._describe_images(extracted_images)
                self._save_images_manifest(extracted_images, pdf_dir, "extracted_images")
                checkpoint.mark_phase_completed("describe_images")
            else:
                logger.info("\n[Phase 4/10] Image descriptions already completed")

            # Phase 5: Describe pages
            if not checkpoint.is_phase_completed("describe_pages"):
                logger.info("\n[Phase 5/10] Generating page descriptions...")
                checkpoint.mark_phase_started("describe_pages")
                full_page_images = self._describe_pages(full_page_images)
                self._save_pages_manifest(full_page_images, pdf_dir)
                checkpoint.mark_phase_completed("describe_pages")
            else:
                logger.info("\n[Phase 5/10] Page descriptions already completed")

            # Phase 6: Embed text chunks
            if not checkpoint.is_phase_completed("embed_text_chunks"):
                logger.info("\n[Phase 6/10] Generating text embeddings...")
                checkpoint.mark_phase_started("embed_text_chunks")
                text_chunks = self._embed_text_chunks(text_chunks)
                self._save_text_chunks(text_chunks, pdf_dir)
                checkpoint.mark_phase_completed("embed_text_chunks")
            else:
                logger.info("\n[Phase 6/10] Text embeddings already completed")

            # Phase 7: Embed images
            if not checkpoint.is_phase_completed("embed_images"):
                logger.info("\n[Phase 7/10] Generating image embeddings...")
                checkpoint.mark_phase_started("embed_images")
                extracted_images = self._embed_images(extracted_images)
                self._save_images_manifest(extracted_images, pdf_dir, "extracted_images")
                checkpoint.mark_phase_completed("embed_images")
            else:
                logger.info("\n[Phase 7/10] Image embeddings already completed")

            # Phase 8: Embed full pages
            if not checkpoint.is_phase_completed("embed_full_pages"):
                logger.info("\n[Phase 8/10] Generating page embeddings...")
                checkpoint.mark_phase_started("embed_full_pages")
                full_page_images = self._embed_full_pages(full_page_images)
                self._save_pages_manifest(full_page_images, pdf_dir)
                checkpoint.mark_phase_completed("embed_full_pages")
            else:
                logger.info("\n[Phase 8/10] Page embeddings already completed")

            # Phase 9: Cross-reference linking
            if not checkpoint.is_phase_completed("cross_reference"):
                logger.info("\n[Phase 9/10] Creating cross-references...")
                checkpoint.mark_phase_started("cross_reference")
                linked_chunks, linked_images, linked_pages = self.linker.link_content(
                    text_chunks, extracted_images, full_page_images, document_id
                )
                checkpoint.mark_phase_completed("cross_reference")
            else:
                logger.info("\n[Phase 9/10] Loading cross-referenced content...")
                # No need to re-link, just use what we have
                linked_chunks, linked_images, linked_pages = (
                    text_chunks,
                    extracted_images,
                    full_page_images,
                )

            # Phase 10: Index to OpenSearch
            if not checkpoint.is_phase_completed("index_opensearch"):
                logger.info("\n[Phase 10/10] Indexing to OpenSearch...")
                checkpoint.mark_phase_started("index_opensearch")
                index_results = self._index_to_opensearch(
                    repository, linked_chunks, linked_images, linked_pages
                )
                checkpoint.mark_phase_completed("index_opensearch")
            else:
                logger.info("\n[Phase 10/10] Already indexed to OpenSearch")
                index_results = {}

            results = {
                "document_id": document_id,
                "status": "success",
                "chunks_indexed": len(linked_chunks),
                "images_indexed": len(linked_images),
                "pages_indexed": len(linked_pages),
                "total_indexed": len(linked_chunks) + len(linked_images) + len(linked_pages),
                "index_results": index_results,
            }

            logger.info(f"\nIngestion complete: {results['total_indexed']} documents indexed")
            return results

        except Exception as e:
            logger.error(f"Ingestion failed for {pdf_path}: {e}")
            raise

    def _save_text_chunks(self, chunks: List[DocumentChunk], pdf_dir: Path):
        """Save text chunks to JSON manifest."""
        manifest_file = pdf_dir / "text_chunks.json"
        chunks_data = []
        for chunk in chunks:
            chunk_dict = {
                "text": chunk.text,
                "chunk_index": chunk.chunk_index,
                "metadata": chunk.metadata,
                "page_numbers": chunk.page_numbers,
                "text_embedding": chunk.text_embedding,
            }
            chunks_data.append(chunk_dict)

        with open(manifest_file, "w") as f:
            json.dump(chunks_data, f, indent=2)
        logger.info(f"Saved {len(chunks)} text chunks to {manifest_file}")

    def _load_text_chunks(self, pdf_dir: Path) -> List[DocumentChunk]:
        """Load text chunks from JSON manifest."""
        manifest_file = pdf_dir / "text_chunks.json"
        with open(manifest_file, "r") as f:
            chunks_data = json.load(f)

        chunks = []
        for chunk_dict in chunks_data:
            chunk = DocumentChunk(
                text=chunk_dict["text"],
                chunk_index=chunk_dict["chunk_index"],
                metadata=chunk_dict["metadata"],
                page_numbers=chunk_dict["page_numbers"],
                text_embedding=chunk_dict.get("text_embedding", []),
            )
            chunks.append(chunk)

        logger.info(f"Loaded {len(chunks)} text chunks from {manifest_file}")
        return chunks

    def _save_images_manifest(self, images: List[ExtractedImage], pdf_dir: Path, subfolder: str):
        """Save images manifest to JSON."""
        manifest_file = pdf_dir / f"{subfolder}_manifest.json"
        images_data = []
        for img in images:
            img_dict = {
                "image_id": img.image_id,
                "page_number": img.page_number,
                "bbox": list(img.bbox),
                "image_format": img.image_format,
                "width": img.width,
                "height": img.height,
                "extraction_method": img.extraction_method,
                "file_path": img.file_path,
                "file_size": img.file_size,
                "extracted_text": img.extracted_text,
                "s3_uri": img.s3_uri,
                "text_embedding": img.text_embedding,
                "multimodal_embedding": img.multimodal_embedding,
                "document_metadata": img.document_metadata,
            }
            images_data.append(img_dict)

        with open(manifest_file, "w") as f:
            json.dump(images_data, f, indent=2)
        logger.info(f"Saved {len(images)} images to {manifest_file}")

    def _load_images_manifest(self, pdf_dir: Path, subfolder: str) -> List[ExtractedImage]:
        """Load images from JSON manifest."""
        manifest_file = pdf_dir / f"{subfolder}_manifest.json"
        with open(manifest_file, "r") as f:
            images_data = json.load(f)

        images = []
        for img_dict in images_data:
            img = ExtractedImage(
                image_id=img_dict["image_id"],
                page_number=img_dict["page_number"],
                bbox=tuple(img_dict["bbox"]),
                image_format=img_dict["image_format"],
                width=img_dict["width"],
                height=img_dict["height"],
                extraction_method=img_dict["extraction_method"],
                file_path=img_dict.get("file_path"),
                extracted_text=img_dict.get("extracted_text"),
                text_embedding=img_dict.get("text_embedding", []),
                multimodal_embedding=img_dict.get("multimodal_embedding", []),
                s3_uri=img_dict.get("s3_uri", ""),
                document_metadata=img_dict.get("document_metadata", {}),
            )
            images.append(img)

        logger.info(f"Loaded {len(images)} images from {manifest_file}")
        return images

    def _save_pages_manifest(self, pages: List[FullPageImage], pdf_dir: Path):
        """Save pages manifest to JSON."""
        manifest_file = pdf_dir / "full_pages_manifest.json"
        pages_data = []
        for page in pages:
            page_dict = {
                "page_image_id": page.page_image_id,
                "page_number": page.page_number,
                "s3_uri": page.s3_uri,
                "text_description": page.text_description,
                "text_embedding": page.text_embedding,
                "multimodal_embedding": page.multimodal_embedding,
                "document_metadata": page.document_metadata,
            }
            pages_data.append(page_dict)

        with open(manifest_file, "w") as f:
            json.dump(pages_data, f, indent=2)
        logger.info(f"Saved {len(pages)} pages to {manifest_file}")

    def _load_pages_manifest(self, pdf_dir: Path) -> List[FullPageImage]:
        """Load pages from JSON manifest."""
        manifest_file = pdf_dir / "full_pages_manifest.json"
        with open(manifest_file, "r") as f:
            pages_data = json.load(f)

        pages = []
        for page_dict in pages_data:
            # Load image bytes from file if available
            image_bytes = b""
            if page_dict.get("page_image_id"):
                # Try to load from extracted full_pages directory
                image_file = (
                    pdf_dir / f"{pdf_dir.name}_full_pages" / f"{page_dict['page_image_id']}.png"
                )
                if image_file.exists():
                    image_bytes = image_file.read_bytes()

            page = FullPageImage(
                page_image_id=page_dict["page_image_id"],
                page_number=page_dict["page_number"],
                image_bytes=image_bytes,
                s3_uri=page_dict.get("s3_uri", ""),
                document_metadata=page_dict.get("document_metadata", {}),
            )
            # Restore description and embeddings from manifest
            page.text_description = page_dict.get("text_description")
            page.text_embedding = page_dict.get("text_embedding", [])
            page.multimodal_embedding = page_dict.get("multimodal_embedding", [])
            pages.append(page)

        logger.info(f"Loaded {len(pages)} pages from {manifest_file}")
        return pages

    def _extract_text(self, pdf_path: Path, metadata: DocumentMetadata) -> List:
        """Extract and chunk text from PDF."""
        return self.doc_processor.process_document(pdf_path, metadata)

    def _extract_images(
        self, pdf_path: Path, document_id: str, metadata: DocumentMetadata, pdf_dir: Path
    ) -> List[ExtractedImage]:
        """Extract embedded images from PDF and save to disk."""
        # Create output directory for images
        output_dir = pdf_dir / f"{pdf_dir.name}_extracted_images"
        images = self.embedded_image_processor.extract_images_from_pdf(
            pdf_path, document_id, output_dir
        )

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
            result = self.embedded_image_processor.batch_upload_to_s3(
                images, document_id, s3_subfolder="extracted_images", save_metadata=False
            )
            # Store S3 URIs in ExtractedImage objects
            for image in images:
                if image.image_id in result["uploaded_uris"]:
                    image.s3_uri = result["uploaded_uris"][image.image_id]

        return images

    def _extract_full_pages(
        self, pdf_path: Path, document_id: str, metadata: DocumentMetadata, pdf_dir: Path
    ) -> List[FullPageImage]:
        """Convert each PDF page to an image using ImageProcessor and save to disk."""
        # Create output directory for full page images
        output_dir = pdf_dir / f"{pdf_dir.name}_full_pages"
        images = self.full_page_processor.extract_images_from_pdf(pdf_path, document_id, output_dir)

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
                    image_bytes=image.get_image_bytes(),
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
                    image.get_image_bytes(), image.image_format.lower()
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
                    image.get_image_bytes()
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
