"""
Mock Market Data Generator

Generates realistic mock market data for testing signal generation
without requiring live market data APIs.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List


class MockMarketDataGenerator:
    """
    Generate realistic mock market data for testing.

    Creates market states with technical indicators, support/resistance levels,
    and patterns that simulate real trading scenarios.
    """

    # Pre-defined scenarios for different market conditions
    SCENARIOS = {
        "oversold_bounce": {
            "RSI": random.uniform(25, 35),
            "MACD": random.uniform(-2.0, -0.5),
            "trend": "uptrend",
            "patterns": ["support_bounce", "hammer"],
            "support_proximity": 0.98,  # Near support
        },
        "overbought_pullback": {
            "RSI": random.uniform(70, 80),
            "MACD": random.uniform(0.5, 2.0),
            "trend": "downtrend",
            "patterns": ["resistance_rejection", "shooting_star"],
            "support_proximity": 1.05,  # Above resistance
        },
        "breakout": {
            "RSI": random.uniform(55, 65),
            "MACD": random.uniform(0.3, 1.5),
            "trend": "uptrend",
            "patterns": ["breakout", "bull_flag"],
            "support_proximity": 1.02,  # Just above resistance
        },
        "consolidation": {
            "RSI": random.uniform(45, 55),
            "MACD": random.uniform(-0.3, 0.3),
            "trend": "sideways",
            "patterns": ["consolidation", "range_bound"],
            "support_proximity": 1.0,  # Mid-range
        },
        "strong_uptrend": {
            "RSI": random.uniform(60, 70),
            "MACD": random.uniform(1.0, 3.0),
            "trend": "strong_uptrend",
            "patterns": ["momentum", "higher_highs"],
            "support_proximity": 1.05,
        },
    }

    SYMBOLS = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "AMD", "META", "AMZN"]

    def generate_market_state(
        self, symbol: str, scenario: str | None = None, base_price: float | None = None
    ) -> Dict:
        """
        Generate mock market state for a symbol.

        Args:
            symbol: Stock symbol
            scenario: Scenario name (random if not specified)
            base_price: Base price (random if not specified)

        Returns:
            Dictionary with market state data
        """
        # Select scenario
        if scenario and scenario in self.SCENARIOS:
            scenario_data = self.SCENARIOS[scenario].copy()
        else:
            scenario_data = random.choice(list(self.SCENARIOS.values())).copy()

        # Generate base price
        if base_price is None:
            base_price = random.uniform(50, 300)

        # Calculate support/resistance levels
        support_levels = self._generate_support_levels(
            base_price, scenario_data["support_proximity"]
        )
        resistance_levels = self._generate_resistance_levels(
            base_price, scenario_data["support_proximity"]
        )

        # Current price based on proximity to levels
        current_price = base_price * scenario_data["support_proximity"]

        # Generate SMAs
        sma_20 = current_price * random.uniform(0.95, 1.00)
        sma_50 = current_price * random.uniform(0.92, 0.98)
        sma_200 = current_price * random.uniform(0.85, 0.95)

        market_state = {
            "symbol": symbol,
            "current_price": round(current_price, 2),
            "timestamp": datetime.utcnow().isoformat(),
            "indicators": {
                "RSI": round(scenario_data["RSI"], 2),
                "MACD": round(scenario_data["MACD"], 2),
                "MACD_signal": round(scenario_data["MACD"] - 0.2, 2),
                "SMA_20": round(sma_20, 2),
                "SMA_50": round(sma_50, 2),
                "SMA_200": round(sma_200, 2),
                "volume_ratio": round(random.uniform(0.8, 1.5), 2),
                "ATR": round(current_price * 0.02, 2),
            },
            "support_levels": support_levels,
            "resistance_levels": resistance_levels,
            "patterns": scenario_data["patterns"],
            "trend": scenario_data["trend"],
            "volume": random.randint(10_000_000, 100_000_000),
            "avg_volume": random.randint(8_000_000, 90_000_000),
        }

        return market_state

    def _generate_support_levels(self, base_price: float, proximity: float) -> List[float]:
        """Generate realistic support levels."""
        if proximity < 1.0:  # Price near/below support
            return [
                round(base_price * 0.97, 2),
                round(base_price * 0.94, 2),
                round(base_price * 0.90, 2),
            ]
        else:
            return [
                round(base_price * 0.95, 2),
                round(base_price * 0.92, 2),
                round(base_price * 0.88, 2),
            ]

    def _generate_resistance_levels(self, base_price: float, proximity: float) -> List[float]:
        """Generate realistic resistance levels."""
        if proximity > 1.0:  # Price near/above resistance
            return [
                round(base_price * 1.02, 2),
                round(base_price * 1.05, 2),
                round(base_price * 1.08, 2),
            ]
        else:
            return [
                round(base_price * 1.03, 2),
                round(base_price * 1.06, 2),
                round(base_price * 1.10, 2),
            ]

    def generate_watchlist_data(self, symbols: List[str] | None = None) -> Dict[str, Dict]:
        """
        Generate market data for multiple symbols.

        Args:
            symbols: List of symbols (uses default if not provided)

        Returns:
            Dictionary mapping symbols to market states
        """
        if symbols is None:
            symbols = random.sample(self.SYMBOLS, k=random.randint(3, 6))

        watchlist_data = {}
        scenarios = list(self.SCENARIOS.keys())

        for symbol in symbols:
            scenario = random.choice(scenarios)
            watchlist_data[symbol] = self.generate_market_state(symbol, scenario)

        return watchlist_data

    def generate_historical_prices(
        self, symbol: str, days: int = 30, current_price: float = 100.0
    ) -> List[Dict]:
        """
        Generate mock historical price data.

        Args:
            symbol: Stock symbol
            days: Number of days of history
            current_price: Starting price

        Returns:
            List of OHLCV dictionaries
        """
        history = []
        price = current_price
        date = datetime.utcnow() - timedelta(days=days)

        for _ in range(days):
            # Random daily movement
            change_pct = random.gauss(0, 0.02)  # 2% std dev
            price *= 1 + change_pct

            open_price = price * random.uniform(0.99, 1.01)
            close_price = price
            high_price = max(open_price, close_price) * random.uniform(1.0, 1.02)
            low_price = min(open_price, close_price) * random.uniform(0.98, 1.0)
            volume = random.randint(10_000_000, 100_000_000)

            history.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "open": round(open_price, 2),
                    "high": round(high_price, 2),
                    "low": round(low_price, 2),
                    "close": round(close_price, 2),
                    "volume": volume,
                }
            )

            date += timedelta(days=1)

        return history


# Convenience instance
mock_data = MockMarketDataGenerator()


# Example usage
if __name__ == "__main__":
    generator = MockMarketDataGenerator()

    # Generate single stock data
    print("=== Single Stock (Oversold Bounce Scenario) ===")
    aapl_data = generator.generate_market_state("AAPL", scenario="oversold_bounce")
    print(f"Symbol: {aapl_data['symbol']}")
    print(f"Price: ${aapl_data['current_price']:.2f}")
    print(f"RSI: {aapl_data['indicators']['RSI']:.2f}")
    print(f"MACD: {aapl_data['indicators']['MACD']:.2f}")
    print(f"Support: {aapl_data['support_levels']}")
    print(f"Patterns: {aapl_data['patterns']}")

    # Generate watchlist
    print("\n=== Watchlist Data ===")
    watchlist = generator.generate_watchlist_data(["AAPL", "MSFT", "NVDA"])
    for symbol, data in watchlist.items():
        print(
            f"{symbol}: ${data['current_price']:.2f}, "
            f"RSI={data['indicators']['RSI']:.0f}, "
            f"Trend={data['trend']}"
        )

    # Generate historical data
    print("\n=== Historical Prices (Last 5 days) ===")
    history = generator.generate_historical_prices("AAPL", days=5)
    for day in history[-5:]:
        print(
            f"{day['date']}: O=${day['open']:.2f} "
            f"H=${day['high']:.2f} L=${day['low']:.2f} C=${day['close']:.2f}"
        )
