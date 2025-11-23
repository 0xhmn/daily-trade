#!/usr/bin/env python3
"""
OpenSearch Health Check and Testing Script for Multimodal RAG

Tests OpenSearch cluster health, samples documents from 3 indexes, and validates search functionality.

Usage:

Check stats across all indexes:

    python scripts/opensearch_query_helper.py \
        --opensearch-host search-daily-trade-knowledge-001-l5zwovvaduyu5jorkbqfcrpspe.us-east-1.es.amazonaws.com \
        --local-role-arn arn:aws:iam::560271561561:role/DailyTradeLocalOpenSearchAccess \
        --stat

Run sample query:

    python scripts/opensearch_query_helper.py \
        --opensearch-host search-daily-trade-knowledge-001-l5zwovvaduyu5jorkbqfcrpspe.us-east-1.es.amazonaws.com \
        --local-role-arn arn:aws:iam::560271561561:role/DailyTradeLocalOpenSearchAccess \
        --test-query "RSI divergence patterns"

Delete document data (dry run first to preview):

    python scripts/opensearch_query_helper.py \
        --opensearch-host search-daily-trade-knowledge-001-l5zwovvaduyu5jorkbqfcrpspe.us-east-1.es.amazonaws.com \
        --local-role-arn arn:aws:iam::560271561561:role/DailyTradeLocalOpenSearchAccess \
        --delete-document 4_page_with_image

"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path to allow proper package imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.ingestion.multimodal_embedder import NovaMultimodalEmbeddingService
from backend.repositories.multimodal_opensearch_repository import MultimodalOpenSearchRepository


# Color codes for terminal output
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{title.center(70)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 70}{Colors.ENDC}\n")


def print_success(message: str):
    """Print success message."""
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")


def print_warning(message: str):
    """Print warning message."""
    print(f"{Colors.WARNING}⚠ {message}{Colors.ENDC}")


def print_error(message: str):
    """Print error message."""
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")


def print_info(label: str, value: Any):
    """Print info with label."""
    print(f"{Colors.OKBLUE}{label}:{Colors.ENDC} {value}")


def check_cluster_health(repo: MultimodalOpenSearchRepository) -> Dict[str, Any]:
    """Check OpenSearch cluster health."""
    print_section("CLUSTER HEALTH CHECK")

    try:
        health = repo.client.cluster.health()

        status = health["status"]
        if status == "green":
            print_success(f"Cluster Status: {status.upper()}")
        elif status == "yellow":
            print_warning(f"Cluster Status: {status.upper()}")
        else:
            print_error(f"Cluster Status: {status.upper()}")

        print_info("Cluster Name", health["cluster_name"])
        print_info("Number of Nodes", health["number_of_nodes"])
        print_info("Active Shards", health["active_shards"])
        print_info("Unassigned Shards", health["unassigned_shards"])

        if health["unassigned_shards"] > 0:
            print_warning(f"{health['unassigned_shards']} unassigned shards detected")

        return health

    except Exception as e:
        print_error(f"Failed to retrieve cluster health: {e}")
        return {}


def check_indexes_health(repo: MultimodalOpenSearchRepository) -> Dict[str, Any]:
    """Check health of all 3 multimodal indexes."""
    print_section("MULTIMODAL INDEXES HEALTH CHECK")

    try:
        stats = repo.get_stats()

        for index_name, index_stats in stats.items():
            print(f"\n{Colors.BOLD}{index_name.upper()}:{Colors.ENDC}")

            if not index_stats.get("exists"):
                print_error(f"  Index does not exist")
                continue

            print_success(f"  Index exists")
            print_info("  Document Count", f"{index_stats['document_count']:,}")

        return stats

    except Exception as e:
        print_error(f"Failed to retrieve index health: {e}")
        return {}


def show_data_statistics(repo: MultimodalOpenSearchRepository) -> Dict[str, Any]:
    """Show statistics about documents across all indexes."""
    print_section("DATA STATISTICS")

    try:
        stats = repo.get_stats()

        total_docs = sum(s.get("document_count", 0) for s in stats.values() if s.get("exists"))

        print_info("Total Documents (All Indexes)", f"{total_docs:,}")
        print()

        for index_name, index_stats in stats.items():
            if not index_stats.get("exists"):
                print(
                    f"{Colors.BOLD}{index_name}:{Colors.ENDC} {Colors.FAIL}Does not exist{Colors.ENDC}"
                )
                continue

            print(f"{Colors.BOLD}{index_name}:{Colors.ENDC}")
            print(f"  Documents: {Colors.OKCYAN}{index_stats['document_count']:,}{Colors.ENDC}")
            print()

        # Try to get document by title for text-chunks
        try:
            agg_query = {
                "size": 0,
                "aggs": {
                    "by_title": {
                        "terms": {
                            "field": "metadata.title.keyword",
                            "size": 50,
                            "order": {"_count": "desc"},
                        },
                    },
                },
            }

            response = repo.client.search(index="text-chunks", body=agg_query)
            by_title = response["aggregations"]["by_title"]["buckets"]

            if by_title:
                print(f"\n{Colors.BOLD}Documents in text-chunks by Title:{Colors.ENDC}\n")
                for i, bucket in enumerate(by_title, 1):
                    title = bucket["key"] if bucket["key"] else "(No Title)"
                    count = bucket["doc_count"]
                    print(f"  {i}. {title}: {Colors.OKCYAN}{count:,} chunks{Colors.ENDC}")

        except Exception as e:
            print_warning(f"Could not aggregate by title: {e}")

        return stats

    except Exception as e:
        print_error(f"Failed to retrieve statistics: {e}")
        logger.exception("Detailed error:")
        return {}


def test_text_search(
    repo: MultimodalOpenSearchRepository,
    embedder: NovaMultimodalEmbeddingService,
    query: str,
    k: int = 5,
) -> List[Dict[str, Any]]:
    """Test text search on text-chunks index."""
    print_section("TEXT SEARCH TEST (text-chunks index)")

    print_info("Query", f'"{query}"')
    print_info("Results to retrieve", k)
    print()

    try:
        # Generate query embedding
        print("Generating query embedding...")
        query_embedding = embedder.generate_text_embedding(query, purpose="GENERIC_RETRIEVAL")
        print_success(f"Generated embedding (dimension: {len(query_embedding)})\n")

        # Search text-chunks index using vector search
        results = repo.vector_search_text(query_embedding, k=k)

        if not results:
            print_warning("No results found")
            return []

        print_success(f"Found {len(results)} results\n")

        for i, result in enumerate(results, 1):
            print(f"{Colors.BOLD}Result {i}:{Colors.ENDC}")
            print(f"  Score: {result.get('score', 0):.4f}")
            print(f"  ID: {result.get('id', 'N/A')}")
            text = result.get("text", "")
            print(f"  Text: {text[:200]}...")

            metadata = result.get("metadata", {})
            if metadata.get("title"):
                print(f"  Title: {metadata['title']}")
            if metadata.get("document_type"):
                print(f"  Type: {metadata['document_type']}")
            print()

        return results

    except Exception as e:
        print_error(f"Text search failed: {e}")
        logger.exception("Detailed error:")
        return []


def print_summary(results: Dict[str, Any]):
    """Print test summary."""
    print_section("TEST SUMMARY")

    print(f"{Colors.BOLD}Cluster Status:{Colors.ENDC}")
    cluster = results.get("cluster", {})
    if cluster:
        status = cluster.get("status", "unknown")
        if status == "green":
            print_success(f"  Status: {status}")
        elif status == "yellow":
            print_warning(f"  Status: {status}")
        else:
            print_error(f"  Status: {status}")

    print(f"\n{Colors.BOLD}Indexes Status:{Colors.ENDC}")
    indexes = results.get("indexes", {})
    if indexes:
        for name, stats in indexes.items():
            if stats.get("exists"):
                print_success(f"  {name}: {stats.get('document_count', 0):,} documents")
            else:
                print_error(f"  {name}: does not exist")

    if results.get("text_results"):
        print(f"\n{Colors.BOLD}Search Tests:{Colors.ENDC}")
        print_success(f"  Text search: {len(results['text_results'])} results")

    print(f"\n{Colors.OKGREEN}{Colors.BOLD}Tests completed!{Colors.ENDC}\n")


def delete_document_data(
    repo: MultimodalOpenSearchRepository, document_id: str, dry_run: bool = True
) -> Dict[str, Any]:
    """
    Delete all data for a specific document across all indexes.

    Args:
        repo: OpenSearch repository
        document_id: Document identifier (filename without extension, e.g., '4_page_with_image')
        dry_run: If True, only show what would be deleted without actually deleting

    Returns:
        Dictionary with deletion results
    """
    print_section(f"DELETE DOCUMENT DATA: {document_id}")

    if dry_run:
        print_warning("DRY RUN MODE - No actual deletion will occur\n")
    else:
        print_error("DELETION MODE - Data will be permanently removed!\n")

    results = {}

    try:
        # Check each index and count matching documents
        # All three indexes now use metadata.source_file for consistent deletion
        source_file_query = {"term": {"metadata.source_file.keyword": f"{document_id}.pdf"}}

        queries = {
            "text-chunks": source_file_query,
            "extracted-images": source_file_query,
            "full-page-images": source_file_query,
        }

        total_to_delete = 0

        for index_name, query_clause in queries.items():
            print(f"{Colors.BOLD}Checking {index_name}...{Colors.ENDC}")

            try:
                # Count documents matching the pattern
                count_query = {"query": query_clause}

                count_response = repo.client.count(index=index_name, body=count_query)
                count = count_response["count"]

                if count > 0:
                    print_warning(f"  Found {count} documents to delete")
                    total_to_delete += count
                    results[index_name] = {"found": count, "deleted": 0}
                else:
                    print_info("  No documents found", "")
                    results[index_name] = {"found": 0, "deleted": 0}

            except Exception as e:
                print_error(f"  Error checking {index_name}: {e}")
                results[index_name] = {"error": str(e)}

        print()
        print_info("Total documents to delete", f"{total_to_delete}")

        if total_to_delete == 0:
            print_warning("\nNo documents found matching this document ID")
            return results

        # Perform deletion if not dry run
        if not dry_run:
            print()
            print_warning("Proceeding with deletion...")

            for index_name, query_clause in queries.items():
                if results[index_name].get("found", 0) > 0:
                    try:
                        delete_query = {"query": query_clause}

                        delete_response = repo.client.delete_by_query(
                            index=index_name, body=delete_query, refresh=True
                        )

                        deleted = delete_response.get("deleted", 0)
                        results[index_name]["deleted"] = deleted

                        if deleted > 0:
                            print_success(f"  Deleted {deleted} documents from {index_name}")

                    except Exception as e:
                        print_error(f"  Error deleting from {index_name}: {e}")
                        results[index_name]["error"] = str(e)

            print()
            print_success(f"Deletion completed!")
        else:
            print()
            print_info("Dry run complete", "Use --confirm-delete to actually delete")

        return results

    except Exception as e:
        print_error(f"Failed to delete document data: {e}")
        logger.exception("Detailed error:")
        return {"error": str(e)}


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Test OpenSearch multimodal RAG system")

    parser.add_argument(
        "--opensearch-host", type=str, required=True, help="OpenSearch domain endpoint"
    )
    parser.add_argument(
        "--local-role-arn",
        type=str,
        help="IAM role ARN for local OpenSearch access",
    )
    parser.add_argument(
        "--region",
        type=str,
        default="us-east-1",
        help="AWS region (default: us-east-1)",
    )
    parser.add_argument(
        "--test-query",
        type=str,
        default="RSI trading strategy",
        help="Search query for testing",
    )
    parser.add_argument(
        "--search-k",
        type=int,
        default=5,
        help="Number of search results (default: 5)",
    )
    parser.add_argument(
        "--embedding-dimension",
        type=int,
        default=1024,
        help="Embedding dimension (default: 1024)",
    )
    parser.add_argument(
        "--stat",
        action="store_true",
        help="Show data statistics",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Run health checks only",
    )
    parser.add_argument(
        "--delete-document",
        type=str,
        help="Delete all data for a specific document (provide document ID, e.g., '4_page_with_image')",
    )
    parser.add_argument(
        "--confirm-delete",
        action="store_true",
        help="Confirm deletion (without this flag, only a dry run is performed)",
    )

    return parser.parse_args()


def main():
    """Main test workflow."""
    args = parse_args()

    print(f"\n{Colors.HEADER}{Colors.BOLD}")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║     Multimodal OpenSearch Health Check & Testing Tool              ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")

    print_info("Host", args.opensearch_host)
    print_info("Region", args.region)
    print_info("Indexes", "text-chunks, extracted-images, full-page-images")
    print_info("Test Query", f'"{args.test_query}"')
    print_info("Timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    test_results = {}

    try:
        # Initialize repository
        print("\nInitializing OpenSearch connection...")
        repo = MultimodalOpenSearchRepository(
            host=args.opensearch_host,
            region=args.region,
            local_role_arn=args.local_role_arn,
        )
        print_success("Connected to OpenSearch\n")

        # Check cluster health
        cluster_health = check_cluster_health(repo)
        test_results["cluster"] = cluster_health

        # Check indexes
        indexes_health = check_indexes_health(repo)
        test_results["indexes"] = indexes_health

        # Handle document deletion
        if args.delete_document:
            delete_result = delete_document_data(
                repo, args.delete_document, dry_run=not args.confirm_delete
            )
            test_results["delete"] = delete_result
            return

        # Handle statistics display
        if args.stat:
            stats_result = show_data_statistics(repo)
            test_results["stats"] = stats_result
            print_summary(test_results)
            return

        # If only health check, exit
        if args.health:
            print_summary(test_results)
            return

        # Initialize embedder for search tests
        print("\nInitializing Nova embedder...")
        embedder = NovaMultimodalEmbeddingService(
            embedding_dimension=args.embedding_dimension,
            region_name=args.region,
        )
        print_success("Embedder initialized\n")

        # Run text search test
        text_results = test_text_search(repo, embedder, args.test_query, k=args.search_k)
        test_results["text_results"] = text_results

        # Print summary
        print_summary(test_results)

    except Exception as e:
        print_error(f"Test failed with error: {e}")
        logger.exception("Detailed error:")
        sys.exit(1)


if __name__ == "__main__":
    main()
