#!/usr/bin/env python3
"""
OpenSearch Health Check and Testing Script

Tests OpenSearch cluster health, samples documents, and validates search functionality.

Usage:

Run sample Query:

    python scripts/opensearch_query_helper.py \
        --opensearch-host search-daily-trade-knowledge-001-l5zwovvaduyu5jorkbqfcrpspe.us-east-1.es.amazonaws.com \
        --local-role-arn arn:aws:iam::560271561561:role/DailyTradeLocalOpenSearchAccess \
        --test-query "Michael Favala Goldman"

Get book stats:

    python scripts/opensearch_query_helper.py \
        --opensearch-host search-daily-trade-knowledge-001-l5zwovvaduyu5jorkbqfcrpspe.us-east-1.es.amazonaws.com \
        --local-role-arn arn:aws:iam::560271561561:role/DailyTradeLocalOpenSearchAccess \
        --stat
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from ingestion.embedder import EmbeddingService
from repositories.opensearch_repository import OpenSearchRepository


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
    level=logging.WARNING,  # Suppress INFO logs for cleaner output
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


def check_cluster_health(repo: OpenSearchRepository) -> Dict[str, Any]:
    """
    Check OpenSearch cluster health.

    Returns:
        Cluster health information
    """
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
        print_info("Number of Data Nodes", health["number_of_data_nodes"])
        print_info("Active Primary Shards", health["active_primary_shards"])
        print_info("Active Shards", health["active_shards"])
        print_info("Relocating Shards", health["relocating_shards"])
        print_info("Initializing Shards", health["initializing_shards"])
        print_info("Unassigned Shards", health["unassigned_shards"])

        if health["unassigned_shards"] > 0:
            print_warning(f"{health['unassigned_shards']} unassigned shards detected")

        return health

    except Exception as e:
        print_error(f"Failed to retrieve cluster health: {e}")
        return {}


def check_index_health(repo: OpenSearchRepository) -> Dict[str, Any]:
    """
    Check index health and statistics.

    Returns:
        Index statistics
    """
    print_section(f"INDEX HEALTH CHECK: {repo.index_name}")

    try:
        # Check if index exists
        exists = repo.client.indices.exists(index=repo.index_name)

        if not exists:
            print_error(f"Index '{repo.index_name}' does not exist")
            return {"exists": False}

        print_success(f"Index '{repo.index_name}' exists")

        # Get index stats
        stats = repo.get_index_stats()

        if stats.get("exists"):
            print_info("Document Count", f"{stats['document_count']:,}")
            print_info("Index Size", f"{stats['size_in_bytes'] / 1024 / 1024:.2f} MB")

        # Get index mappings
        mappings = repo.client.indices.get_mapping(index=repo.index_name)
        index_mappings = mappings[repo.index_name]["mappings"]

        # Check embedding dimension
        if "properties" in index_mappings and "embedding" in index_mappings["properties"]:
            embedding_config = index_mappings["properties"]["embedding"]
            dimension = embedding_config.get("dimension", "N/A")
            print_info("Embedding Dimension", dimension)
            print_info(
                "Embedding Method",
                embedding_config.get("method", {}).get("name", "N/A"),
            )

        # Get index settings
        settings = repo.client.indices.get_settings(index=repo.index_name)
        index_settings = settings[repo.index_name]["settings"]["index"]

        print_info("Number of Shards", index_settings.get("number_of_shards", "N/A"))
        print_info("Number of Replicas", index_settings.get("number_of_replicas", "N/A"))
        print_info("kNN Enabled", index_settings.get("knn", "N/A"))

        return stats

    except Exception as e:
        print_error(f"Failed to retrieve index health: {e}")
        return {}


def sample_documents(repo: OpenSearchRepository, sample_size: int = 3) -> List[Dict[str, Any]]:
    """
    Retrieve sample documents from the index.

    Args:
        repo: OpenSearch repository
        sample_size: Number of documents to sample

    Returns:
        List of sample documents
    """
    print_section(f"SAMPLE DOCUMENTS (n={sample_size})")

    try:
        # Query for random documents
        query = {
            "size": sample_size,
            "query": {"match_all": {}},
            "_source": ["text", "metadata"],
        }

        response = repo.client.search(index=repo.index_name, body=query)
        hits = response["hits"]["hits"]

        if not hits:
            print_warning("No documents found in index")
            return []

        print_success(f"Retrieved {len(hits)} sample documents\n")

        documents = []
        for i, hit in enumerate(hits, 1):
            doc = {
                "id": hit["_id"],
                "score": hit["_score"],
                "text": hit["_source"]["text"],
                "metadata": hit["_source"]["metadata"],
            }
            documents.append(doc)

            print(f"{Colors.BOLD}Document {i}:{Colors.ENDC}")
            print(f"  ID: {doc['id']}")
            print(f"  Text Preview: {doc['text'][:150]}...")
            print(f"  Metadata:")
            for key, value in doc["metadata"].items():
                if value:  # Only show non-empty metadata
                    print(f"    - {key}: {value}")
            print()

        return documents

    except Exception as e:
        print_error(f"Failed to sample documents: {e}")
        return []


def test_lexical_search(repo: OpenSearchRepository, query: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    Test lexical (BM25) search.

    Args:
        repo: OpenSearch repository
        query: Search query text
        k: Number of results

    Returns:
        Search results
    """
    print_section(f"LEXICAL SEARCH TEST (BM25)")

    print_info("Query", f'"{query}"')
    print_info("Results to retrieve", k)
    print()

    try:
        results = repo.lexical_search(query, k=k)

        if not results:
            print_warning("No results found")
            return []

        print_success(f"Found {len(results)} results\n")

        for i, result in enumerate(results, 1):
            print(f"{Colors.BOLD}Result {i}:{Colors.ENDC}")
            print(f"  Score: {result['score']:.4f}")
            print(f"  ID: {result['id']}")
            print(f"  Text: {result['text'][:200]}...")

            # Show relevant metadata
            metadata = result.get("metadata", {})
            if metadata.get("title"):
                print(f"  Title: {metadata['title']}")
            if metadata.get("strategy_type"):
                print(f"  Strategy: {metadata['strategy_type']}")
            print()

        return results

    except Exception as e:
        print_error(f"Lexical search failed: {e}")
        return []


