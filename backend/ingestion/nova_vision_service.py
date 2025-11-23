"""
Nova Vision Service for Trading Knowledge Base

Uses Amazon Nova's vision capabilities to analyze and describe images.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from .image_processor import ExtractedImage

logger = logging.getLogger(__name__)


class NovaVisionService:
    """
    Service for analyzing images using Amazon Nova vision model.

    Features:
    - Image description generation
    - Technical element extraction (RSI, MACD, patterns, etc.)
    - Chart type identification
    - Trading-specific analysis
    """

    def __init__(
        self,
        model_id: str = "amazon.nova-pro-v1:0",
        region_name: str = "us-east-1",
        max_retries: int = 3,
    ):
        """
        Initialize Nova vision service.

        Args:
            model_id: Nova model ID for vision tasks
            region_name: AWS region
            max_retries: Maximum retry attempts for API failures
        """
        self.model_id = model_id
        self.max_retries = max_retries

        # Initialize Bedrock client
        self.bedrock_runtime = boto3.client(service_name="bedrock-runtime", region_name=region_name)

        logger.info(f"Initialized NovaVisionService with model {model_id}")

    def describe_image(
        self, image_bytes: bytes, image_format: str = "png", context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive description of an image.

        Args:
            image_bytes: Image data as bytes
            image_format: Image format (png, jpeg, etc.)
            context: Optional context about the image (page content, etc.)

        Returns:
            Dictionary with description and metadata
        """
        prompt = self._build_image_description_prompt(context)

        try:
            response = self._invoke_vision_model(image_bytes, image_format, prompt)
            description = self._extract_description_from_response(response)

            # Parse technical elements from description
            technical_elements = self._extract_technical_elements(description)

            return {
                "description": description,
                "technical_elements": technical_elements,
                "image_type": self._identify_image_type(description),
                "confidence": "high",  # Nova doesn't provide confidence scores
            }

        except Exception as e:
            logger.error(f"Failed to describe image: {e}")
            raise

    def describe_chart(self, image_bytes: bytes, image_format: str = "png") -> Dict[str, Any]:
        """
        Generate detailed description of a trading chart.

        Args:
            image_bytes: Image data as bytes
            image_format: Image format (png, jpeg, etc.)

        Returns:
            Dictionary with chart analysis
        """
        prompt = """Analyze this trading chart and provide a detailed description including:

1. Chart Type: (candlestick, line, bar, etc.)
2. Timeframe: If visible, what timeframe is shown?
3. Technical Indicators: List ALL visible indicators (RSI, MACD, Moving Averages, Bollinger Bands, Volume, etc.)
4. Key Levels: Support and resistance levels, if visible
5. Patterns: Any chart patterns (head and shoulders, double top/bottom, triangles, wedges, flags, etc.)
6. Price Action: Describe the trend and price movement
7. Volume Analysis: If volume is shown, describe the pattern
8. Notable Features: Any other significant elements

Format your response clearly with these sections."""

        try:
            response = self._invoke_vision_model(image_bytes, image_format, prompt)
            description = self._extract_description_from_response(response)

            return {
                "description": description,
                "image_type": "chart",
                "technical_elements": self._extract_technical_elements(description),
            }

        except Exception as e:
            logger.error(f"Failed to describe chart: {e}")
            raise

    def describe_page(
        self, image_bytes: bytes, image_format: str = "png", page_number: int = 0
    ) -> Dict[str, Any]:
        """
        Generate description of a full page image for context.

        Args:
            image_bytes: Image data as bytes
            image_format: Image format (png, jpeg, etc.)
            page_number: Page number for context

        Returns:
            Dictionary with page description
        """
        prompt = f"""Describe this page (page {page_number}) from a trading book. Include:

1. Layout: How is the content organized? (text, charts, diagrams, tables, etc.)
2. Main Topic: What is the primary subject of this page?
3. Visual Elements: List all charts, diagrams, or images with their positions
4. Text Sections: Brief description of text content and structure
5. Key Concepts: What trading concepts are being explained?

Keep the description concise but comprehensive for document retrieval."""

        try:
            response = self._invoke_vision_model(image_bytes, image_format, prompt)
            description = self._extract_description_from_response(response)

            return {
                "description": description,
                "image_type": "page",
                "page_number": page_number,
            }

        except Exception as e:
            logger.error(f"Failed to describe page: {e}")
            raise

    def batch_describe_images(
        self, images: List[ExtractedImage], image_type: str = "auto"
    ) -> List[Dict[str, Any]]:
        """
        Describe multiple images in batch.

        Args:
            images: List of ExtractedImage objects
            image_type: Type of images ('auto', 'chart', 'diagram', 'page')

        Returns:
            List of description dictionaries
        """
        descriptions = []

        for i, image in enumerate(images):
            try:
                logger.info(f"Describing image {i+1}/{len(images)}: {image.image_id}")

                if image_type == "chart":
                    desc = self.describe_chart(image.image_bytes, image.image_format.lower())
                elif image_type == "page":
                    desc = self.describe_page(
                        image.image_bytes, image.image_format.lower(), image.page_number
                    )
                else:
                    desc = self.describe_image(image.image_bytes, image.image_format.lower())

                desc["image_id"] = image.image_id
                desc["page_number"] = image.page_number
                descriptions.append(desc)

            except Exception as e:
                logger.error(f"Failed to describe image {image.image_id}: {e}")
                # Add error placeholder
                descriptions.append(
                    {
                        "image_id": image.image_id,
                        "page_number": image.page_number,
                        "description": "Error generating description",
                        "error": str(e),
                    }
                )

        logger.info(f"Generated {len(descriptions)} image descriptions")
        return descriptions

    def _build_image_description_prompt(self, context: Optional[str] = None) -> str:
        """Build prompt for general image description."""
        base_prompt = """Describe this image from a trading/finance book. Focus on:

1. Type of image (chart, diagram, screenshot, table, illustration)
2. Main content and purpose
3. Technical indicators or concepts shown (if any)
4. Key visual elements and their arrangement
5. Any text or labels visible

Keep the description clear and detailed for search and retrieval purposes."""

        if context:
            base_prompt += f"\n\nContext: {context}"

        return base_prompt

    def _invoke_vision_model(
        self, image_bytes: bytes, image_format: str, prompt: str
    ) -> Dict[str, Any]:
        """
        Invoke Nova vision model.

        Args:
            image_bytes: Image data
            image_format: Image format
            prompt: Text prompt for the model

        Returns:
            Model response
        """
        import base64

        # Encode image to base64
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Build request body for Nova
        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": {"format": image_format, "source": {"bytes": image_base64}}},
                        {"text": prompt},
                    ],
                }
            ],
            "inferenceConfig": {"maxTokens": 1000, "temperature": 0.7, "topP": 0.9},
        }

        # Invoke model
        try:
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )

            # Parse response
            response_body = json.loads(response["body"].read())
            return response_body

        except ClientError as e:
            logger.error(f"Bedrock API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error invoking vision model: {e}")
            raise

    def _extract_description_from_response(self, response: Dict[str, Any]) -> str:
        """Extract description text from Nova response."""
        try:
            # Nova response format: {"output": {"message": {"content": [{"text": "..."}]}}}
            content = response.get("output", {}).get("message", {}).get("content", [])

            for item in content:
                if "text" in item:
                    return item["text"]

            raise ValueError("No text content found in response")

        except Exception as e:
            logger.error(f"Failed to extract description: {e}")
            raise

    def _extract_technical_elements(self, description: str) -> List[str]:
        """
        Extract technical indicators and patterns from description.

        Args:
            description: Image description text

        Returns:
            List of technical elements found
        """
        elements = []

        # Common technical indicators
        indicators = [
            "RSI",
            "MACD",
            "Moving Average",
            "MA",
            "EMA",
            "SMA",
            "Bollinger Bands",
            "Stochastic",
            "Volume",
            "ATR",
            "Fibonacci",
            "Support",
            "Resistance",
            "Trend Line",
        ]

        # Chart patterns
        patterns = [
            "Head and Shoulders",
            "Double Top",
            "Double Bottom",
            "Triangle",
            "Wedge",
            "Flag",
            "Pennant",
            "Cup and Handle",
            "Channel",
            "Breakout",
            "Reversal",
            "Continuation",
        ]

        # Search for elements in description (case-insensitive)
        description_lower = description.lower()

        for indicator in indicators:
            if indicator.lower() in description_lower:
                elements.append(indicator)

        for pattern in patterns:
            if pattern.lower() in description_lower:
                elements.append(pattern)

        return list(set(elements))  # Remove duplicates

    def _identify_image_type(self, description: str) -> str:
        """
        Identify image type from description.

        Args:
            description: Image description

        Returns:
            Image type string
        """
        description_lower = description.lower()

        # Check for specific types
        if any(word in description_lower for word in ["chart", "candlestick", "graph", "plot"]):
            return "chart"
        elif any(word in description_lower for word in ["diagram", "flowchart", "schematic"]):
            return "diagram"
        elif "table" in description_lower:
            return "table"
        elif "screenshot" in description_lower:
            return "screenshot"
        else:
            return "illustration"


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    from pathlib import Path

    from .image_processor import ExtractionMethod, ImageProcessor

    # Initialize services
    vision_service = NovaVisionService(region_name="us-east-1")
    image_processor = ImageProcessor(extraction_method=ExtractionMethod.GET_IMAGES)

    # Extract and describe images from a PDF
    pdf_path = Path("data/sample_data/4_page_with_image.pdf")
    if pdf_path.exists():
        images = image_processor.extract_images_from_pdf(pdf_path, "test_doc")
        print(f"Extracted {len(images)} images")

        if images:
            # Describe first image
            desc = vision_service.describe_image(
                images[0].image_bytes, images[0].image_format.lower()
            )
            print(f"\nDescription: {desc['description']}")
            print(f"Technical Elements: {desc['technical_elements']}")
            print(f"Image Type: {desc['image_type']}")
