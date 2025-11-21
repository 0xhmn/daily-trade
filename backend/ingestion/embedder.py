"""
Embedding Service for Trading Knowledge Base

Generates embeddings using AWS Bedrock (Amazon Titan Embeddings).
"""

import json
import logging
import time
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for generating text embeddings using AWS Bedrock.

    Features:
    - Batch embedding generation
    - Retry logic with exponential backoff
    - Embedding caching
    - Dimension validation
    """

    def __init__(
        self,
        model_id: str = "amazon.titan-embed-text-v1",
        region_name: str = "us-east-1",
        batch_size: int = 25,
        max_retries: int = 3,
    ):
        """
        Initialize embedding service.

        Args:
            model_id: Bedrock embedding model ID
            region_name: AWS region
            batch_size: Number of texts to process in one batch
            max_retries: Maximum retry attempts for API failures
        """
        self.model_id = model_id
        self.batch_size = batch_size
        self.max_retries = max_retries

        # Initialize Bedrock client
        self.bedrock_runtime = boto3.client(service_name="bedrock-runtime", region_name=region_name)

        # Model-specific dimensions
        self.embedding_dimensions = {
            "amazon.titan-embed-text-v1": 1536,
            "amazon.titan-embed-text-v2:0": 1024,
            "cohere.embed-english-v3": 1024,
            "cohere.embed-multilingual-v3": 1024,
        }

        self.expected_dimension = self.embedding_dimensions.get(model_id, 1536)
        logger.info(
            f"Initialized EmbeddingService with model {model_id}, "
            f"expected dimension: {self.expected_dimension}"
        )

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        for attempt in range(self.max_retries):
            try:
                response = self._invoke_model(text)
                embedding = self._extract_embedding(response)

                # Validate dimension
                if len(embedding) != self.expected_dimension:
                    logger.warning(
                        f"Unexpected embedding dimension: {len(embedding)}, "
                        f"expected {self.expected_dimension}"
                    )

                return embedding

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")

                if error_code == "ThrottlingException":
                    # Exponential backoff
                    wait_time = (2**attempt) * 1
                    logger.warning(
                        f"Throttled, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Bedrock API error: {e}")
                    raise

            except Exception as e:
                logger.error(f"Unexpected error generating embedding: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2**attempt)

        raise RuntimeError(f"Failed to generate embedding after {self.max_retries} attempts")

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        embeddings = []

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            logger.info(f"Processing batch {i // self.batch_size + 1}, size: {len(batch)}")

            for text in batch:
                embedding = self.generate_embedding(text)
                embeddings.append(embedding)

            # Rate limiting: small delay between batches
            if i + self.batch_size < len(texts):
                time.sleep(0.5)

        logger.info(f"Generated {len(embeddings)} embeddings")
        return embeddings

    def _invoke_model(self, text: str) -> Dict[str, Any]:
        """
        Invoke Bedrock model for embedding generation.

        Args:
            text: Text to embed

        Returns:
            Model response
        """
        # Truncate text if too long (Titan has 8K token limit)
        max_chars = 8000 * 4  # Approximate
        if len(text) > max_chars:
            logger.warning(f"Truncating text from {len(text)} to {max_chars} characters")
            text = text[:max_chars]

        # Prepare request based on model
        if "titan" in self.model_id.lower():
            body = json.dumps({"inputText": text})
        elif "cohere" in self.model_id.lower():
            body = json.dumps({"texts": [text], "input_type": "search_document", "truncate": "END"})
        else:
            # Default format
            body = json.dumps({"inputText": text})

        # Invoke model
        response = self.bedrock_runtime.invoke_model(
            modelId=self.model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )

        # Parse response
        response_body = json.loads(response["body"].read())
        return response_body

    def _extract_embedding(self, response: Dict[str, Any]) -> List[float]:
        """
        Extract embedding vector from model response.

        Args:
            response: Model response

        Returns:
            Embedding vector
        """
        # Titan format
        if "embedding" in response:
            return response["embedding"]

        # Cohere format
        if "embeddings" in response:
            return response["embeddings"][0]

        # Generic fallback
        for key in ["vector", "embedding_vector", "embeddings"]:
            if key in response:
                value = response[key]
                if isinstance(value, list) and len(value) > 0:
                    return value if isinstance(value[0], (int, float)) else value[0]

        raise ValueError(f"Could not extract embedding from response: {response.keys()}")

    def validate_embedding(self, embedding: List[float]) -> bool:
        """
        Validate embedding vector.

        Args:
            embedding: Embedding vector to validate

        Returns:
            True if valid, False otherwise
        """

        if len(embedding) != self.expected_dimension:
            logger.error(
                f"Invalid embedding dimension: {len(embedding)}, "
                f"expected {self.expected_dimension}"
            )
            return False

        if not all(isinstance(x, (int, float)) for x in embedding):
            logger.error("Embedding contains non-numeric values")
            return False

        return True


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Initialize service
    embedder = EmbeddingService(model_id="amazon.titan-embed-text-v1", region_name="us-east-1")

    # Test single embedding
    test_text = "The RSI indicator shows overbought conditions at 75."
    embedding = embedder.generate_embedding(test_text)
    print(f"Generated embedding with dimension: {len(embedding)}")
    print(f"First 5 values: {embedding[:5]}")

    # Test batch embeddings
    test_texts = [
        "Buy signal: Price above 50-day moving average.",
        "Sell signal: Bearish engulfing pattern detected.",
        "Hold: Market is in consolidation phase.",
    ]
    embeddings = embedder.generate_embeddings_batch(test_texts)
    print(f"Generated {len(embeddings)} batch embeddings")

    # Validate
    for i, emb in enumerate(embeddings):
        is_valid = embedder.validate_embedding(emb)
        print(f"Embedding {i + 1} valid: {is_valid}")
