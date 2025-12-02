"""
Bedrock Service - AWS Bedrock LLM Integration

Provides interface to AWS Bedrock for Claude 3 Sonnet/Haiku models.
Handles prompt construction, API calls, response parsing, and error handling.
"""

import json
import logging
from typing import Any, Dict, Optional

import boto3
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class BedrockService:
    """
    Service for interacting with AWS Bedrock LLMs.

    Supports:
    - Claude 3 Sonnet (primary, high accuracy)
    - Claude 3 Haiku (fallback, cost-efficient)
    - Structured JSON output parsing
    - Retry logic with exponential backoff
    - Error handling and fallback
    """

    # Model IDs
    CLAUDE_OPUS_4_5 = "anthropic.claude-opus-4-5-20251101-v1:0"
    CLAUDE_SONNET_4_5 = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    CLAUDE_3_SONNET = "anthropic.claude-3-sonnet-20240229-v1:0"
    CLAUDE_3_HAIKU = "anthropic.claude-3-haiku-20240307-v1:0"

    def __init__(
        self,
        region_name: str = "us-east-1",
        primary_model: str = CLAUDE_OPUS_4_5,
        fallback_model: Optional[str] = CLAUDE_SONNET_4_5,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ):
        """
        Initialize Bedrock service.

        Args:
            region_name: AWS region for Bedrock
            primary_model: Primary model ID to use
            fallback_model: Fallback model ID (None to disable fallback)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0-1.0, lower = more deterministic)
        """
        self.region_name = region_name
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Initialize Bedrock Runtime client
        self.client = boto3.client(service_name="bedrock-runtime", region_name=region_name)

        logger.info(
            f"Initialized BedrockService "
            f"(region={region_name}, primary={primary_model}, "
            f"fallback={fallback_model}, temp={temperature})"
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        response_format: str = "json",
    ) -> Dict[str, Any]:
        """
        Generate response from Claude model.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt for instruction
            response_format: Expected format ("json" or "text")

        Returns:
            Dictionary containing response and metadata

        Raises:
            Exception: If all attempts fail (after retries)
        """
        try:
            response = self._invoke_model(
                model_id=self.primary_model,
                prompt=prompt,
                system_prompt=system_prompt,
            )
            logger.info(f"Generated response using {self.primary_model}")
            return self._parse_response(response, response_format)

        except Exception as e:
            logger.error(f"Primary model {self.primary_model} failed: {e}")

            # Try fallback model if configured
            if self.fallback_model:
                logger.info(f"Attempting fallback to {self.fallback_model}")
                try:
                    response = self._invoke_model(
                        model_id=self.fallback_model,
                        prompt=prompt,
                        system_prompt=system_prompt,
                    )
                    logger.info(f"Generated response using fallback {self.fallback_model}")
                    return self._parse_response(response, response_format)
                except Exception as fallback_error:
                    logger.error(f"Fallback model also failed: {fallback_error}")
                    raise

            # No fallback configured, re-raise original error
            raise

    def _invoke_model(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Invoke Bedrock model with prompt.

        Args:
            model_id: Model ID to invoke
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            Raw response from Bedrock API
        """
        # Construct messages for Claude
        messages = [{"role": "user", "content": prompt}]

        # Build request body
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": messages,
        }

        # Add system prompt if provided
        if system_prompt:
            body["system"] = system_prompt

        # Invoke model
        response = self.client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        # Parse response body
        response_body = json.loads(response["body"].read())
        return response_body

    def _parse_response(self, response: Dict[str, Any], response_format: str) -> Dict[str, Any]:
        """
        Parse Bedrock response.

        Args:
            response: Raw Bedrock response
            response_format: Expected format ("json" or "text")

        Returns:
            Parsed response dictionary
        """
        # Extract content from Claude response
        content_blocks = response.get("content", [])
        if not content_blocks:
            raise ValueError("Empty response from model")

        # Get text from first content block
        text_content = content_blocks[0].get("text", "")

        # Parse based on expected format
        if response_format == "json":
            try:
                # Try to extract JSON from response
                parsed_json = self._extract_json(text_content)
                return {
                    "content": parsed_json,
                    "raw_text": text_content,
                    "usage": response.get("usage", {}),
                    "stop_reason": response.get("stop_reason", ""),
                }
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from response: {e}")
                logger.error(f"Raw text: {text_content[:200]}...")
                # Return as text if JSON parsing fails
                return {
                    "content": {"error": "JSON parse failed", "text": text_content},
                    "raw_text": text_content,
                    "usage": response.get("usage", {}),
                    "stop_reason": response.get("stop_reason", ""),
                }
        else:
            # Return as plain text
            return {
                "content": text_content,
                "raw_text": text_content,
                "usage": response.get("usage", {}),
                "stop_reason": response.get("stop_reason", ""),
            }

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """
        Extract JSON from text that may contain markdown code blocks.

        Args:
            text: Text potentially containing JSON

        Returns:
            Parsed JSON dictionary
        """
        # Try direct JSON parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to extract from markdown code blocks
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                json_str = text[start:end].strip()
                return json.loads(json_str)
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                json_str = text[start:end].strip()
                return json.loads(json_str)

        # If no code blocks, try to find JSON object in text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_str = text[start : end + 1]
            return json.loads(json_str)

        # Failed to extract JSON
        raise json.JSONDecodeError("No valid JSON found in text", text, 0)

    def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema_example: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON response.

        Args:
            prompt: User prompt
            system_prompt: Optional system instruction
            schema_example: Optional JSON schema example to guide output

        Returns:
            Parsed JSON response
        """
        # Add JSON instruction to prompt if schema provided
        if schema_example:
            prompt = (
                f"{prompt}\n\n"
                f"Respond with valid JSON matching this structure:\n"
                f"```json\n{json.dumps(schema_example, indent=2)}\n```"
            )

        # Generate with JSON format
        response = self.generate(prompt=prompt, system_prompt=system_prompt, response_format="json")

        return response


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Initialize service
    bedrock_service = BedrockService()

    # Example: Simple text generation
    # system_prompt = "You are a trading expert analyzing market conditions."
    # prompt = "Explain what RSI divergence means for swing trading."
    #
    # response = bedrock_service.generate(
    #     prompt=prompt,
    #     system_prompt=system_prompt,
    #     response_format="text"
    # )
    #
    # print(f"\n=== Response ===")
    # print(response["content"])

    # Example: Structured JSON generation
    # schema = {
    #     "signal_type": "BUY or SELL",
    #     "strategy": "strategy name",
    #     "entry_price": 0.0,
    #     "target_price": 0.0,
    #     "stop_loss": 0.0,
    #     "confidence": 0.0,
    #     "reasoning": "explanation"
    # }
    #
    # prompt = "Analyze AAPL at $180.50 with RSI=42 near support at $178."
    # system_prompt = "You are a trading signal generator. Output valid JSON."
    #
    # response = bedrock_service.generate_structured(
    #     prompt=prompt,
    #     system_prompt=system_prompt,
    #     schema_example=schema
    # )
    #
    # print(f"\n=== Structured Response ===")
    # print(json.dumps(response["content"], indent=2))

    print("BedrockService initialized")
