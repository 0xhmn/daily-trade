"""
Prompt Provider - Centralized Prompt Management

Loads and manages trading style-specific prompts from JSON configuration files.
Supports multiple trading styles with external configuration for easy updates.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from ..models.signal import TradingStyle

logger = logging.getLogger(__name__)


class PromptProvider:
    """
    Centralized prompt management for trading signals.

    Loads prompts from JSON files for different trading styles.
    Provides style-specific system prompts, signal prompts, query patterns,
    and validation rules.

    Features:
    - External JSON configuration
    - Multiple trading style support
    - Query pattern library
    - Validation rules per style
    - Easy prompt versioning
    """

    def __init__(self, prompts_dir: Optional[Path] = None):
        """
        Initialize PromptProvider.

        Args:
            prompts_dir: Directory containing JSON prompt files.
                        Defaults to backend/prompts/
        """
        if prompts_dir is None:
            # Default to prompts directory relative to this file
            prompts_dir = Path(__file__).parent.parent / "prompts"

        self.prompts_dir = Path(prompts_dir)
        self.prompts_cache: Dict[TradingStyle, Dict] = {}

        # Load all prompts at initialization
        self._load_all_prompts()

        logger.info(
            f"PromptProvider initialized with {len(self.prompts_cache)} styles from {self.prompts_dir}"
        )

    def _load_all_prompts(self):
        """Load all prompt configurations from JSON files."""
        style_files = {
            TradingStyle.SWING: "swing_trading.json",
            TradingStyle.POSITION: "position_trading.json",
        }

        for style, filename in style_files.items():
            filepath = self.prompts_dir / filename
            try:
                with open(filepath, "r") as f:
                    config = json.load(f)
                    self.prompts_cache[style] = config
                logger.info(f"Loaded prompts for {style.value} from {filename}")
            except FileNotFoundError:
                logger.error(f"Prompt file not found: {filepath}")
                raise ValueError(f"Missing prompt configuration: {filename}")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in {filepath}: {e}")
                raise ValueError(f"Invalid prompt configuration in {filename}: {e}")

    def get_system_prompt(self, style: TradingStyle) -> str:
        """
        Get system prompt for trading style.

        Args:
            style: Trading style (SWING or POSITION)

        Returns:
            System prompt string

        Raises:
            ValueError: If style not configured
        """
        config = self.prompts_cache.get(style)
        if not config:
            raise ValueError(f"No prompts configured for style: {style}")

        return config["system_prompt"]["role"]

    def get_signal_prompt(self, style: TradingStyle, symbol: str, context: str) -> str:
        """
        Get formatted signal generation prompt.

        Args:
            style: Trading style
            symbol: Stock symbol
            context: RAG context string

        Returns:
            Formatted prompt string ready for LLM

        Raises:
            ValueError: If style not configured
        """
        config = self.prompts_cache.get(style)
        if not config:
            raise ValueError(f"No prompts configured for style: {style}")

        template = config["signal_prompt"]["template"]
        return template.format(symbol=symbol, context=context)

    def get_schema_example(self, style: TradingStyle) -> Dict:
        """
        Get JSON schema example for trading style.

        Args:
            style: Trading style

        Returns:
            Schema example dictionary

        Raises:
            ValueError: If style not configured
        """
        config = self.prompts_cache.get(style)
        if not config:
            raise ValueError(f"No prompts configured for style: {style}")

        return config["signal_prompt"]["schema_example"]

    def get_query_pattern(self, style: TradingStyle, pattern_type: str) -> Optional[str]:
        """
        Get query pattern for RAG retrieval.

        Args:
            style: Trading style
            pattern_type: Type of pattern (e.g., "oversold_rsi", "support_bounce")

        Returns:
            Query pattern string or None if not found
        """
        config = self.prompts_cache.get(style)
        if not config:
            return None

        return config.get("query_patterns", {}).get(pattern_type)

    def get_all_query_patterns(self, style: TradingStyle) -> Dict[str, str]:
        """
        Get all query patterns for a trading style.

        Args:
            style: Trading style

        Returns:
            Dictionary of pattern_type -> query_pattern

        Raises:
            ValueError: If style not configured
        """
        config = self.prompts_cache.get(style)
        if not config:
            raise ValueError(f"No prompts configured for style: {style}")

        return config.get("query_patterns", {})

    def get_validation_rules(self, style: TradingStyle) -> Dict:
        """
        Get validation rules for trading style.

        Args:
            style: Trading style

        Returns:
            Validation rules dictionary

        Raises:
            ValueError: If style not configured
        """
        config = self.prompts_cache.get(style)
        if not config:
            raise ValueError(f"No prompts configured for style: {style}")

        return config.get("validation_rules", {})

    def get_holding_period_range(self, style: TradingStyle) -> tuple[int, int]:
        """
        Get valid holding period range for style.

        Args:
            style: Trading style

        Returns:
            Tuple of (min_days, max_days)
        """
        rules = self.get_validation_rules(style)
        holding = rules.get("holding_period", {})
        return (holding.get("min", 1), holding.get("max", 365))

    def get_min_risk_reward(self, style: TradingStyle) -> float:
        """
        Get minimum risk/reward ratio for style.

        Args:
            style: Trading style

        Returns:
            Minimum R/R ratio (e.g., 1.5 for swing, 2.0 for position)
        """
        rules = self.get_validation_rules(style)
        return rules.get("risk_reward_min", 1.5)

    def get_stop_loss_range(self, style: TradingStyle) -> tuple[float, float]:
        """
        Get stop loss percentage range for style.

        Args:
            style: Trading style

        Returns:
            Tuple of (min_pct, max_pct)
        """
        rules = self.get_validation_rules(style)
        stop_loss = rules.get("stop_loss_percentage", {})
        return (stop_loss.get("min", 2.0), stop_loss.get("max", 10.0))

    def validate_holding_period(self, style: TradingStyle, days: int) -> bool:
        """
        Validate if holding period is valid for trading style.

        Args:
            style: Trading style
            days: Holding period in days

        Returns:
            True if valid, False otherwise
        """
        min_days, max_days = self.get_holding_period_range(style)
        return min_days <= days <= max_days

    def validate_risk_reward(self, style: TradingStyle, ratio: float) -> bool:
        """
        Validate if risk/reward ratio meets minimum for style.

        Args:
            style: Trading style
            ratio: Risk/reward ratio

        Returns:
            True if valid, False otherwise
        """
        min_rr = self.get_min_risk_reward(style)
        return ratio >= min_rr


# Singleton instance for easy import
_prompt_provider_instance: Optional[PromptProvider] = None


def get_prompt_provider() -> PromptProvider:
    """
    Get singleton PromptProvider instance.

    Returns:
        PromptProvider instance
    """
    global _prompt_provider_instance
    if _prompt_provider_instance is None:
        _prompt_provider_instance = PromptProvider()
    return _prompt_provider_instance


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    provider = PromptProvider()

    # Test swing trading
    print("\n=== Swing Trading ===")
    print(f"System: {provider.get_system_prompt(TradingStyle.SWING)[:80]}...")
    print(f"Holding Period: {provider.get_holding_period_range(TradingStyle.SWING)}")
    print(f"Min R/R: {provider.get_min_risk_reward(TradingStyle.SWING)}")
    print(f"Query Patterns: {list(provider.get_all_query_patterns(TradingStyle.SWING).keys())}")

    # Test position trading
    print("\n=== Position Trading ===")
    print(f"System: {provider.get_system_prompt(TradingStyle.POSITION)[:80]}...")
    print(f"Holding Period: {provider.get_holding_period_range(TradingStyle.POSITION)}")
    print(f"Min R/R: {provider.get_min_risk_reward(TradingStyle.POSITION)}")
    print(f"Query Patterns: {list(provider.get_all_query_patterns(TradingStyle.POSITION).keys())}")

    # Test validation
    print("\n=== Validation ===")
    print(f"Swing 7 days valid: {provider.validate_holding_period(TradingStyle.SWING, 7)}")
    print(f"Swing 30 days valid: {provider.validate_holding_period(TradingStyle.SWING, 30)}")
    print(f"Position 90 days valid: {provider.validate_holding_period(TradingStyle.POSITION, 90)}")
    print(f"Swing R/R 2.0 valid: {provider.validate_risk_reward(TradingStyle.SWING, 2.0)}")