def test_vector_search(
    repo: OpenSearchRepository, embedder: EmbeddingService, query: str, k: int = 5
) -> List[Dict[str, Any]]:
    """
    Test vector (kNN) search.

    Args:
        repo: OpenSearch repository
        embedder: Embedding service
        query: Search query text
        k: Number of results

    Returns:
        Search results
    """
    print_section(f"VECTOR SEARCH TEST (kNN)")

    print_info("Query", f'"{query}"')
    print_info("Results to retrieve", k)
    print()

    try:
        # Generate query embedding
        print("Generating query embedding...")
        query_embedding = embedder.generate_embedding(query)
        print_success(f"Generated embedding (dimension: {len(query_embedding)})\n")

        # Perform vector search
        results = repo.vector_search(query_embedding, k=k)

        if not results:
            print_warning("No results found")
            return []

        print_success(f"Found {len(results)} results\n")

        for i, result in enumerate(results, 1):
            print(f"{Colors.BOLD}Result {i}:{Colors.ENDC}")
            print(f"  Score: {result['score']:.4f}")
            print(f"  ID: {result['id']}")
            print(f"  Text: {result['text'][:200]}...")

            # Show relevant metadata
            metadata = result.get("metadata", {})
            if metadata.get("docuemnt_type"):
                print(f"  Document Type: {metadata['document_type']}")
            if metadata.get("title"):
                print(f"  Title: {metadata['title']}")
            if metadata.get("strategy_type"):
                print(f"  Strategy: {metadata['strategy_type']}")
            print()

        return results

    except Exception as e:
        print_error(f"Vector search failed: {e}")
        return []


