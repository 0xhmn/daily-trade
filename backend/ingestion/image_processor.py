"""
Image Processor for Trading Knowledge Base

Handles image extraction from PDFs using PyMuPDF, position tracking, and S3 storage.
"""

import base64
import hashlib
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import boto3
import fitz
from botocore.exceptions import ClientError
from PIL import Image

logger = logging.getLogger(__name__)


class ExtractionMethod(Enum):
    """Image extraction methods supported by PyMuPDF."""

    GET_IMAGES = "get_images"  # Extract embedded raster images
    GET_SVG_IMAGE = "get_svg_image"  # Extract vector graphics as SVG
    GET_DRAWINGS = "get_drawings"  # Extract vector drawings with filters


@dataclass
class ExtractedImage:
    """Represents an image extracted from a PDF."""

    image_id: str
    page_number: int
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    image_bytes: bytes
    image_format: str  # PNG, JPEG, SVG, etc.
    width: int
    height: int
    extraction_method: str  # Which method was used
    extracted_text: Optional[str] = None  # OCR text if present
    file_size: int = 0
    drawing_metadata: Optional[Dict[str, Any]] = None  # Metadata from get_drawings()

    def __post_init__(self):
        """Calculate file size after initialization."""
        self.file_size = len(self.image_bytes)


@dataclass
class ImageAnalysis:
    """Analysis results from Claude vision model."""

    description: str
    image_type: str  # chart, diagram, table, screenshot, illustration
    technical_elements: List[str]  # RSI, MACD, support_level, etc.
    confidence_score: float
    extracted_text: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageReference:
    """Reference to an image with its analysis and storage location."""

    image_id: str
    s3_uri: str
    page_number: int
    position_in_page: Tuple[float, float]  # (x, y) center coordinates
    bbox: Tuple[float, float, float, float]
    description: str
    analysis: Optional[ImageAnalysis] = None
    related_chunk_ids: List[str] = field(default_factory=list)


