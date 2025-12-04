#!/usr/bin/env python3
"""
Multimodal Document Ingestion Script

Ingests trading books with charts and graphs into the multimodal RAG system.
Processes PDFs with text and images, generates dual embeddings, and indexes to 3 OpenSearch indexes.

Features:
- Extracts text chunks
- Extracts embedded images (charts, graphs)
- Converts pages to full-page images
- Generates descriptions with Nova Vision
- Creates dual embeddings (text + multimodal)
- Cross-references content spatially
- Indexes to 3 OpenSearch indexes

Usage:
python scripts/ingest_multimodal_documents.py \
    --pdf data/sample_data/4_page_with_image.pdf \
    --opensearch-host search-daily-trade-knowledge-001-xxx.us-east-1.es.amazonaws.com \
    --local-role-arn arn:aws:iam::560271561561:role/DailyTradeLocalOpenSearchAccess \
    --s3-bucket daily-trade-images-560271561561 \
    --title "Technical Analysis Sample" \
    --author "Test Author" \
    --strategy-type technical_analysis \
    --document-type test-doc

Example with William O'Neil book:
python scripts/ingest_multimodal_documents.py \
  --pdf "data/knowledge_base/swing_trading/how_to_make_money_in_stocks/how_to_make_money_in_stocks.pdf" \
  --opensearch-host search-daily-trade-knowledge-001-l5zwovvaduyu5jorkbqfcrpspe.us-east-1.es.amazonaws.com \
  --local-role-arn arn:aws:iam::560271561561:role/DailyTradeLocalOpenSearchAccess \
  --s3-bucket daily-trade-images-560271561561 \
  --title "How to Make Money in Stocks: A Winning System in Good Times and Bad, Fourth Edition" \
  --author "William J. O'Neil" \
  --strategy-type swing_trading \
  --document-type ebook \
  --timeframe "3_weeks-6_months" \
  --market-conditions bull_and_bear \
  --asset-class equities \
  --concepts CAN_SLIM cup_with_handle relative_strength earnings_growth institutional_buying chart_patterns volume_analysis

"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path to allow proper package imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.ingestion.document_ingestion_orchestrator import DocumentIngestionOrchestrator
from backend.ingestion.document_processor import DocumentMetadata
from backend.ingestion.image_processor import ExtractionMethod
from backend.repositories.multimodal_opensearch_repository import MultimodalOpenSearchRepository

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Ingest trading documents into multimodal RAG system"
    )

    # Required arguments
    parser.add_argument("--pdf", type=str, required=True, help="Path to PDF file")
    parser.add_argument("--title", type=str, required=True, help="Document title")
    parser.add_argument(
        "--strategy-type",
        type=str,
        required=True,
        choices=["swing_trading", "technical_analysis", "risk_management", "test"],
        help="Strategy type",
    )
    parser.add_argument(
        "--document-type",
        type=str,
        required=True,
        choices=["test-doc", "ebook", "article"],
        help="Type of document",
    )

    # Optional document metadata
    parser.add_argument("--author", type=str, help="Document author")
    parser.add_argument(
        "--timeframe",
        type=str,
        default="swing_trading",
        help="Trading timeframe (e.g., '3-7 days', '7-14 days')",
    )
    parser.add_argument(
        "--market-conditions",
        nargs="+",
        default=["trending", "ranging"],
        help="Applicable market conditions",
    )
    parser.add_argument(
        "--asset-class",
        nargs="+",
        default=["equities"],
        help="Applicable asset classes",
    )
    parser.add_argument("--concepts", nargs="+", default=[], help="Key concepts in the document")

    # AWS/Infrastructure parameters
    parser.add_argument(
        "--opensearch-host", type=str, required=True, help="OpenSearch domain endpoint"
    )
    parser.add_argument(
        "--s3-bucket",
        type=str,
        required=True,
        help="S3 bucket for image storage (e.g., daily-trade-images-560271561561)",
    )
    parser.add_argument("--region", type=str, default="us-east-1", help="AWS region")
    parser.add_argument(
        "--local-role-arn", type=str, help="IAM role ARN for local OpenSearch access"
    )

    # Processing parameters
    parser.add_argument(
        "--chunk-size", type=int, default=1000, help="Target chunk size in characters"
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=200,
        help="Overlap between chunks in characters",
    )
    parser.add_argument(
        "--embedding-dimension",
        type=int,
        default=1024,
        choices=[256, 384, 1024, 3072],
        help="Nova embedding dimension",
    )
    parser.add_argument(
        "--image-extraction-method",
        type=str,
        default="get_drawings",
        choices=["get_images", "get_svg_image", "get_drawings"],
        help="Method for extracting images from PDF",
    )
    parser.add_argument(
        "--full-page-dpi",
        type=int,
        default=150,
        help="DPI for full-page image rendering",
    )

    # Options
    parser.add_argument(
        "--create-indexes",
        action="store_true",
        help="Create OpenSearch indexes if they don't exist",
    )
    parser.add_argument(
        "--skip-indexing",
        action="store_true",
        help="Skip OpenSearch indexing (only process locally)",
    )
    parser.add_argument(
        "--reset-checkpoint",
        action="store_true",
        help="Reset checkpoint and start ingestion from beginning",
    )

    return parser.parse_args()


async def main():
    """Main multimodal ingestion workflow."""
    args = parse_args()

    # Validate PDF path
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        logger.error(f"PDF file not found: {pdf_path}")
        sys.exit(1)

    logger.info("=" * 80)
    logger.info("MULTIMODAL DOCUMENT INGESTION")
    logger.info(f"Document: {args.title}")
    logger.info(f"PDF: {pdf_path}")
    logger.info("=" * 80)

    # Create metadata
    metadata = DocumentMetadata(
        title=args.title,
        author=args.author,
        strategy_type=args.strategy_type,
        timeframe=args.timeframe,
        market_conditions=args.market_conditions,
        asset_class=args.asset_class,
        key_concepts=args.concepts,
        document_type=args.document_type,
        source_file=pdf_path.name,
    )

    logger.info("\nDocument Metadata:")
    logger.info(f"  Author: {metadata.author}")
    logger.info(f"  Strategy: {metadata.strategy_type}")
    logger.info(f"  Timeframe: {metadata.timeframe}")
    logger.info(f"  Asset Classes: {', '.join(metadata.asset_class)}")
    logger.info(f"  Key Concepts: {', '.join(metadata.key_concepts[:5])}...")

    # Initialize orchestrator
    logger.info("\n[1/2] Initializing multimodal orchestrator...")

    extraction_method_map = {
        "get_images": ExtractionMethod.GET_IMAGES,
        "get_svg_image": ExtractionMethod.GET_SVG_IMAGE,
        "get_drawings": ExtractionMethod.GET_DRAWINGS,
    }

    orchestrator = DocumentIngestionOrchestrator(
        s3_bucket=args.s3_bucket,
        region_name=args.region,
        embedding_dimension=args.embedding_dimension,
        image_extraction_method=extraction_method_map[args.image_extraction_method],
        full_page_dpi=args.full_page_dpi,
    )

    logger.info(f"✓ S3 Bucket: {args.s3_bucket}")
    logger.info(f"✓ OpenSearch: {args.opensearch_host}")
    logger.info(f"✓ Embedding Dimension: {args.embedding_dimension}")
    logger.info(f"✓ Image Extraction: {args.image_extraction_method}")

    # Image extraction quality reminder
    print("\n" + "\033[93m" + "=" * 80)
    print("⚠️  IMAGE EXTRACTION QUALITY REMINDER")
    print("=" * 80)
    print("For BEST image extraction results (especially with Amazon Kindle/DRM PDFs):")
    print("  1. Open the PDF in Preview (macOS) or your PDF viewer")
    print("  2. Print → Save as PDF")
    print("  3. Use the re-saved PDF for ingestion")
    print("")
    print("This flattens vector graphics into single drawing objects, preventing")
    print("fragmented/split images during extraction.")
    print("=" * 80 + "\033[0m\n")

    if not args.skip_indexing:
        # Initialize OpenSearch repository
        logger.info("\n[2/2] Initializing OpenSearch repository...")

        repository = MultimodalOpenSearchRepository(
            host=args.opensearch_host,
            region=args.region,
            local_role_arn=args.local_role_arn,
        )

        # Create indexes if requested
        if args.create_indexes:
            logger.info("Creating OpenSearch indexes...")
            try:
                repository.create_indexes(
                    text_dim=args.embedding_dimension,
                    multimodal_dim=args.embedding_dimension,
                )
                logger.info("✓ Indexes created successfully")
            except Exception as e:
                logger.warning(f"Index creation: {e}")
                logger.info("Indexes may already exist, continuing...")

        # Run complete ingestion pipeline
        logger.info("\n" + "=" * 80)
        logger.info("STARTING INGESTION PIPELINE")
        logger.info("=" * 80)

        try:
            results = await orchestrator.ingest_document(
                pdf_path, metadata, repository, reset_checkpoint=args.reset_checkpoint
            )

            # Display results
            logger.info("\n" + "=" * 80)
            logger.info("✓ INGESTION COMPLETED SUCCESSFULLY!")
            logger.info("=" * 80)
            logger.info(f"Document ID: {results['document_id']}")
            logger.info(f"Status: {results['status']}")
            logger.info("\nIndexed Documents:")
            logger.info(f"  • Text Chunks: {results['chunks_indexed']}")
            logger.info(f"  • Extracted Images: {results['images_indexed']}")
            logger.info(f"  • Full Page Images: {results['pages_indexed']}")
            logger.info(f"  • Total: {results['total_indexed']}")
            logger.info("=" * 80)

            # Show index stats
            logger.info("\nOpenSearch Index Statistics:")
            try:
                all_stats = repository.get_stats()
                for name, stats in all_stats.items():
                    if stats.get("exists"):
                        logger.info(f"  • {name}:")
                        logger.info(f"    - Documents: {stats['document_count']}")
                    else:
                        logger.info(f"  • {name}: Index does not exist")
            except Exception as e:
                logger.warning(f"Could not get index stats: {e}")

        except Exception as e:
            logger.error(f"\n✗ Ingestion failed: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    else:
        logger.info("\n[2/2] Skipping OpenSearch indexing (--skip-indexing)")
        logger.warning("Note: Multimodal pipeline requires indexing to create cross-references")
        logger.info("Processing will extract and analyze content but not index it.")

    logger.info("\n" + "=" * 80)
    logger.info("Ingestion process completed.")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