def test_hybrid_search(
    repo: OpenSearchRepository,
    embedder: EmbeddingService,
    query: str,
    k: int = 5,
    alpha: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    Test hybrid search (lexical + vector with RRF).

    Args:
        repo: OpenSearch repository
        embedder: Embedding service
        query: Search query text
        k: Number of results
        alpha: Weight for vector search (0-1)

    Returns:
        Search results
    """
    print_section(f"HYBRID SEARCH TEST (Lexical + Vector + RRF)")

    print_info("Query", f'"{query}"')
    print_info("Results to retrieve", k)
    print_info("Vector weight (alpha)", alpha)
    print_info("Lexical weight (1-alpha)", 1 - alpha)
    print()

    try:
        # Generate query embedding
        print("Generating query embedding...")
        query_embedding = embedder.generate_embedding(query)
        print_success(f"Generated embedding (dimension: {len(query_embedding)})\n")

        # Perform hybrid search
        results = repo.hybrid_search(query, query_embedding, k=k, alpha=alpha)

        if not results:
            print_warning("No results found")
            return []

        print_success(f"Found {len(results)} results (fused with RRF)\n")

        for i, result in enumerate(results, 1):
            print(f"{Colors.BOLD}Result {i}:{Colors.ENDC}")
            print(f"  Fused Score: {result['score']:.6f}")
            print(f"  ID: {result['id']}")
            print(f"  Text: {result['text'][:200]}...")

            metadata = result.get("metadata", {})
            if metadata.get("title"):
                print(f"  Title: {metadata['title']}")
            if metadata.get("document_type"):
                print(f"  Document Type: {metadata['document_type']}")

            print()

        return results

    except Exception as e:
        print_error(f"Hybrid search failed: {e}")
        return []


def delete_documents_by_query(
    repo: OpenSearchRepository, doc_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete documents matching a specific type.

    Args:
        repo: OpenSearch repository
        doc_type: Document type to delete (e.g., "test", "temp")

    Returns:
        Deletion result statistics
    """
    print_section("DELETE DOCUMENTS BY QUERY")

    if not doc_type:
        print_error("Document type must be specified for deletion")
        print_warning("Use --doc-type parameter to specify which documents to delete")
        return {"deleted": 0, "error": "Type not specified"}

    delete_query = {"query": {"term": {"metadata.document_type": doc_type}}}

    print_info("Target", f"Documents with type='{doc_type}'")
    print_warning("This operation cannot be undone!")
    print()

    try:
        # First, count documents to be deleted
        count_response = repo.client.count(index=repo.index_name, body=delete_query)
        doc_count = count_response["count"]

        if doc_count == 0:
            print_warning("No documents found matching the query")
            return {"deleted": 0}

        print_info("Documents to delete", doc_count)

        # Confirm deletion
        confirm = input(
            f"\n{Colors.WARNING}Are you sure you want to delete {doc_count} documents? (yes/no): {Colors.ENDC}"
        )

        if confirm.lower() != "yes":
            print_warning("Deletion cancelled by user")
            return {"deleted": 0, "cancelled": True}

        # Execute deletion
        print("\nDeleting documents...")
        response = repo.client.delete_by_query(index=repo.index_name, body=delete_query)

        # Refresh index to make changes visible
        repo.client.indices.refresh(index=repo.index_name)

        deleted = response.get("deleted", 0)
        failures = response.get("failures", [])

        if deleted > 0:
            print_success(f"Successfully deleted {deleted} documents")

        if failures:
            print_error(f"Failed to delete {len(failures)} documents")
            for failure in failures[:5]:  # Show first 5 failures
                print(f"  - {failure}")

        return {
            "deleted": deleted,
            "failures": len(failures),
            "total": response.get("total", 0),
        }

    except Exception as e:
        print_error(f"Delete operation failed: {e}")
        logger.exception("Detailed error:")
        return {"deleted": 0, "error": str(e)}


def recreate_index(repo: OpenSearchRepository, vector_dimension: int = 1536) -> Dict[str, Any]:
    """
    Recreate the OpenSearch index (deletes existing index and creates new one).

    Args:
        repo: OpenSearch repository
        vector_dimension: Dimension of embedding vectors (default: 1536)

    Returns:
        Operation result
    """
    print_section("RECREATE INDEX")

    print_warning("⚠️  WARNING: This will DELETE the existing index and ALL its data!")
    print_warning("This operation cannot be undone!")
    print()

    # Check if index exists
    exists = repo.client.indices.exists(index=repo.index_name)

    if exists:
        stats = repo.get_index_stats()
        doc_count = stats.get("document_count", 0)
        print_info("Current Index", repo.index_name)
        print_info("Documents to be deleted", f"{doc_count:,}")
        print()
    else:
        print_info("Current Status", "Index does not exist (will create new)")
        print()

    # Confirm operation
    confirm = input(
        f"{Colors.FAIL}Type 'DELETE ALL DATA' to confirm index recreation: {Colors.ENDC}"
    )

    if confirm != "DELETE ALL DATA":
        print_warning("Operation cancelled by user")
        return {"recreated": False, "cancelled": True}

    try:
        print("\nRecreating index...")

        # This will delete the index if it exists and create a new one
        success = repo.create_index(vector_dimension=vector_dimension, force=True)

        if success:
            print_success(f"Successfully recreated index: {repo.index_name}")
            print_info("Vector Dimension", vector_dimension)
            print()
            print_warning("Index is now empty. You need to re-ingest documents.")

            return {
                "recreated": True,
                "index_name": repo.index_name,
                "vector_dimension": vector_dimension,
            }
        else:
            print_error("Failed to recreate index")
            return {"recreated": False, "error": "Index creation returned False"}

    except Exception as e:
        print_error(f"Index recreation failed: {e}")
        logger.exception("Detailed error:")
        return {"recreated": False, "error": str(e)}


def show_data_statistics(repo: OpenSearchRepository) -> Dict[str, Any]:
    """
    Show statistics about documents in the index grouped by title.

    Args:
        repo: OpenSearch repository

    Returns:
        Statistics data
    """
    print_section("DATA STATISTICS")

    try:
        # Aggregation query to group by title and get metadata
        agg_query = {
            "size": 0,
            "aggs": {
                "by_title": {
                    "terms": {
                        "field": "metadata.title.keyword",
                        "size": 100,
                        "order": {"_count": "desc"},
                    },
                    "aggs": {
                        "source_files": {"terms": {"field": "metadata.source_file", "size": 10}},
                        "types": {"terms": {"field": "metadata.type", "size": 10}},
                        "strategy_types": {
                            "terms": {"field": "metadata.strategy_type", "size": 10}
                        },
                        "authors": {"terms": {"field": "metadata.author", "size": 10}},
                        "timeframes": {"terms": {"field": "metadata.timeframe", "size": 10}},
                    },
                },
                "total_by_type": {"terms": {"field": "metadata.type", "size": 20}},
                "total_by_source": {"terms": {"field": "metadata.source_file", "size": 50}},
            },
        }

        response = repo.client.search(index=repo.index_name, body=agg_query)

        total_docs = repo.get_index_stats()["document_count"]
        print_info("Total Documents", f"{total_docs:,}")
        print()

        # Show by title
        by_title = response["aggregations"]["by_title"]["buckets"]

        if by_title:
            print(f"{Colors.BOLD}Documents Grouped by Title:{Colors.ENDC}\n")

            for i, bucket in enumerate(by_title, 1):
                title = bucket["key"] if bucket["key"] else "(No Title)"
                count = bucket["doc_count"]

                print(f"{Colors.OKCYAN}{i}. {title}{Colors.ENDC}")
                print(f"   Document Count: {Colors.BOLD}{count:,}{Colors.ENDC}")

                # Show source files
                sources = bucket["source_files"]["buckets"]
                if sources:
                    print(f"   Source Files:")
                    for src in sources:
                        print(f"     - {src['key']} ({src['doc_count']} chunks)")

                # Show types
                types = bucket["types"]["buckets"]
                if types:
                    print(f"   Types:")
                    for typ in types:
                        print(f"     - {typ['key']} ({typ['doc_count']} docs)")

                # Show strategy types
                strategies = bucket["strategy_types"]["buckets"]
                if strategies:
                    print(f"   Strategy Types:")
                    for strat in strategies:
                        print(f"     - {strat['key']} ({strat['doc_count']} docs)")

                # Show authors
                authors = bucket["authors"]["buckets"]
                if authors:
                    print(f"   Authors:")
                    for author in authors:
                        print(f"     - {author['key']} ({author['doc_count']} docs)")

                # Show timeframes
                timeframes = bucket["timeframes"]["buckets"]
                if timeframes:
                    print(f"   Timeframes:")
                    for tf in timeframes:
                        print(f"     - {tf['key']} ({tf['doc_count']} docs)")

                print()

        # Show summary by type
        by_type = response["aggregations"]["total_by_type"]["buckets"]
        if by_type:
            print(f"\n{Colors.BOLD}Summary by Type:{Colors.ENDC}")
            for bucket in by_type:
                type_name = bucket["key"] if bucket["key"] else "(No Type)"
                print(f"  {type_name}: {bucket['doc_count']:,} documents")

        # Show summary by source file
        by_source = response["aggregations"]["total_by_source"]["buckets"]
        if by_source:
            print(f"\n{Colors.BOLD}Summary by Source File:{Colors.ENDC}")
            for bucket in by_source:
                print(f"  {bucket['key']}: {bucket['doc_count']:,} chunks")

        print()

        return {
            "total_documents": total_docs,
            "by_title": by_title,
            "by_type": by_type,
            "by_source": by_source,
        }

    except Exception as e:
        print_error(f"Failed to retrieve statistics: {e}")
        logger.exception("Detailed error:")
        return {}


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
        print(f"  Nodes: {cluster.get('number_of_nodes', 'N/A')}")

    print(f"\n{Colors.BOLD}Index Status:{Colors.ENDC}")
    index = results.get("index", {})
    if index.get("exists"):
        print_success(f"  Index exists with {index.get('document_count', 0):,} documents")
        print(f"  Size: {index.get('size_in_bytes', 0) / 1024 / 1024:.2f} MB")
    else:
        print_error("  Index does not exist")

    print(f"\n{Colors.BOLD}Search Tests:{Colors.ENDC}")
    if results.get("lexical_results"):
        print_success(f"  Lexical search: {len(results['lexical_results'])} results")
    else:
        print_error("  Lexical search: failed or no results")

    if results.get("vector_results"):
        print_success(f"  Vector search: {len(results['vector_results'])} results")
    else:
        print_error("  Vector search: failed or no results")

    if results.get("hybrid_results"):
        print_success(f"  Hybrid search: {len(results['hybrid_results'])} results")
    else:
        print_error("  Hybrid search: failed or no results")

    print(f"\n{Colors.OKGREEN}{Colors.BOLD}All tests completed!{Colors.ENDC}\n")


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Test OpenSearch cluster health and search functionality"
    )

    # Required arguments
    parser.add_argument(
        "--opensearch-host", type=str, required=True, help="OpenSearch domain endpoint"
    )
    parser.add_argument(
        "--local-role-arn",
        type=str,
        help="IAM role ARN for local OpenSearch access (required when STAGE=local)",
    )

    # Optional arguments
    parser.add_argument(
        "--region",
        type=str,
        default="us-east-1",
        help="AWS region (default: us-east-1)",
    )
    parser.add_argument(
        "--index-name",
        type=str,
        default="trading-knowledge",
        help="Index name to test (default: trading-knowledge)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=3,
        help="Number of sample documents to retrieve (default: 3)",
    )
    parser.add_argument(
        "--test-query",
        type=str,
        default="RSI trading strategy",
        help="Search query for testing (default: 'RSI trading strategy')",
    )
    parser.add_argument(
        "--search-k",
        type=int,
        default=5,
        help="Number of search results to retrieve (default: 5)",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default="amazon.titan-embed-text-v1",
        help="Bedrock embedding model ID (default: amazon.titan-embed-text-v1)",
    )

    # Action flags - specify which tests to run
    parser.add_argument(
        "--health",
        action="store_true",
        help="Run health checks (cluster and index)",
    )
    parser.add_argument("--lexical", action="store_true", help="Run lexical search test")
    parser.add_argument("--vector", action="store_true", help="Run vector search test")
    parser.add_argument("--hybrid", action="store_true", help="Run hybrid search test")
    parser.add_argument(
        "--delete-data",
        action="store_true",
        help="Delete documents by type (requires --doc-type parameter)",
    )
    parser.add_argument(
        "--doc-type",
        type=str,
        choices=["test-doc"],
        help="Document type to delete (e.g., 'test-doc'). Required with --delete-data",
    )
    parser.add_argument(
        "--stat",
        action="store_true",
        help="Show data statistics grouped by title and metadata",
    )
    parser.add_argument(
        "--recreate-index",
        action="store_true",
        help="⚠️  DANGER: Recreate index (deletes ALL data and creates new index)",
    )
    parser.add_argument(
        "--vector-dimension",
        type=int,
        default=1536,
        help="Vector dimension for index creation (default: 1536)",
    )

    return parser.parse_args()