class ImageProcessor:
    """
    Service for extracting and processing images from PDFs using PyMuPDF.

    Features:
    - Multiple extraction methods (embedded images, SVG, vector drawings)
    - Image deduplication
    - S3 storage management
    - Image format conversion
    - Size optimization
    """

    def __init__(
        self,
        s3_bucket: Optional[str] = None,
        region_name: str = "us-east-1",
        extraction_method: ExtractionMethod = ExtractionMethod.GET_IMAGES,
        min_image_width: int = 100,
        min_image_height: int = 100,
        max_image_size_mb: int = 5,
        dpi: int = 150,
        # GET_DRAWINGS filters
        min_file_size_kb: float = 20.0,
        drawing_type_filter: Optional[str] = "f",
        drawing_fill_filter: Optional[tuple[float, float, float]] = None,
    ):
        """
        Initialize image processor.

        Args:
            s3_bucket: S3 bucket name for image storage
            region_name: AWS region
            extraction_method: Method to use for image extraction
            min_image_width: Minimum width to consider (filters tiny images)
            min_image_height: Minimum height to consider
            max_image_size_mb: Maximum image size in MB
            dpi: DPI for rendering drawings
            min_file_size_kb: Minimum file size in KB for GET_DRAWINGS (default: 20.0)
            drawing_type_filter: Drawing type filter for GET_DRAWINGS (default: 'f')
            drawing_fill_filter: Drawing fill color filter for GET_DRAWINGS (default: [1.0, 1.0, 1.0])
        """
        self.s3_bucket = s3_bucket
        self.region_name = region_name
        self.extraction_method = extraction_method
        self.min_image_width = min_image_width
        self.min_image_height = min_image_height
        self.max_image_size_bytes = max_image_size_mb * 1024 * 1024
        self.dpi = dpi

        # GET_DRAWINGS specific filters
        self.min_file_size_kb = min_file_size_kb
        self.drawing_type_filter = drawing_type_filter
        self.drawing_fill_filter = drawing_fill_filter if drawing_fill_filter else [1.0, 1.0, 1.0]

        # Initialize S3 client if bucket provided
        self.s3_client = None
        if s3_bucket:
            self.s3_client = boto3.client("s3", region_name=region_name)

        logger.info(
            f"Initialized ImageProcessor with bucket: {s3_bucket}, "
            f"method: {extraction_method.value}, "
            f"min size: {min_image_width}x{min_image_height}, "
            f"DPI: {dpi}"
        )

    def extract_images_from_pdf(self, pdf_path: Path, document_id: str) -> List[ExtractedImage]:
        """
        Extract all images from a PDF with position metadata.

        Args:
            pdf_path: Path to PDF file
            document_id: Unique document identifier for image naming

        Returns:
            List of ExtractedImage objects
        """
        logger.info(f"Extracting images from: {pdf_path} using {self.extraction_method.value}")
        extracted_images = []
        seen_hashes = set()  # For deduplication

        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)

            for page_num in range(total_pages):
                page = doc[page_num]
                page_images = self._extract_images_from_page(
                    page, page_num + 1, document_id, seen_hashes
                )
                extracted_images.extend(page_images)

            doc.close()

            logger.info(
                f"Extracted {len(extracted_images)} images from {total_pages} pages "
                f"using {self.extraction_method.value}"
            )

        except Exception as e:
            logger.error(f"Failed to extract images from {pdf_path}: {e}")
            raise

        return extracted_images

    def _extract_images_from_page(
        self,
        page: fitz.Page,
        page_num: int,
        document_id: str,
        seen_hashes: set,
    ) -> List[ExtractedImage]:
        """
        Extract images from a single PDF page using configured method.

        Args:
            page: PyMuPDF page object
            page_num: Page number (1-indexed)
            document_id: Document identifier
            seen_hashes: Set of image hashes for deduplication

        Returns:
            List of ExtractedImage objects
        """
        if self.extraction_method == ExtractionMethod.GET_IMAGES:
            return self._extract_with_get_images(page, page_num, document_id, seen_hashes)
        elif self.extraction_method == ExtractionMethod.GET_SVG_IMAGE:
            return self._extract_with_get_svg_image(page, page_num, document_id, seen_hashes)
        elif self.extraction_method == ExtractionMethod.GET_DRAWINGS:
            return self._extract_with_get_drawings(page, page_num, document_id, seen_hashes)
        else:
            logger.warning(f"Unknown extraction method: {self.extraction_method}")
            return []

    def _extract_with_get_images(
        self, page: fitz.Page, page_num: int, document_id: str, seen_hashes: set
    ) -> List[ExtractedImage]:
        """Extract embedded raster images using get_images()."""
        page_images = []

        try:
            image_list = page.get_images(full=True)

            for img_idx, img in enumerate(image_list):
                try:
                    xref = img[0]  # Image XREF number

                    # page.parent is the document object
                    if not page.parent:
                        logger.warning(f"Page {page_num} has no parent document")
                        continue

                    base_image = page.parent.extract_image(xref)

                    image_bytes = base_image["image"]
                    image_format = base_image["ext"].upper()  # png, jpeg, etc.

                    # Get image info
                    pix = fitz.Pixmap(page.parent, xref)
                    width = pix.width
                    height = pix.height

                    # Filter tiny images
                    if width < self.min_image_width or height < self.min_image_height:
                        logger.debug(f"Skipping small image on page {page_num}: {width}x{height}")
                        pix = None
                        continue

                    # Get bbox (position on page)
                    img_rects = page.get_image_rects(xref)
                    if img_rects:
                        rect = img_rects[0]  # First occurrence
                        bbox = (rect.x0, rect.y0, rect.x1, rect.y1)
                    else:
                        # Default to full page if bbox not found
                        bbox = (0, 0, page.rect.width, page.rect.height)

                    # Check size limit
                    if len(image_bytes) > self.max_image_size_bytes:
                        logger.warning(
                            f"Image on page {page_num} exceeds size limit: "
                            f"{len(image_bytes) / 1024 / 1024:.2f}MB"
                        )
                        pix = None
                        continue

                    # Deduplicate
                    img_hash = hashlib.md5(image_bytes).hexdigest()
                    if img_hash in seen_hashes:
                        logger.debug(f"Skipping duplicate image on page {page_num}")
                        pix = None
                        continue
                    seen_hashes.add(img_hash)

                    # Create ExtractedImage
                    image_id = self._generate_image_id(document_id, page_num, img_idx)

                    extracted_img = ExtractedImage(
                        image_id=image_id,
                        page_number=page_num,
                        bbox=bbox,
                        image_bytes=image_bytes,
                        image_format=image_format,
                        width=width,
                        height=height,
                        extraction_method="get_images",
                    )

                    page_images.append(extracted_img)
                    logger.debug(
                        f"Extracted image {image_id}: {width}x{height}px, "
                        f"{len(image_bytes) / 1024:.1f}KB"
                    )

                    pix = None  # Clean up

                except Exception as e:
                    logger.warning(f"Failed to extract image {img_idx} from page {page_num}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Failed to get images from page {page_num}: {e}")

        return page_images

    def _extract_with_get_svg_image(
        self, page: fitz.Page, page_num: int, document_id: str, seen_hashes: set
    ) -> List[ExtractedImage]:
        """Extract vector graphics as SVG using get_svg_image()."""
        page_images = []

        try:
            # Get SVG representation of page
            svg_text = page.get_svg_image()
            svg_bytes = svg_text.encode("utf-8")

            # Check size
            if len(svg_bytes) > self.max_image_size_bytes:
                logger.warning(
                    f"Page {page_num} SVG exceeds size limit: "
                    f"{len(svg_bytes) / 1024 / 1024:.2f}MB"
                )
                return page_images

            # Deduplicate
            img_hash = hashlib.md5(svg_bytes).hexdigest()
            if img_hash in seen_hashes:
                logger.debug(f"Skipping duplicate SVG for page {page_num}")
                return page_images
            seen_hashes.add(img_hash)

            # Create ExtractedImage
            image_id = self._generate_image_id(document_id, page_num, 0)

            extracted_img = ExtractedImage(
                image_id=image_id,
                page_number=page_num,
                bbox=(0, 0, page.rect.width, page.rect.height),
                image_bytes=svg_bytes,
                image_format="SVG",
                width=int(page.rect.width),
                height=int(page.rect.height),
                extraction_method="get_svg_image",
            )

            page_images.append(extracted_img)
            logger.debug(f"Extracted SVG for page {page_num}: {len(svg_bytes) / 1024:.1f}KB")

        except Exception as e:
            logger.warning(f"Failed to extract SVG from page {page_num}: {e}")

        return page_images

    def _extract_with_get_drawings(
        self, page: fitz.Page, page_num: int, document_id: str, seen_hashes: set
    ) -> List[ExtractedImage]:
        """Extract vector drawings using page.get_drawings() with filters."""
        page_images = []

        try:
            drawings = page.get_drawings()

            for draw_idx, drawing in enumerate(drawings):
                try:
                    # Get bounding rect for this drawing
                    rect = drawing.get("rect")
                    if not rect:
                        logger.debug(f"Drawing {draw_idx} on page {page_num}: No rect")

                    # Convert rect to fitz.Rect
                    draw_rect = fitz.Rect(rect)

                    # Add small padding to capture the drawing fully
                    padding = 5
                    draw_rect.x0 = max(0, draw_rect.x0 - padding)
                    draw_rect.y0 = max(0, draw_rect.y0 - padding)
                    draw_rect.x1 = min(page.rect.width, draw_rect.x1 + padding)
                    draw_rect.y1 = min(page.rect.height, draw_rect.y1 + padding)

                    # Skip tiny drawings
                    if draw_rect.width < 10 or draw_rect.height < 10:
                        logger.debug(
                            f"Drawing {draw_idx} on page {page_num}: Too small "
                            f"({draw_rect.width:.1f}x{draw_rect.height:.1f}), skipping"
                        )
                        continue

                    # Render drawing region at specified DPI
                    mat = fitz.Matrix(self.dpi / 72, self.dpi / 72)
                    pix = page.get_pixmap(matrix=mat, clip=draw_rect, alpha=False)
                    image_bytes = pix.tobytes("png")
                    file_size_kb = len(image_bytes) / 1024

                    # Apply file size filter
                    if file_size_kb < self.min_file_size_kb:
                        logger.debug(
                            f"Drawing {draw_idx} on page {page_num}: File too small "
                            f"({file_size_kb:.1f}KB < {self.min_file_size_kb}KB), skipping"
                        )
                        pix = None
                        continue

                    # Apply drawing type filter
                    drawing_type = drawing.get("type", "")
                    if self.drawing_type_filter and drawing_type != self.drawing_type_filter:
                        logger.debug(
                            f"Drawing {draw_idx} on page {page_num}: Type mismatch "
                            f"('{drawing_type}' != '{self.drawing_type_filter}'), skipping"
                        )
                        pix = None
                        continue

                    # Apply fill color filter
                    fill_color = drawing.get("fill")
                    if self.drawing_fill_filter and fill_color != self.drawing_fill_filter:
                        logger.debug(
                            f"Drawing {draw_idx} on page {page_num}: Fill color mismatch "
                            f"({fill_color} != {self.drawing_fill_filter}), skipping"
                        )
                        pix = None
                        continue

                    # Deduplicate
                    img_hash = hashlib.md5(image_bytes).hexdigest()
                    if img_hash in seen_hashes:
                        logger.debug(f"Skipping duplicate drawing on page {page_num}")
                        pix = None
                        continue
                    seen_hashes.add(img_hash)

                    # Create ExtractedImage for this drawing
                    image_id = self._generate_image_id(document_id, page_num, draw_idx)
                    extracted_img = ExtractedImage(
                        image_id=image_id,
                        page_number=page_num,
                        bbox=(draw_rect.x0, draw_rect.y0, draw_rect.x1, draw_rect.y1),
                        image_bytes=image_bytes,
                        image_format="PNG",
                        width=pix.width,
                        height=pix.height,
                        extraction_method="get_drawings",
                    )

                    # Store drawing metadata
                    extracted_img.drawing_metadata = {
                        "type": drawing.get("type"),
                        "fill": drawing.get("fill"),
                        "color": drawing.get("color"),
                        "width": drawing.get("width"),
                        "closePath": drawing.get("closePath"),
                        "even_odd": drawing.get("even_odd"),
                        "items_count": len(drawing.get("items", [])),
                    }

                    page_images.append(extracted_img)
                    logger.debug(
                        f"Extracted drawing {image_id}: {pix.width}x{pix.height}px, "
                        f"{file_size_kb:.1f}KB, type={drawing.get('type', 'N/A')}"
                    )

                    pix = None  # Clean up

                except Exception as e:
                    logger.warning(
                        f"Failed to extract drawing {draw_idx} from page {page_num}: {e}"
                    )
                    continue

        except Exception as e:
            logger.warning(f"Failed to get drawings from page {page_num}: {e}")

        return page_images

    def _generate_image_id(self, document_id: str, page_num: int, image_idx: int) -> str:
        """
        Generate unique image identifier.

        Args:
            document_id: Document identifier
            page_num: Page number
            image_idx: Image index on page

        Returns:
            Unique image ID
        """
        return f"{document_id}_p{page_num:04d}_img{image_idx:03d}"

    def save_images_locally(
        self,
        images: List[ExtractedImage],
        output_dir: Path,
        document_id: str,
        save_metadata: bool = True,
    ) -> Dict[str, Any]:
        """
        Save extracted images to local directory with optional metadata.

        Args:
            images: List of ExtractedImage objects
            output_dir: Directory to save images
            document_id: Document identifier for metadata file
            save_metadata: Whether to save metadata JSON file

        Returns:
            Dictionary with save results
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []
        metadata_list = []

        for img in images:
            try:
                file_path = output_dir / f"{img.image_id}.{img.image_format.lower()}"
                file_path.write_bytes(img.image_bytes)
                saved_files.append(str(file_path))
                logger.debug(f"Saved: {file_path}")

                # Collect metadata
                metadata = {
                    "image_id": img.image_id,
                    "filename": f"{img.image_id}.{img.image_format.lower()}",
                    "page_number": img.page_number,
                    "bbox": {
                        "x0": img.bbox[0],
                        "y0": img.bbox[1],
                        "x1": img.bbox[2],
                        "y1": img.bbox[3],
                    },
                    "width": img.width,
                    "height": img.height,
                    "format": img.image_format,
                    "file_size_bytes": img.file_size,
                    "file_size_kb": round(img.file_size / 1024, 2),
                    "extraction_method": img.extraction_method,
                    "drawing_attributes": img.drawing_metadata if img.drawing_metadata else {},
                }
                metadata_list.append(metadata)

            except Exception as e:
                logger.error(f"Failed to save {img.image_id}: {e}")

        # Save metadata JSON file with timestamp in current working directory
        metadata_file = None
        if save_metadata and metadata_list:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            cwd = Path.cwd()
            metadata_file = cwd / f"{document_id}_metadata_{timestamp}.json"
            metadata_output = {
                "document_id": document_id,
                "timestamp": timestamp,
                "total_images_extracted": len(images),
                "images_saved": len(saved_files),
                "extraction_method": self.extraction_method.value,
                "output_directory": str(output_dir.absolute()),
                "images": metadata_list,
            }

            try:
                with open(metadata_file, "w") as f:
                    json.dump(metadata_output, f, indent=2)
                logger.info(f"Saved metadata: {metadata_file}")
            except Exception as e:
                logger.error(f"Failed to save metadata: {e}")

        logger.info(f"Saved {len(saved_files)}/{len(images)} images to {output_dir.absolute()}")

        return {
            "saved_files": saved_files,
            "metadata_file": str(metadata_file) if metadata_file else None,
            "output_dir": str(output_dir.absolute()),
        }

    def upload_to_s3(
        self, image: ExtractedImage, document_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Upload image to S3 bucket organized by document_id.

        Args:
            image: ExtractedImage object
            document_id: Document identifier to use as S3 prefix (extracts from image_id if not provided)

        Returns:
            S3 URI (s3://bucket/key) or None if upload fails
        """
        if not self.s3_client or not self.s3_bucket:
            logger.warning("S3 client not initialized, skipping upload")
            return None

        try:
            # Extract document_id from image_id if not provided
            if document_id is None:
                # image_id format: {document_id}_p{page_num:04d}_img{image_idx:03d}
                document_id = image.image_id.split("_p")[0]

            # Create S3 key with document_id as prefix for better organization
            s3_key = f"images/{document_id}/{image.image_id}.{image.image_format.lower()}"

            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=image.image_bytes,
                ContentType=f"image/{image.image_format.lower()}",
                Metadata={
                    "page_number": str(image.page_number),
                    "width": str(image.width),
                    "height": str(image.height),
                    "image_id": image.image_id,
                    "extraction_method": image.extraction_method,
                },
            )

            s3_uri = f"s3://{self.s3_bucket}/{s3_key}"
            logger.debug(f"Uploaded image to S3: {s3_uri}")
            return s3_uri

        except ClientError as e:
            logger.error(f"Failed to upload image {image.image_id} to S3: {e}")
            return None

    def batch_upload_to_s3(
        self,
        images: List[ExtractedImage],
        document_id: Optional[str] = None,
        save_metadata: bool = True,
    ) -> Dict[str, Any]:
        """
        Upload multiple images to S3 organized by document_id with optional metadata file.

        Args:
            images: List of ExtractedImage objects
            document_id: Document identifier to use as S3 prefix (extracts from image_id if not provided)
            save_metadata: Whether to save metadata JSON file to current working directory

        Returns:
            Dictionary with upload results and metadata file path
        """
        uploaded = {}

        for image in images:
            s3_uri = self.upload_to_s3(image, document_id)
            if s3_uri:
                uploaded[image.image_id] = s3_uri

        logger.info(f"Uploaded {len(uploaded)}/{len(images)} images to S3 bucket: {self.s3_bucket}")

        # Save metadata JSON file with timestamp in current working directory
        metadata_file = None
        if save_metadata and uploaded:
            if document_id is None and images:
                document_id = images[0].image_id.split("_p")[0]

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            cwd = Path.cwd()
            metadata_file = cwd / f"{document_id}_s3_metadata_{timestamp}.json"

            # Collect metadata for uploaded images
            metadata_list = []
            for img in images:
                if img.image_id in uploaded:
                    metadata = {
                        "image_id": img.image_id,
                        "s3_uri": uploaded[img.image_id],
                        "page_number": img.page_number,
                        "bbox": {
                            "x0": img.bbox[0],
                            "y0": img.bbox[1],
                            "x1": img.bbox[2],
                            "y1": img.bbox[3],
                        },
                        "width": img.width,
                        "height": img.height,
                        "format": img.image_format,
                        "file_size_bytes": img.file_size,
                        "file_size_kb": round(img.file_size / 1024, 2),
                        "extraction_method": img.extraction_method,
                        "drawing_attributes": img.drawing_metadata if img.drawing_metadata else {},
                    }
                    metadata_list.append(metadata)

            metadata_output = {
                "document_id": document_id,
                "timestamp": timestamp,
                "s3_bucket": self.s3_bucket,
                "total_images_extracted": len(images),
                "images_uploaded": len(uploaded),
                "extraction_method": self.extraction_method.value,
                "images": metadata_list,
            }

            try:
                with open(metadata_file, "w") as f:
                    json.dump(metadata_output, f, indent=2)
                logger.info(f"Saved S3 upload metadata: {metadata_file}")
            except Exception as e:
                logger.error(f"Failed to save S3 metadata: {e}")

        return {
            "uploaded_uris": uploaded,
            "metadata_file": str(metadata_file) if metadata_file else None,
        }

    def get_image_base64(self, image: ExtractedImage) -> str:
        """
        Convert image to base64 string for API calls.

        Args:
            image: ExtractedImage object

        Returns:
            Base64 encoded image string
        """
        return base64.b64encode(image.image_bytes).decode("utf-8")

    def optimize_image(
        self, image: ExtractedImage, max_width: int = 1024, max_height: int = 1024
    ) -> ExtractedImage:
        """
        Optimize image size for API transmission.
        Only works for raster images (PNG, JPEG), not SVG.

        Args:
            image: ExtractedImage object
            max_width: Maximum width
            max_height: Maximum height

        Returns:
            Optimized ExtractedImage
        """
        # Skip SVG images
        if image.image_format.upper() == "SVG":
            return image

        try:
            # Load image
            img = Image.open(io.BytesIO(image.image_bytes))

            # Check if resize needed
            if img.width > max_width or img.height > max_height:
                # Calculate new size maintaining aspect ratio
                img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

                # Convert back to bytes
                buffer = io.BytesIO()
                img.save(buffer, format=image.image_format)
                optimized_bytes = buffer.getvalue()

                logger.debug(
                    f"Optimized image {image.image_id}: "
                    f"{image.width}x{image.height} -> {img.width}x{img.height}, "
                    f"{len(image.image_bytes) / 1024:.1f}KB -> "
                    f"{len(optimized_bytes) / 1024:.1f}KB"
                )

                return ExtractedImage(
                    image_id=image.image_id,
                    page_number=image.page_number,
                    bbox=image.bbox,
                    image_bytes=optimized_bytes,
                    image_format=image.image_format,
                    width=img.width,
                    height=img.height,
                    extraction_method=image.extraction_method,
                    extracted_text=image.extracted_text,
                )

            return image

        except Exception as e:
            logger.warning(f"Failed to optimize image {image.image_id}: {e}")
            return image


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    pdf_path = Path("data/sample_data/4_page_with_image.pdf")
    document_id = "4_page_with_image"
    save_locally = True  # Set to True to save locally, False for S3
    output_dir = Path("backend/ingestion/tmp")

    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        print("Please ensure the test PDF exists")
        exit(1)

    print(f"\n{'='*60}")
    print(f"Testing GET_DRAWINGS extraction method")
    print(f"{'='*60}")

    # Initialize processor with GET_DRAWINGS method
    processor = ImageProcessor(
        s3_bucket="daily-trade-images-560271561561" if not save_locally else None,
        extraction_method=ExtractionMethod.GET_DRAWINGS,
        dpi=150,
        min_file_size_kb=20.0,
        drawing_type_filter="f",
        drawing_fill_filter=(1.0, 1.0, 1.0),
    )

    try:
        # Extract images
        images = processor.extract_images_from_pdf(pdf_path, document_id)
        print(f"\nExtracted {len(images)} images")

        # Display extracted images
        for img in images:
            drawing_attrs = img.drawing_metadata if img.drawing_metadata else {}
            print(
                f"  {img.image_id}: Page {img.page_number}, "
                f"{img.width}x{img.height}px, {img.file_size / 1024:.1f}KB, "
                f"type: {drawing_attrs.get('type', 'N/A')}"
                f"type: {drawing_attrs.get('fill', 'N/A')}"
            )

        # Save results
        if images:
            if save_locally:
                print(f"\nSaving {len(images)} images locally...")
                result = processor.save_images_locally(images, output_dir, document_id)
                print(f"\nSaved to: {result['output_dir']}")
                print(f"Metadata file: {result['metadata_file']}")
            else:
                print(f"\nUploading {len(images)} images to S3...")
                result = processor.batch_upload_to_s3(images, document_id)
                uploaded_uris = result["uploaded_uris"]
                print(f"\nSuccessfully uploaded {len(uploaded_uris)}/{len(images)} images")
                for image_id, s3_uri in list(uploaded_uris.items())[:5]:  # Show first 5
                    print(f"  {image_id} -> {s3_uri}")
                print(f"Metadata file: {result['metadata_file']}")
        else:
            print("\nNo images extracted")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
