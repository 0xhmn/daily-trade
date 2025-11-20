#!/usr/bin/env python3
"""
Document Ingestion Script

Ingests trading books and articles into the knowledge base.
Processes PDFs, generates embeddings, and indexes to OpenSearch.

Usage:
    python scripts/ingest_documents.py \
        --pdf data/sample_data/The_Rubaiyat_of_Omar_Khayyam.pdf \
        --opensearch-host search-daily-trade-knowledge-001-l5zwovvaduyu5jorkbqfcrpspe.us-east-1.es.amazonaws.com \
        --local-role-arn arn:aws:iam::560271561561:role/DailyTradeLocalOpenSearchAccess \
        --index-name trading-knowledge \
        --title "The Rubaiyat of Omar Khayyam" \
        --author "Khayyam" \
        --strategy-type test \
        --timeframe "11th_century_persian" \
        --asset-class poetry_collection \
        --concepts mortality hedonism carpe_diem philosophy wine love time \
        --document-type test-doc
"""

import argparse
import logging
import sys
from pathlib import Path

from tqdm import tqdm

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from ingestion.document_processor import DocumentMetadata, DocumentProcessor
from ingestion.embedder import EmbeddingService
from repositories.opensearch_repository import OpenSearchRepository

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Ingest trading documents into knowledge base")

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
        choices=["test-doc", "ebook"],
        help="Type of Document - use test for test documents",
    )

    # Optional arguments
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

    # AWS/OpenSearch parameters
    parser.add_argument(
        "--opensearch-host",
        type=str,
        help="OpenSearch domain endpoint (required for indexing)",
    )
    parser.add_argument("--region", type=str, default="us-east-1", help="AWS region")
    parser.add_argument(
        "--local-role-arn",
        type=str,
        help="IAM role ARN for local OpenSearch access (required when STAGE=local)",
    )
    parser.add_argument(
        "--index-name",
        type=str,
        default="trading-knowledge",
        help="OpenSearch index name",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default="amazon.titan-embed-text-v1",
        help="Bedrock embedding model ID",
    )

    # Options
    parser.add_argument(
        "--skip-indexing",
        action="store_true",
        help="Skip OpenSearch indexing (only process locally)",
    )
    parser.add_argument(
        "--create-index",
        action="store_true",
        help="Create OpenSearch index if it doesn't exist",
    )

    return parser.parse_args()


def main():
    """Main ingestion workflow."""
    args = parse_args()

    # Validate PDF path
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        logger.error(f"PDF file not found: {pdf_path}")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info(f"Starting document ingestion: {args.title}")
    logger.info("=" * 60)

    # Step 1: Initialize document processor
    logger.info("\n[1/4] Initializing document processor...")
    processor = DocumentProcessor(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)

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

    # Step 2: Process document
    logger.info("\n[2/4] Processing document...")
    try:
        chunks = processor.process_document(pdf_path, metadata)
        logger.info(f"✓ Created {len(chunks)} chunks from {metadata.page_count} pages")
    except Exception as e:
        logger.error(f"Failed to process document: {e}")
        sys.exit(1)

    # Step 3: Generate embeddings
    logger.info("\n[3/4] Generating embeddings...")
    embedder = EmbeddingService(model_id=args.embedding_model, region_name=args.region)

    embeddings = []
    try:
        for chunk in tqdm(chunks, desc="Embedding chunks"):
            embedding = embedder.generate_embedding(chunk.text)
            embeddings.append(embedding)
        logger.info(f"✓ Generated {len(embeddings)} embeddings")
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        sys.exit(1)

    # Step 4: Index to OpenSearch
    success = 0  # Initialize for summary logging

    if not args.skip_indexing:
        logger.info("\n[4/4] Indexing to OpenSearch...")

        if not args.opensearch_host:
            logger.error("--opensearch-host is required for indexing")
            logger.info("Use --skip-indexing to only process locally")
            sys.exit(1)

        try:
            repo = OpenSearchRepository(
                host=args.opensearch_host,
                region=args.region,
                index_name=args.index_name,
                local_role_arn=args.local_role_arn,
            )

            # Create index if requested
            if args.create_index:
                logger.info("Creating OpenSearch index...")
                repo.create_index(vector_dimension=len(embeddings[0]), force=False)

            # Prepare documents for bulk indexing
            documents = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                doc_id = f"{pdf_path.stem}_chunk_{i}"
                documents.append(
                    {
                        "id": doc_id,
                        "text": chunk.text,
                        "embedding": embedding,
                        "metadata": chunk.metadata,
                    }
                )

            # Bulk index
            logger.info(f"Indexing {len(documents)} documents...")
            success, failed = repo.index_documents_bulk(documents)

            if failed > 0:
                logger.warning(f"⚠ {failed} documents failed to index")

            logger.info(f"✓ Successfully indexed {success} documents")

            # Show index stats
            stats = repo.get_index_stats()
            logger.info(
                f"Index stats: {stats['document_count']} docs, "
                f"{stats['size_in_bytes'] / 1024 / 1024:.2f} MB"
            )

        except Exception as e:
            logger.error(f"Failed to index documents: {e}")
            sys.exit(1)
    else:
        logger.info("\n[4/4] Skipping OpenSearch indexing (--skip-indexing)")

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("✓ Ingestion completed successfully!")
    logger.info("=" * 60)
    logger.info(f"Title: {args.title}")
    logger.info(f"Strategy Type: {args.strategy_type}")
    logger.info(f"Chunks: {len(chunks)}")
    logger.info(f"Embeddings: {len(embeddings)}")
    if not args.skip_indexing:
        logger.info(f"Indexed: {success} documents")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