def main():
    """Main test workflow."""
    args = parse_args()

    print(f"\n{Colors.HEADER}{Colors.BOLD}")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║        OpenSearch Health Check & Search Testing Tool              ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")

    print_info("Host", args.opensearch_host)
    print_info("Region", args.region)
    print_info("Index", args.index_name)
    print_info("Test Query", f'"{args.test_query}"')
    print_info("Timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Store results
    test_results = {}

    try:
        # Initialize OpenSearch repository
        print("\nInitializing OpenSearch connection...")
        repo = OpenSearchRepository(
            host=args.opensearch_host,
            region=args.region,
            index_name=args.index_name,
            local_role_arn=args.local_role_arn,
        )
        print_success("Connected to OpenSearch\n")

        # Handle delete operation
        if args.delete_data:
            if not args.doc_type:
                print_error("--doc_type parameter is required when using --delete-data")
                print_warning("Example: --delete-data --doc_type test-doc")
                sys.exit(1)
            delete_result = delete_documents_by_query(repo, doc_type=args.doc_type)
            test_results["delete_result"] = delete_result
            # Exit after deletion
            return

        # Handle statistics display
        if args.stat:
            stats_result = show_data_statistics(repo)
            test_results["stats"] = stats_result
            # Exit after showing statistics
            return

        # Handle index recreation
        if args.recreate_index:
            recreate_result = recreate_index(repo, vector_dimension=args.vector_dimension)
            test_results["recreate_result"] = recreate_result
            # Exit after recreation
            return

        # If no action flags specified, run all tests
        if not (args.health or args.lexical or args.vector or args.hybrid):
            args.health = True
            args.lexical = True
            args.vector = True
            args.hybrid = True

        # Run health checks
        if args.health:
            cluster_health = check_cluster_health(repo)
            test_results["cluster"] = cluster_health

            index_health = check_index_health(repo)
            test_results["index"] = index_health

        # Initialize embedder if needed for vector/hybrid searches
        embedder = None
        if args.vector or args.hybrid:
            embedder = EmbeddingService(model_id=args.embedding_model, region_name=args.region)

        # Run lexical search
        if args.lexical:
            lexical_results = test_lexical_search(repo, args.test_query, k=args.search_k)
            test_results["lexical_results"] = lexical_results

        # Run vector search
        if args.vector and embedder:
            vector_results = test_vector_search(repo, embedder, args.test_query, k=args.search_k)
            test_results["vector_results"] = vector_results

        # Run hybrid search
        if args.hybrid and embedder:
            hybrid_results = test_hybrid_search(
                repo, embedder, args.test_query, k=args.search_k, alpha=0.5
            )
            test_results["hybrid_results"] = hybrid_results

        # Print summary
        print_summary(test_results)

    except Exception as e:
        print_error(f"Test failed with error: {e}")
        logger.exception("Detailed error:")
        sys.exit(1)


if __name__ == "__main__":
    main()
