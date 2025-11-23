"""
Cross-Reference Linker for Multimodal RAG

Links text chunks, extracted images, and full page images based on:
- Page number proximity
- Spatial bbox overlap
- Content relationships
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from .document_processor import DocumentChunk
from .image_processor import ExtractedImage

logger = logging.getLogger(__name__)


class FullPageImage:
    """Represents a full page image."""

    def __init__(
        self,
        page_image_id: str,
        page_number: int,
        image_bytes: bytes,
        s3_uri: str,
        document_metadata: Optional[Dict[str, Any]] = None,
    ):
        self.page_image_id = page_image_id
        self.page_number = page_number
        self.image_bytes = image_bytes
        self.s3_uri = s3_uri
        self.text_description = ""
        self.text_embedding = []
        self.multimodal_embedding = []
        self.text_chunk_ids = []
        self.extracted_image_ids = []
        self.document_metadata = document_metadata if document_metadata else {}


class CrossReferenceLinker:
    """
    Creates cross-references between text chunks, extracted images, and full pages.

    Linking Strategy:
    - Text chunks → Images on same page
    - Images → Text chunks on same page (with bbox proximity)
    - Everything → Its full page
    - Full pages → All content on that page
    """

    def __init__(self, spatial_threshold: float = 0.2):
        """
        Initialize cross-reference linker.

        Args:
            spatial_threshold: Minimum bbox overlap ratio to consider spatial proximity
        """
        self.spatial_threshold = spatial_threshold
        logger.info(f"Initialized CrossReferenceLinker with threshold={spatial_threshold}")

    def link_content(
        self,
        text_chunks: List[DocumentChunk],
        extracted_images: List[ExtractedImage],
        full_page_images: List[FullPageImage],
        document_id: str,
    ) -> Tuple[List[DocumentChunk], List[ExtractedImage], List[FullPageImage]]:
        """
        Create cross-references between all content types.

        Args:
            text_chunks: List of text chunks
            extracted_images: List of extracted images
            full_page_images: List of full page images
            document_id: Document identifier

        Returns:
            Tuple of (linked_chunks, linked_images, linked_pages)
        """
        logger.info(
            f"Linking content: {len(text_chunks)} chunks, "
            f"{len(extracted_images)} images, {len(full_page_images)} pages"
        )

        # Create lookup maps by page
        chunks_by_page = self._group_by_page(text_chunks)
        images_by_page = self._group_by_page(extracted_images)

        # 1. Link text chunks to nearby images and full page
        for chunk in text_chunks:
            chunk.related_extracted_image_ids = self._find_images_on_page(
                chunk.page_numbers[0] if chunk.page_numbers else 0, images_by_page
            )
            chunk.full_page_image_id = self._generate_page_id(
                document_id, chunk.page_numbers[0] if chunk.page_numbers else 0
            )

        # 2. Link extracted images to nearby text chunks and full page
        for image in extracted_images:
            image.related_text_chunk_ids = self._find_chunks_on_page(
                image.page_number, chunks_by_page
            )
            image.full_page_image_id = self._generate_page_id(document_id, image.page_number)

        # 3. Link full pages to their content
        for page in full_page_images:
            page.text_chunk_ids = self._find_chunks_on_page(page.page_number, chunks_by_page)
            page.extracted_image_ids = self._find_images_on_page(page.page_number, images_by_page)

        logger.info("Cross-reference linking completed")
        return text_chunks, extracted_images, full_page_images

    def _group_by_page(self, items: List) -> Dict[int, List]:
        """
        Group items by page number.

        Handles both single page_number and list page_numbers attributes.
        For items spanning multiple pages, they appear in all relevant page groups.
        """
        grouped = {}
        for item in items:
            pages = []

            if hasattr(item, "page_numbers"):
                # Text chunks have page_numbers list
                if item.page_numbers:
                    pages = item.page_numbers
                else:
                    # Fallback: if empty, skip this item (shouldn't happen with new code)
                    logger.warning(f"Item has empty page_numbers, skipping: {item}")
                    continue
            elif hasattr(item, "page_number"):
                # Images and full pages have single page_number
                pages = [item.page_number]
            else:
                logger.warning(f"Item has no page information, skipping: {item}")
                continue

            # Add item to all its pages
            for page in pages:
                if page not in grouped:
                    grouped[page] = []
                grouped[page].append(item)

        return grouped

    def _find_images_on_page(self, page_number: int, images_by_page: Dict) -> List[str]:
        """Find image IDs on a specific page."""
        images = images_by_page.get(page_number, [])
        return [img.image_id for img in images]

    def _find_chunks_on_page(self, page_number: int, chunks_by_page: Dict) -> List[str]:
        """Find chunk IDs on a specific page."""
        chunks = chunks_by_page.get(page_number, [])
        return [
            f"{chunk.metadata.get('source_file', 'doc')}_{chunk.chunk_index}" for chunk in chunks
        ]

    def _generate_page_id(self, document_id: str, page_number: int) -> str:
        """Generate full page image ID."""
        return f"{document_id}_fullpage_p{page_number:04d}"

    def _calculate_bbox_overlap(
        self, bbox1: Tuple[float, float, float, float], bbox2: Tuple[float, float, float, float]
    ) -> float:
        """
        Calculate overlap ratio between two bounding boxes.

        Args:
            bbox1: (x0, y0, x1, y1) first bbox
            bbox2: (x0, y0, x1, y1) second bbox

        Returns:
            Overlap ratio (0.0 to 1.0)
        """
        # Calculate intersection
        x_left = max(bbox1[0], bbox2[0])
        y_top = max(bbox1[1], bbox2[1])
        x_right = min(bbox1[2], bbox2[2])
        y_bottom = min(bbox1[3], bbox2[3])

        if x_right < x_left or y_bottom < y_top:
            return 0.0

        intersection_area = (x_right - x_left) * (y_bottom - y_top)

        # Calculate areas
        bbox1_area = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        bbox2_area = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])

        # Return ratio of intersection to smaller bbox
        smaller_area = min(bbox1_area, bbox2_area)
        if smaller_area == 0:
            return 0.0

        return intersection_area / smaller_area


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example: Link content from a document
    linker = CrossReferenceLinker(spatial_threshold=0.2)

    # Mock data
    text_chunks = []  # Would come from DocumentProcessor
    extracted_images = []  # Would come from ImageProcessor
    full_page_images = []  # Would be generated

    # Link everything
    linked_chunks, linked_images, linked_pages = linker.link_content(
        text_chunks, extracted_images, full_page_images, document_id="test_doc"
    )

    print(f"Linked {len(linked_chunks)} chunks")
    print(f"Linked {len(linked_images)} images")
    print(f"Linked {len(linked_pages)} pages")
