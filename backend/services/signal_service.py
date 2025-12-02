"""
Signal Service - Trading Signal Generation

Orchestrates the complete signal generation pipeline:
1. Retrieves trading knowledge via RAG
2. Formats context with market data
3. Generates signal via Claude LLM
4. Parses and validates signal
5. Calculates confidence score
"""

import logging
import time
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4

from ..models.signal import Signal, SignalPricing, SignalType, TradingStyle, categorize_confidence
from .bedrock_service import BedrockService
from .prompt_provider import PromptProvider
from .trading_rag_service import TradingRAGService

logger = logging.getLogger(__name__)


class SignalService:
    """
    Service for generating trading signals.

    Combines RAG retrieval with LLM reasoning to generate actionable
    trading signals with proper risk management parameters.

    Supports multiple trading styles via PromptProvider.
    """

    def __init__(
        self,
        rag_service: TradingRAGService,
        bedrock_service: BedrockService,
        prompt_provider: PromptProvider,
        default_style: TradingStyle = TradingStyle.SWING,
    ):
        """
        Initialize signal service.

        Args:
            rag_service: RAG service for context retrieval
            bedrock_service: Bedrock service for LLM generation
            prompt_provider: Prompt provider for style-specific prompts
            default_style: Default trading style (SWING by default)
        """
        self.rag_service = rag_service
        self.bedrock_service = bedrock_service
        self.prompt_provider = prompt_provider
        self.default_style = default_style

        logger.info(f"Initialized SignalService (default_style={default_style.value})")

    def generate_signal(
        self,
        symbol: str,
        market_state: Dict,
        trading_style: Optional[TradingStyle] = None,
        query: Optional[str] = None,
    ) -> Signal:
        """
        Generate trading signal for a symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            market_state: Current market data and indicators
            trading_style: Trading style (SWING or POSITION). Uses default if not provided.
            query: Optional custom query for RAG (auto-generated if not provided)

        Returns:
            Signal object with pricing and reasoning

        Raises:
            ValueError: If signal generation fails or produces invalid data
        """
        start_time = time.time()

        # Use default style if not provided
        style = trading_style or self.default_style

        logger.info(f"Generating {style.value} signal for {symbol}")

        try:
            # Auto-generate query if not provided
            if not query:
                query = self._generate_query(symbol, market_state, style)

            # Prepare context with RAG
            rag_context = self.rag_service.prepare_context(
                query=query, market_state=market_state, max_documents=10
            )

            # Get style-specific prompts from PromptProvider
            system_prompt = self.prompt_provider.get_system_prompt(style)
            signal_prompt = self.prompt_provider.get_signal_prompt(
                style=style, symbol=symbol, context=rag_context.formatted_context
            )
            schema_example = self.prompt_provider.get_schema_example(style)

            # Generate signal via LLM
            response = self.bedrock_service.generate_structured(
                prompt=signal_prompt,
                system_prompt=system_prompt,
                schema_example=schema_example,
            )

            # Parse signal from response
            signal_data = response["content"]

            # Calculate R/R ratio
            risk_reward_ratio = self._calculate_risk_reward(
                signal_type=signal_data["signal_type"],
                entry=signal_data["entry_price"],
                target=signal_data["target_price"],
                stop=signal_data["stop_loss"],
            )

            # Validate pricing logic
            self._validate_pricing(
                signal_type=signal_data["signal_type"],
                entry=signal_data["entry_price"],
                target=signal_data["target_price"],
                stop=signal_data["stop_loss"],
            )

            # Calculate confidence score
            confidence_score = self._calculate_confidence(signal_data, rag_context, market_state)

            # Extract citations
            citations = self._extract_citations(rag_context)

            # Extract image references
            image_refs = self._extract_image_references(rag_context)

            # Create pricing object
            pricing = SignalPricing(
                entry_price=signal_data["entry_price"],
                target_price=signal_data["target_price"],
                stop_loss=signal_data["stop_loss"],
                risk_reward_ratio=risk_reward_ratio,
            )

            # Create signal object
            signal = Signal(
                signal_id=str(uuid4()),
                symbol=symbol,
                generated_at=datetime.utcnow(),
                signal_type=SignalType[signal_data["signal_type"]],
                strategy_name=signal_data["strategy_name"],
                trading_style=style,
                holding_period_days=signal_data["holding_period_days"],
                pricing=pricing,
                confidence_score=confidence_score,
                confidence_level=categorize_confidence(confidence_score),
                reasoning=signal_data["reasoning"],
                citations=citations,
                image_references=image_refs,
                market_context=market_state,
                model_used=self.bedrock_service.primary_model,
                generation_time_ms=(time.time() - start_time) * 1000,
            )

            logger.info(
                f"Generated {signal.signal_type.value} signal for {symbol} "
                f"(confidence: {signal.confidence_score:.2f}, "
                f"R/R: {signal.pricing.risk_reward_ratio:.2f})"
            )

            return signal

        except Exception as e:
            logger.error(f"Failed to generate signal for {symbol}: {e}")
            raise ValueError(f"Signal generation failed: {str(e)}")

    def _generate_query(self, symbol: str, market_state: Dict, style: TradingStyle) -> str:
        """
        Auto-generate RAG query based on market state and trading style.

        Args:
            symbol: Stock symbol
            market_state: Current market data
            style: Trading style

        Returns:
            Query string for RAG retrieval
        """
        # Extract key indicators
        indicators = market_state.get("indicators", {})
        patterns = market_state.get("patterns", [])

        # Try to match market condition to query patterns
        query_pattern = None

        # Check RSI-based patterns
        rsi = indicators.get("RSI")
        if rsi:
            if rsi < 30:
                query_pattern = self.prompt_provider.get_query_pattern(style, "oversold_rsi")
            elif rsi > 70:
                query_pattern = self.prompt_provider.get_query_pattern(style, "overbought_rsi")

        # Check support/resistance patterns
        if not query_pattern:
            support = market_state.get("support_levels", [])
            resistance = market_state.get("resistance_levels", [])
            if support:
                query_pattern = self.prompt_provider.get_query_pattern(style, "support_bounce")
            elif resistance:
                query_pattern = self.prompt_provider.get_query_pattern(style, "resistance_breakout")

        # Check for consolidation pattern
        if not query_pattern and "consolidation" in patterns:
            query_pattern = self.prompt_provider.get_query_pattern(style, "consolidation")

        # Check for trend patterns
        if not query_pattern:
            trend = market_state.get("trend", "")
            if "uptrend" in trend or "strong" in trend:
                query_pattern = self.prompt_provider.get_query_pattern(style, "trend_continuation")

        # Fallback: build custom query or use default pattern
        if not query_pattern:
            query_parts = []

            # Get support/resistance for fallback
            support = market_state.get("support_levels", [])
            resistance = market_state.get("resistance_levels", [])

            # Add RSI context
            if rsi:
                if rsi < 45:
                    query_parts.append("RSI divergence")

            # Add pattern context
            if patterns:
                query_parts.extend(patterns)

            # Add support/resistance context
            if support:
                query_parts.append("support bounce")
            if resistance:
                query_parts.append("resistance breakout")

            # Combine with style prefix
            style_prefix = "swing trade" if style == TradingStyle.SWING else "position trade"
            query = " ".join(query_parts) if query_parts else f"{style_prefix} setup"
            query += " strategy entry exit stop loss"
        else:
            query = query_pattern

        logger.debug(f"Generated query for {symbol} ({style.value}): {query}")
        return query

    def _calculate_risk_reward(
        self, signal_type: str, entry: float, target: float, stop: float
    ) -> float:
        """
        Calculate risk/reward ratio.

        Args:
            signal_type: BUY or SELL
            entry: Entry price
            target: Target price
            stop: Stop loss price

        Returns:
            Risk/reward ratio
        """
        if signal_type == "BUY":
            reward = target - entry
            risk = entry - stop
        elif signal_type == "SELL":
            reward = entry - target
            risk = stop - entry
        else:  # HOLD
            return 0.0

        if risk <= 0:
            raise ValueError(f"Invalid risk: {risk}")

        return reward / risk

    def _validate_pricing(self, signal_type: str, entry: float, target: float, stop: float) -> None:
        """
        Validate pricing logic consistency.

        Args:
            signal_type: BUY, SELL, or HOLD
            entry: Entry price
            target: Target price
            stop: Stop loss price

        Raises:
            ValueError: If pricing is inconsistent
        """
        if signal_type == "BUY":
            if target <= entry:
                raise ValueError("BUY signal: target must be above entry")
            if stop >= entry:
                raise ValueError("BUY signal: stop loss must be below entry")
        elif signal_type == "SELL":
            if target >= entry:
                raise ValueError("SELL signal: target must be below entry")
            if stop <= entry:
                raise ValueError("SELL signal: stop loss must be above entry")

    def _calculate_confidence(self, signal_data: Dict, rag_context, market_state: Dict) -> float:
        """
        Calculate confidence score for signal.

        Factors:
        - Number of supporting citations (35%)
        - Diversity of sources (20%)
        - Key factors identified (25%)
        - Market indicator alignment (20%)

        Args:
            signal_data: Parsed signal data from LLM
            rag_context: RAG context with citations
            market_state: Current market data

        Returns:
            Confidence score (0-1)
        """
        # Citation count score (max 5 citations = 1.0)
        citation_score = min(rag_context.total_documents / 5.0, 1.0) * 0.35

        # Source diversity score (unique sources)
        unique_sources = len(set(c.source_file for c in rag_context.citations))
        diversity_score = min(unique_sources / 3.0, 1.0) * 0.20

        # Key factors score (more factors = higher confidence)
        key_factors = signal_data.get("key_factors", [])
        factors_score = min(len(key_factors) / 3.0, 1.0) * 0.25

        # Indicator alignment score
        # (this is simplified - could be more sophisticated)
        indicator_score = 0.20  # Baseline score

        total_confidence = citation_score + diversity_score + factors_score + indicator_score

        return min(max(total_confidence, 0.0), 1.0)

    def _extract_citations(self, rag_context) -> list:
        """
        Extract citation strings from RAG context.

        Args:
            rag_context: RAG context with citations

        Returns:
            List of citation strings
        """
        citations = []
        for citation in rag_context.citations:
            citation_str = (
                f"{citation.source_file}, p.{citation.page_number} "
                f"(relevance: {citation.relevance_score:.2f})"
            )
            citations.append(citation_str)
        return citations

    def _extract_image_references(self, rag_context) -> list:
        """
        Extract image reference IDs from RAG context.

        Args:
            rag_context: RAG context with citations

        Returns:
            List of image IDs
        """
        image_refs = []
        for citation in rag_context.citations:
            if citation.image_id:
                image_refs.append(citation.image_id)
        return image_refs


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # This would require actual service instances
    # from ..repositories.multimodal_opensearch_repository import MultimodalOpenSearchRepository
    # from ..ingestion.multimodal_embedder import NovaMultimodalEmbeddingService
    # from .hybrid_multimodal_search import HybridMultimodalSearch
    # from .trading_retriever import MultimodalOpenSearchRetriever
    #
    # # Initialize services
    # repository = MultimodalOpenSearchRepository(host="...")
    # embedder = NovaMultimodalEmbeddingService()
    # search_service = HybridMultimodalSearch(repository, embedder)
    # retriever = MultimodalOpenSearchRetriever(search_service=search_service)
    # rag_service = TradingRAGService(retriever=retriever)
    # bedrock_service = BedrockService()
    # signal_service = SignalService(rag_service, bedrock_service)
    #
    # # Mock market state
    # market_state = {
    #     "symbol": "AAPL",
    #     "current_price": 180.50,
    #     "indicators": {
    #         "RSI": 42,
    #         "SMA_20": 175.20,
    #         "MACD": -1.2,
    #     },
    #     "support_levels": [178.00, 175.50],
    #     "resistance_levels": [185.00, 190.00],
    #     "patterns": ["support_bounce"],
    # }
    #
    # # Generate signal
    # signal = signal_service.generate_signal("AAPL", market_state)
    #
    # print(f"\n=== Signal Generated ===")
    # print(f"Symbol: {signal.symbol}")
    # print(f"Type: {signal.signal_type.value}")
    # print(f"Strategy: {signal.strategy_name}")
    # print(f"Entry: ${signal.pricing.entry_price:.2f}")
    # print(f"Target: ${signal.pricing.target_price:.2f}")
    # print(f"Stop: ${signal.pricing.stop_loss:.2f}")
    # print(f"R/R: {signal.pricing.risk_reward_ratio:.2f}")
    # print(f"Confidence: {signal.confidence_level.value} ({signal.confidence_score:.2f})")
    # print(f"Reasoning: {signal.reasoning[:200]}...")

    print("SignalService initialized")
