"""
Signal Data Models

Defines data structures for trading signals, including signal details,
pricing information, and metadata.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class SignalType(str, Enum):
    """Type of trading signal."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TradingStyle(str, Enum):
    """Trading style classification."""

    SWING = "SWING"  # 3-10 days
    POSITION = "POSITION"  # 14-180 days (weeks to months)


class ConfidenceLevel(str, Enum):
    """Signal confidence level categorization."""

    HIGH = "HIGH"  # > 0.75
    MEDIUM = "MEDIUM"  # 0.50 - 0.75
    LOW = "LOW"  # < 0.50


@dataclass
class SignalPricing:
    """Pricing information for a trading signal."""

    entry_price: float
    target_price: float
    stop_loss: float
    risk_reward_ratio: float

    def __post_init__(self):
        """Validate pricing consistency."""
        if self.entry_price <= 0:
            raise ValueError("Entry price must be positive")
        if self.target_price <= 0:
            raise ValueError("Target price must be positive")
        if self.stop_loss <= 0:
            raise ValueError("Stop loss must be positive")
        if self.risk_reward_ratio <= 0:
            raise ValueError("Risk/reward ratio must be positive")


@dataclass
class Signal:
    """
    Trading signal with comprehensive metadata.

    Contains all information needed for a trader to act on a signal:
    - What to trade (symbol)
    - When (generated_at)
    - Direction (signal_type)
    - Strategy (strategy_name)
    - Pricing (entry, target, stop-loss)
    - Reasoning (why this signal)
    - Evidence (citations from knowledge base)
    """

    # Identification
    signal_id: str
    symbol: str
    generated_at: datetime

    # Signal details
    signal_type: SignalType
    strategy_name: str
    trading_style: TradingStyle
    holding_period_days: int

    # Pricing
    pricing: SignalPricing

    # Analysis
    confidence_score: float
    confidence_level: ConfidenceLevel
    reasoning: str

    # Evidence
    citations: List[str] = field(default_factory=list)
    image_references: List[str] = field(default_factory=list)

    # Market context (optional)
    market_context: Optional[dict] = None

    # Metadata
    model_used: Optional[str] = None
    generation_time_ms: Optional[float] = None

    def __post_init__(self):
        """Validate signal consistency."""
        if not 0 <= self.confidence_score <= 1:
            raise ValueError("Confidence score must be between 0 and 1")

        if self.holding_period_days <= 0:
            raise ValueError("Holding period must be positive")

        # Validate signal type vs pricing
        if self.signal_type == SignalType.BUY:
            if self.pricing.target_price <= self.pricing.entry_price:
                raise ValueError("BUY signal: target must be above entry")
            if self.pricing.stop_loss >= self.pricing.entry_price:
                raise ValueError("BUY signal: stop loss must be below entry")
        elif self.signal_type == SignalType.SELL:
            if self.pricing.target_price >= self.pricing.entry_price:
                raise ValueError("SELL signal: target must be below entry")
            if self.pricing.stop_loss <= self.pricing.entry_price:
                raise ValueError("SELL signal: stop loss must be above entry")

    def to_dict(self) -> dict:
        """Convert signal to dictionary for storage/serialization."""
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "generated_at": self.generated_at.isoformat(),
            "signal_type": self.signal_type.value,
            "strategy_name": self.strategy_name,
            "trading_style": self.trading_style.value,
            "holding_period_days": self.holding_period_days,
            "pricing": {
                "entry_price": self.pricing.entry_price,
                "target_price": self.pricing.target_price,
                "stop_loss": self.pricing.stop_loss,
                "risk_reward_ratio": self.pricing.risk_reward_ratio,
            },
            "confidence_score": self.confidence_score,
            "confidence_level": self.confidence_level.value,
            "reasoning": self.reasoning,
            "citations": self.citations,
            "image_references": self.image_references,
            "market_context": self.market_context,
            "model_used": self.model_used,
            "generation_time_ms": self.generation_time_ms,
        }

    @property
    def potential_profit_percent(self) -> float:
        """Calculate potential profit percentage."""
        if self.signal_type == SignalType.BUY:
            return (
                (self.pricing.target_price - self.pricing.entry_price) / self.pricing.entry_price
            ) * 100
        elif self.signal_type == SignalType.SELL:
            return (
                (self.pricing.entry_price - self.pricing.target_price) / self.pricing.entry_price
            ) * 100
        return 0.0

    @property
    def potential_loss_percent(self) -> float:
        """Calculate potential loss percentage."""
        if self.signal_type == SignalType.BUY:
            return (
                (self.pricing.entry_price - self.pricing.stop_loss) / self.pricing.entry_price
            ) * 100
        elif self.signal_type == SignalType.SELL:
            return (
                (self.pricing.stop_loss - self.pricing.entry_price) / self.pricing.entry_price
            ) * 100
        return 0.0


def categorize_confidence(score: float) -> ConfidenceLevel:
    """
    Categorize confidence score into level.

    Args:
        score: Confidence score (0-1)

    Returns:
        ConfidenceLevel enum
    """
    if score >= 0.75:
        return ConfidenceLevel.HIGH
    elif score >= 0.50:
        return ConfidenceLevel.MEDIUM
    else:
        return ConfidenceLevel.LOW


# Example usage
if __name__ == "__main__":
    from uuid import uuid4

    # Create example signal
    signal = Signal(
        signal_id=str(uuid4()),
        symbol="AAPL",
        generated_at=datetime.now(),
        signal_type=SignalType.BUY,
        strategy_name="Support Bounce",
        trading_style=TradingStyle.SWING,
        holding_period_days=7,
        pricing=SignalPricing(
            entry_price=180.50,
            target_price=190.00,
            stop_loss=176.00,
            risk_reward_ratio=2.11,
        ),
        confidence_score=0.82,
        confidence_level=ConfidenceLevel.HIGH,
        reasoning="RSI oversold + triple-tested support + bullish divergence",
        citations=["How to Make Money in Stocks, p.142", "Technical Analysis, p.89"],
        image_references=["support_bounce_diagram.png"],
    )

    print("=== Signal Created ===")
    print(f"Symbol: {signal.symbol}")
    print(f"Type: {signal.signal_type.value}")
    print(f"Strategy: {signal.strategy_name}")
    print(f"Entry: ${signal.pricing.entry_price:.2f}")
    print(f"Target: ${signal.pricing.target_price:.2f}")
    print(f"Stop Loss: ${signal.pricing.stop_loss:.2f}")
    print(f"R/R Ratio: {signal.pricing.risk_reward_ratio:.2f}")
    print(f"Confidence: {signal.confidence_level.value} ({signal.confidence_score:.2f})")
    print(f"Potential Profit: {signal.potential_profit_percent:.1f}%")
    print(f"Potential Loss: {signal.potential_loss_percent:.1f}%")
