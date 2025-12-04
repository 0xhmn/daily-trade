"""
Multimodal Embedding Service for Trading Knowledge Base

Generates embeddings using AWS Bedrock Nova Multimodal Embeddings.
Supports:
- Text embeddings
- Image embeddings (from charts, diagrams, etc.)
- Unified semantic space for crossmodal retrieval
"""

import base64
import io
import json
import logging
import time
from typing import List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError
from PIL import Image

logger = logging.getLogger(__name__)


class NovaMultimodalEmbeddingService:
    """
    Service for generating multimodal embeddings using Amazon Nova.

    Features:
    - Unified embeddings for text and images via Nova
    - Crossmodal retrieval capability
    - Flexible output dimensions (3072, 1024, 384, 256)
    - Batch processing with retry logic
    - Purpose-specific embeddings (indexing vs retrieval)
    """

    def __init__(
        self,
        model_id: str = "amazon.nova-2-multimodal-embeddings-v1:0",
        embedding_dimension: int = 1024,
        region_name: str = "us-east-1",
        batch_size: int = 25,
        max_retries: int = 3,
    ):
        """
        Initialize Nova multimodal embedding service.

        Args:
            model_id: Bedrock Nova embedding model ID
            embedding_dimension: Output dimension (3072, 1024, 384, or 256)
            region_name: AWS region
            batch_size: Number of items to process in one batch
            max_retries: Maximum retry attempts for API failures
        """
        self.model_id = model_id
        self.embedding_dimension = embedding_dimension
        self.batch_size = batch_size
        self.max_retries = max_retries

        # Validate dimension
        valid_dimensions = [3072, 1024, 384, 256]
        if embedding_dimension not in valid_dimensions:
            raise ValueError(
                f"embedding_dimension must be one of {valid_dimensions}, "
                f"got {embedding_dimension}"
            )

        # Initialize Bedrock client
        self.bedrock_runtime = boto3.client(service_name="bedrock-runtime", region_name=region_name)

        logger.info(
            f"Initialized NovaMultimodalEmbeddingService: "
            f"model={model_id}, dimension={embedding_dimension}"
        )

    def generate_text_embedding(
        self,
        text: str,
        purpose: str = "GENERIC_INDEX",
    ) -> List[float]:
        """
        Generate text embedding using Nova.

        Args:
            text: Text to embed
            purpose: Embedding purpose - "GENERIC_INDEX" for indexing,
                    "GENERIC_RETRIEVAL" for query,
                    "DOCUMENT_RETRIEVAL" for document-specific retrieval

        Returns:
            Text embedding vector
        """
        for attempt in range(self.max_retries):
            try:
                request_body = {
                    "taskType": "SINGLE_EMBEDDING",
                    "singleEmbeddingParams": {
                        "embeddingPurpose": purpose,
                        "embeddingDimension": self.embedding_dimension,
                        "text": {
                            "truncationMode": "END",
                            "value": text,
                        },
                    },
                }

                response = self.bedrock_runtime.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(request_body),
                    contentType="application/json",
                    accept="application/json",
                )

                response_body = json.loads(response["body"].read())
                embedding = response_body["embeddings"][0]["embedding"]

                if len(embedding) != self.embedding_dimension:
                    logger.warning(
                        f"Unexpected embedding dimension: {len(embedding)}, "
                        f"expected {self.embedding_dimension}"
                    )

                return embedding

            except ClientError as e:
                if self._should_retry(e, attempt):
                    continue
                raise
            except Exception as e:
                logger.error(f"Error generating text embedding: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2**attempt)

        raise RuntimeError(f"Failed to generate text embedding after {self.max_retries} attempts")

    def _get_image_dimensions(self, image_bytes: bytes) -> Tuple[int, int]:
        """
        Extract width and height from image bytes.

        Args:
            image_bytes: Image bytes

        Returns:
            Tuple of (width, height)
        """
        img = Image.open(io.BytesIO(image_bytes))
        return img.size

    def _validate_aspect_ratio(self, width: int, height: int, max_ratio: float = 20.0) -> bool:
        """
        Validate image aspect ratio is within acceptable bounds.

        Args:
            width: Image width in pixels
            height: Image height in pixels
            max_ratio: Maximum allowed aspect ratio (default: 20.0)

        Returns:
            True if aspect ratio is valid (between 1/max_ratio and max_ratio)
        """
        if width == 0 or height == 0:
            return False

        ratio = width / height
        return (1 / max_ratio) <= ratio <= max_ratio

    def generate_image_embedding(
        self,
        image_bytes: bytes,
        image_format: str = "png",
        purpose: str = "GENERIC_INDEX",
    ) -> List[float]:
        """
        Generate image embedding using Nova.

        Args:
            image_bytes: Image bytes
            image_format: Image format (png, jpeg)
            purpose: Embedding purpose - "GENERIC_INDEX" for indexing,
                    "GENERIC_RETRIEVAL" for query

        Returns:
            Image embedding vector, or empty list if aspect ratio is invalid
        """
        # Validate aspect ratio before sending to Bedrock
        try:
            width, height = self._get_image_dimensions(image_bytes)
            if not self._validate_aspect_ratio(width, height):
                ratio = width / height if height > 0 else float("inf")
                logger.warning(
                    f"Skipping image with invalid aspect ratio: {width}x{height} "
                    f"(ratio: {ratio:.2f}, max: 20:1)"
                )
                return []
        except Exception as e:
            logger.warning(f"Failed to validate image dimensions: {e}")
            return []

        for attempt in range(self.max_retries):
            try:
                # Encode image to base64
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")

                request_body = {
                    "taskType": "SINGLE_EMBEDDING",
                    "singleEmbeddingParams": {
                        "embeddingPurpose": purpose,
                        "embeddingDimension": self.embedding_dimension,
                        "image": {
                            "format": image_format.lower(),
                            "source": {"bytes": image_base64},
                        },
                    },
                }

                response = self.bedrock_runtime.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(request_body),
                    contentType="application/json",
                    accept="application/json",
                )

                response_body = json.loads(response["body"].read())
                embedding = response_body["embeddings"][0]["embedding"]

                if len(embedding) != self.embedding_dimension:
                    logger.warning(
                        f"Unexpected embedding dimension: {len(embedding)}, "
                        f"expected {self.embedding_dimension}"
                    )

                return embedding

            except ClientError as e:
                if self._should_retry(e, attempt):
                    continue
                raise
            except Exception as e:
                logger.error(f"Error generating image embedding: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2**attempt)

        raise RuntimeError(f"Failed to generate image embedding after {self.max_retries} attempts")

    def generate_text_embeddings_batch(
        self,
        texts: List[str],
        purpose: str = "GENERIC_INDEX",
    ) -> List[List[float]]:
        """
        Generate text embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            purpose: Embedding purpose

        Returns:
            List of text embedding vectors
        """
        embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            logger.info(f"Processing text batch {i // self.batch_size + 1}, size: {len(batch)}")

            for text in batch:
                embedding = self.generate_text_embedding(text, purpose=purpose)
                embeddings.append(embedding)

            # Rate limiting
            if i + self.batch_size < len(texts):
                time.sleep(0.5)

        logger.info(f"Generated {len(embeddings)} text embeddings")
        return embeddings

    def generate_image_embeddings_batch(
        self,
        images: List[bytes],
        formats: Optional[List[str]] = None,
        purpose: str = "GENERIC_INDEX",
    ) -> List[List[float]]:
        """
        Generate image embeddings for multiple images.

        Args:
            images: List of image bytes
            formats: List of image formats (defaults to 'png' for all)
            purpose: Embedding purpose

        Returns:
            List of image embedding vectors
        """
        if formats is None:
            formats = ["png"] * len(images)

        embeddings = []

        for i in range(0, len(images), self.batch_size):
            batch_images = images[i : i + self.batch_size]
            batch_formats = formats[i : i + self.batch_size]
            logger.info(
                f"Processing image batch {i // self.batch_size + 1}, " f"size: {len(batch_images)}"
            )

            for img_bytes, img_format in zip(batch_images, batch_formats):
                embedding = self.generate_image_embedding(img_bytes, img_format, purpose=purpose)
                embeddings.append(embedding)

            # Rate limiting
            if i + self.batch_size < len(images):
                time.sleep(0.5)

        logger.info(f"Generated {len(embeddings)} image embeddings")
        return embeddings

    def _should_retry(self, error: ClientError, attempt: int) -> bool:
        """Determine if request should be retried."""
        error_code = error.response.get("Error", {}).get("Code", "")

        if error_code == "ThrottlingException":
            wait_time = (2**attempt) * 1
            logger.warning(
                f"Throttled, retrying in {wait_time}s "
                f"(attempt {attempt + 1}/{self.max_retries})"
            )
            time.sleep(wait_time)
            return attempt < self.max_retries - 1

        return False

    def validate_embedding(self, embedding: List[float]) -> bool:
        """Validate embedding vector."""
        if len(embedding) != self.embedding_dimension:
            logger.error(
                f"Invalid embedding dimension: {len(embedding)}, "
                f"expected {self.embedding_dimension}"
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
    embedder = NovaMultimodalEmbeddingService(embedding_dimension=1024, region_name="us-east-1")

    # Test text embedding
    test_text = "The RSI indicator shows overbought conditions at 75."
    text_embedding = embedder.generate_text_embedding(test_text)
    print(f"\nGenerated text embedding with dimension: {len(text_embedding)}")
    print(f"First 5 values: {text_embedding[:5]}")
    print(f"Valid: {embedder.validate_embedding(text_embedding)}")

    # Test batch text embeddings
    test_texts = [
        "Buy signal: Price above 50-day moving average.",
        "Sell signal: Bearish engulfing pattern detected.",
        "Hold: Market is in consolidation phase.",
    ]
    embeddings = embedder.generate_text_embeddings_batch(test_texts)
    print(f"\nGenerated {len(embeddings)} batch text embeddings")

    # Test image embedding (requires actual image bytes)
    # with open("path/to/image.png", "rb") as f:
    #     image_bytes = f.read()
    # image_embedding = embedder.generate_image_embedding(image_bytes, "png")
    # print(f"Generated image embedding with dimension: {len(image_embedding)}")
    # print(f"Valid: {embedder.validate_embedding(image_embedding)}")
