"""
OpenSearch Repository for Trading Knowledge Base

Handles vector storage, indexing, and hybrid search (vector + lexical).
"""

import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from opensearchpy import OpenSearch, RequestsHttpConnection  # type: ignore
from opensearchpy.helpers import bulk  # type: ignore
import boto3
from requests_aws4auth import AWS4Auth  # type: ignore

# Add backend to path for utils import
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.aws_credentials import get_credentials_for_opensearch

logger = logging.getLogger(__name__)


class OpenSearchRepository:
    """
    Repository for managing trading knowledge base in OpenSearch.

    Features:
    - Index creation with kNN vector configuration
    - Document indexing with embeddings
    - Hybrid search (vector + BM25 lexical)
    - Reciprocal Rank Fusion (RRF)
    - Metadata filtering
    """

    def __init__(
        self,
        host: str,
        region: str = "us-east-1",
        index_name: str = "trading-knowledge",
        use_ssl: bool = True,
        verify_certs: bool = True,
        local_role_arn: Optional[str] = None,
    ):
        """
        Initialize OpenSearch repository.

        Automatically handles credentials based on STAGE environment variable:
        - STAGE=local: Assumes local_role_arn (required)
        - STAGE=prod: Uses default credentials (task role)

        Args:
            host: OpenSearch domain endpoint
            region: AWS region
            index_name: Name of the index to use
            use_ssl: Use SSL connection
            verify_certs: Verify SSL certificates
            local_role_arn: Role ARN to assume for local development (required when STAGE=local)
        """
        self.index_name = index_name
        self.region = region

        # Get appropriate credentials based on environment
        session = get_credentials_for_opensearch(region=region, local_role_arn=local_role_arn)

        credentials = session.get_credentials()
        if credentials is None:
            raise ValueError("AWS credentials not found. Please configure AWS credentials.")

        awsauth = AWS4Auth(
            credentials.access_key,  # type: ignore
            credentials.secret_key,  # type: ignore
            region,
            "es",
            session_token=credentials.token,  # type: ignore
        )

        # Initialize OpenSearch client
        # Set Host header explicitly to match domain endpoint
        self.client = OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=awsauth,
            use_ssl=use_ssl,
            verify_certs=verify_certs,
            connection_class=RequestsHttpConnection,
            timeout=120,  # Increased for bulk operations with large documents
            headers={"Host": host},
        )

        logger.info(f"Initialized OpenSearch repository: {host}, index: {index_name}")

    def create_index(self, vector_dimension: int = 1536, force: bool = False) -> bool:
        """
        Create index with kNN vector configuration.

        Args:
            vector_dimension: Dimension of embedding vectors
            force: If True, delete existing index

        Returns:
            True if index created successfully
        """
        if self.client.indices.exists(index=self.index_name):
            if force:
                logger.warning(f"Deleting existing index: {self.index_name}")
                self.client.indices.delete(index=self.index_name)
            else:
                logger.info(f"Index {self.index_name} already exists")
                return True

        # Index mapping with kNN vector field
        index_body = {
            "settings": {
                "index": {
                    "knn": True,
                    "knn.algo_param.ef_search": 512,
                    "number_of_shards": 2,
                    "number_of_replicas": 1,
                }
            },
            "mappings": {
                "properties": {
                    "text": {"type": "text", "analyzer": "standard"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": vector_dimension,
                        "method": {
                            "name": "hnsw",
                            "space_type": "l2",
                            "engine": "lucene",
                            "parameters": {"ef_construction": 512, "m": 16},
                        },
                    },
                    "metadata": {
                        "properties": {
                            "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                            "author": {"type": "keyword"},
                            "strategy_type": {"type": "keyword"},
                            "timeframe": {"type": "keyword"},
                            "market_conditions": {"type": "keyword"},
                            "asset_class": {"type": "keyword"},
                            "key_concepts": {"type": "keyword"},
                            "source_file": {"type": "keyword"},
                            "chunk_index": {"type": "integer"},
                            "document_type": {"type": "keyword"},
                        }
                    },
                }
            },
        }

        response = self.client.indices.create(index=self.index_name, body=index_body)
        logger.info(f"Created index: {self.index_name}")
        return response.get("acknowledged", False)

    def index_document(
        self, doc_id: str, text: str, embedding: List[float], metadata: Dict[str, Any]
    ) -> bool:
        """
        Index a single document chunk.

        Args:
            doc_id: Unique document ID
            text: Document text
            embedding: Embedding vector
            metadata: Document metadata

        Returns:
            True if indexed successfully
        """
        document = {"text": text, "embedding": embedding, "metadata": metadata}

        response = self.client.index(
            index=self.index_name, id=doc_id, body=document, refresh=True  # type: ignore
        )

        return response.get("result") in ["created", "updated"]

    def index_documents_bulk(self, documents: List[Dict[str, Any]]) -> tuple[int, int]:
        """
        Index multiple documents in bulk.

        Args:
            documents: List of documents with id, text, embedding, metadata

        Returns:
            Tuple of (success_count, failed_count)
        """
        actions = []
        for doc in documents:
            action = {
                "_index": self.index_name,
                "_id": doc["id"],
                "_source": {
                    "text": doc["text"],
                    "embedding": doc["embedding"],
                    "metadata": doc["metadata"],
                },
            }
            actions.append(action)

        success, failed = bulk(
            self.client, actions, raise_on_error=False, refresh=True  # type: ignore
        )

        logger.info(f"Bulk indexed: {success} success, {len(failed)} failed")
        return success, len(failed)

    def vector_search(
        self, query_embedding: List[float], k: int = 10, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform kNN vector search.

        Args:
            query_embedding: Query embedding vector
            k: Number of results to return
            filters: Optional metadata filters

        Returns:
            List of search results with scores
        """
        query = {
            "size": k,
            "query": {"knn": {"embedding": {"vector": query_embedding, "k": k}}},
            "_source": ["text", "metadata"],
        }

        # Add filters if provided
        if filters:
            query["query"] = {
                "bool": {
                    "must": [{"knn": {"embedding": {"vector": query_embedding, "k": k}}}],
                    "filter": self._build_filters(filters),
                }
            }

        response = self.client.search(index=self.index_name, body=query)

        results = []
        for hit in response["hits"]["hits"]:
            results.append(
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "text": hit["_source"]["text"],
                    "metadata": hit["_source"]["metadata"],
                }
            )

        return results

    def lexical_search(
        self, query_text: str, k: int = 10, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform BM25 lexical search.

        Args:
            query_text: Query text
            k: Number of results to return
            filters: Optional metadata filters

        Returns:
            List of search results with scores
        """
        query = {
            "size": k,
            "query": {"match": {"text": query_text}},
            "_source": ["text", "metadata"],
        }

        # Add filters if provided
        if filters:
            query["query"] = {
                "bool": {
                    "must": [{"match": {"text": query_text}}],
                    "filter": self._build_filters(filters),
                }
            }

        response = self.client.search(index=self.index_name, body=query)

        results = []
        for hit in response["hits"]["hits"]:
            results.append(
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "text": hit["_source"]["text"],
                    "metadata": hit["_source"]["metadata"],
                }
            )

        return results

    def hybrid_search(
        self,
        query_text: str,
        query_embedding: List[float],
        k: int = 10,
        alpha: float = 0.5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining vector and lexical search.

        Uses Reciprocal Rank Fusion (RRF) to combine results.

        Args:
            query_text: Query text for lexical search
            query_embedding: Query embedding for vector search
            k: Number of results to return
            alpha: Weight for vector search (0-1), 1-alpha for lexical
            filters: Optional metadata filters

        Returns:
            List of fused search results
        """
        # Perform both searches
        vector_results = self.vector_search(query_embedding, k=k * 2, filters=filters)
        lexical_results = self.lexical_search(query_text, k=k * 2, filters=filters)

        # Apply Reciprocal Rank Fusion
        fused_results = self._reciprocal_rank_fusion(
            vector_results, lexical_results, k=k, alpha=alpha
        )

        return fused_results

    def _reciprocal_rank_fusion(
        self,
        vector_results: List[Dict[str, Any]],
        lexical_results: List[Dict[str, Any]],
        k: int = 10,
        alpha: float = 0.5,
        rank_constant: int = 60,
    ) -> List[Dict[str, Any]]:
        """
        Combine results using Reciprocal Rank Fusion.

        RRF formula: score(d) = sum over all rankings: 1 / (k + rank(d))

        Args:
            vector_results: Results from vector search
            lexical_results: Results from lexical search
            k: Number of final results
            alpha: Weight for vector search
            rank_constant: Constant k in RRF formula

        Returns:
            Fused and ranked results
        """
        # Calculate RRF scores
        scores = {}

        # Vector search scores
        for rank, result in enumerate(vector_results, start=1):
            doc_id = result["id"]
            rrf_score = alpha / (rank_constant + rank)
            if doc_id not in scores:
                scores[doc_id] = {"score": 0, "result": result}
            scores[doc_id]["score"] += rrf_score

        # Lexical search scores
        for rank, result in enumerate(lexical_results, start=1):
            doc_id = result["id"]
            rrf_score = (1 - alpha) / (rank_constant + rank)
            if doc_id not in scores:
                scores[doc_id] = {"score": 0, "result": result}
            scores[doc_id]["score"] += rrf_score

        # Sort by fused score
        fused_results = sorted(scores.values(), key=lambda x: x["score"], reverse=True)[:k]

        # Format results
        return [
            {
                "id": item["result"]["id"],
                "score": item["score"],
                "text": item["result"]["text"],
                "metadata": item["result"]["metadata"],
            }
            for item in fused_results
        ]

    def _build_filters(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Build OpenSearch filter clauses from metadata filters.

        Args:
            filters: Metadata filters

        Returns:
            List of filter clauses
        """
        filter_clauses = []

        for field, value in filters.items():
            if isinstance(value, list):
                # Multiple values - use terms query
                filter_clauses.append({"terms": {f"metadata.{field}": value}})
            else:
                # Single value - use term query
                filter_clauses.append({"term": {f"metadata.{field}": value}})

        return filter_clauses

    def delete_index(self) -> bool:
        """Delete the index."""
        if self.client.indices.exists(index=self.index_name):
            self.client.indices.delete(index=self.index_name)
            logger.info(f"Deleted index: {self.index_name}")
            return True
        return False

    def get_index_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        if not self.client.indices.exists(index=self.index_name):
            return {"exists": False}

        stats = self.client.indices.stats(index=self.index_name)
        count = self.client.count(index=self.index_name)

        return {
            "exists": True,
            "document_count": count["count"],
            "size_in_bytes": stats["indices"][self.index_name]["total"]["store"]["size_in_bytes"],
        }


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Initialize repository (use actual OpenSearch endpoint)
    # repo = OpenSearchRepository(
    #     host="search-trading-knowledge-xxxxx.us-east-1.es.amazonaws.com",
    #     region="us-east-1"
    # )

    # Create index
    # repo.create_index(vector_dimension=1536)

    # Index sample document
    # doc_id = "doc_1_chunk_0"
    # text = "Buy when RSI is below 30 and price is above 50-day moving average."
    # embedding = [0.1] * 1536  # Sample embedding
    # metadata = {
    #     "title": "Technical Analysis Guide",
    #     "strategy_type": "swing_trading",
    #     "timeframe": "3-7 days"
    # }
    # repo.index_document(doc_id, text, embedding, metadata)

    # Search
    # query_embedding = [0.1] * 1536
    # results = repo.hybrid_search(
    #     query_text="RSI overbought signal",
    #     query_embedding=query_embedding,
    #     k=5
    # )

    print("OpenSearch repository initialized")
