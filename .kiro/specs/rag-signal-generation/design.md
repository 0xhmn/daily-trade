# Design Document: RAG & Signal Generation

## Overview

The RAG & Signal Generation system integrates the existing multimodal knowledge base (Phase 1) with LLM-powered signal generation to produce actionable trading signals. The system uses a hybrid architecture that combines LangChain's retriever abstraction for flexibility with custom control over prompting, parsing, and multimodal context handling.

**Key Design Principles:**

- **Hybrid Architecture**: Use LangChain's `BaseRetriever` abstraction while maintaining custom control over prompts and parsing
- **Multimodal Context**: Preserve text and image descriptions from Phase 1 throughout the RAG pipeline
- **Citation-Driven**: Every signal must cite specific source documents to prevent hallucination
- **Cost-Optimized**: Primary model is Claude 3 Sonnet with fallback to Haiku for cost management
- **Extensible**: Architecture supports future GraphRAG or alternative retrieval methods

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    TradingRAGService                        │
│  (Orchestrates query → retrieval → generation → scoring)    │
└────────────┬────────────────────────────────────┬───────────┘
             │                                    │
             ▼                                    ▼
┌────────────────────────────┐      ┌────────────────────────┐
│ MultimodalOpenSearchRetriever│      │    SignalService       │
│  (LangChain BaseRetriever)  │      │ (Signal Generation)    │
│                             │      │                        │
│ - Wraps existing hybrid     │      │ - Prompt templates     │
│   search (vector + BM25)    │      │ - Market context       │
│ - Returns LangChain Docs    │      │   injection            │
│ - Preserves multimodal      │      │ - LLM response parsing │
│   metadata                  │      │ - Signal validation    │
└────────────┬────────────────┘      └───────────┬────────────┘
             │                                    │
             ▼                                    ▼
┌────────────────────────────┐      ┌────────────────────────┐
│  HybridSearchService       │      │   BedrockService       │
│  (Existing from Phase 1)   │      │  (LLM Integration)     │
│                             │      │                        │
│ - Vector search (kNN)       │      │ - Claude 3 Sonnet      │
│ - Lexical search (BM25)     │      │ - Fallback to Haiku    │
│ - Reciprocal Rank Fusion    │      │ - Error handling       │
│ - OpenSearch client         │      │ - Response streaming   │
└─────────────────────────────┘      └────────────────────────┘
                                                  │
                                                  ▼
                                     ┌────────────────────────┐
                                     │ SignalScoringService   │
                                     │ (Confidence Scoring)   │
                                     │                        │
                                     │ - Source agreement     │
                                     │ - Indicator strength   │
                                     │ - Pattern confidence   │
                                     │ - Weighted formula     │
                                     └────────────────────────┘
```

### Data Flow

1. **Query Preprocessing** (TradingRAGService)

   - Receive stock symbol and market context
   - Format query for retrieval
   - Validate inputs

2. **Context Retrieval** (MultimodalOpenSearchRetriever)

   - Execute hybrid search via existing HybridSearchService
   - Convert OpenSearch results to LangChain Document format
   - Preserve multimodal metadata (text + image descriptions)
   - Filter by relevance threshold

3. **Signal Generation** (SignalService)

   - Build prompt with market data + retrieved context
   - Call BedrockService with Claude 3 Sonnet
   - Parse LLM response for signal components
   - Extract citations and validate against sources

4. **Confidence Scoring** (SignalScoringService)

   - Calculate source agreement score
   - Evaluate indicator strength
   - Assess pattern confidence
   - Compute weighted confidence (0-1)

5. **Signal Ranking** (TradingRAGService)
   - Compare signals across multiple stocks
   - Apply confidence threshold filtering
   - Consider diversification
   - Return ranked opportunities

## Components and Interfaces

### 1. MultimodalOpenSearchRetriever

**Purpose**: LangChain-compatible wrapper for existing OpenSearch hybrid search

**Interface**:

```python
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from typing import List

class MultimodalOpenSearchRetriever(BaseRetriever):
    """
    LangChain retriever wrapping existing HybridSearchService.
    Preserves multimodal context from Phase 1.
    """

    def __init__(
        self,
        hybrid_search_service: HybridSearchService,
        top_k: int = 10,
        relevance_threshold: float = 0.7
    ):
        """Initialize with existing search service."""
        pass

    def _get_relevant_documents(
        self,
        query: str,
        **kwargs
    ) -> List[Document]:
        """
        Retrieve relevant documents using hybrid search.

        Returns:
            List of LangChain Document objects with metadata:
            - page_content: combined text + image descriptions
            - metadata: {
                'document_id': str,
                'chunk_id': str,
                'source': str,
                'page_number': int,
                'relevance_score': float,
                'has_images': bool,
                'image_descriptions': List[str]
              }
        """
        pass
```

**Key Responsibilities**:

- Wrap existing `HybridSearchService.search()` method
- Convert OpenSearch results to LangChain `Document` format
- Preserve all multimodal metadata from Phase 1
- Apply relevance filtering
- Handle errors gracefully

### 2. TradingRAGService

**Purpose**: Orchestrate the complete RAG pipeline from query to ranked signals

**Interface**:

```python
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class MarketContext:
    """Market data for a stock."""
    symbol: str
    current_price: float
    indicators: Dict[str, float]  # RSI, MACD, SMA, etc.
    volume: float
    price_change_pct: float
    patterns: List[str]  # Detected patterns

@dataclass
class TradingSignal:
    """Generated trading signal."""
    symbol: str
    action: str  # BUY, SELL, HOLD
    entry_price: float
    target_price: float
    stop_loss: float
    holding_period_days: int
    risk_reward_ratio: float
    confidence_score: float
    reasoning: str
    citations: List[Dict[str, Any]]
    timestamp: str

class TradingRAGService:
    """
    Main RAG orchestration service for trading signals.
    """

    def __init__(
        self,
        retriever: MultimodalOpenSearchRetriever,
        signal_service: SignalService,
        scoring_service: SignalScoringService
    ):
        """Initialize with dependencies."""
        pass

    def generate_signal(
        self,
        market_context: MarketContext,
        query: str = None
    ) -> TradingSignal:
        """
        Generate a trading signal for a stock.

        Args:
            market_context: Current market data and indicators
            query: Optional custom query (defaults to strategy query)

        Returns:
            TradingSignal with all components
        """
        pass

    def generate_signals_batch(
        self,
        market_contexts: List[MarketContext]
    ) -> List[TradingSignal]:
        """Generate signals for multiple stocks."""
        pass

    def rank_signals(
        self,
        signals: List[TradingSignal],
        min_confidence: float = 0.6
    ) -> List[TradingSignal]:
        """
        Rank signals by quality and diversification.

        Args:
            signals: List of generated signals
            min_confidence: Minimum confidence threshold

        Returns:
            Filtered and ranked signals
        """
        pass

    def _preprocess_query(
        self,
        market_context: MarketContext
    ) -> str:
        """Build retrieval query from market context."""
        pass

    def _filter_by_relevance(
        self,
        documents: List[Document],
        threshold: float = 0.7
    ) -> List[Document]:
        """Filter retrieved documents by relevance score."""
        pass
```

### 3. BedrockService

**Purpose**: Manage AWS Bedrock LLM interactions with error handling and fallback

**Interface**:

```python
from typing import Optional, Dict, Any
import boto3

class BedrockService:
    """
    Service for AWS Bedrock LLM interactions.
    Supports Claude 3 Sonnet with Haiku fallback.
    """

    def __init__(
        self,
        region_name: str = "us-east-1",
        primary_model: str = "anthropic.claude-3-sonnet-20240229-v1:0",
        fallback_model: str = "anthropic.claude-3-haiku-20240307-v1:0",
        max_tokens: int = 2000,
        temperature: float = 0.1
    ):
        """Initialize Bedrock client with model configuration."""
        self.bedrock_runtime = boto3.client(
            service_name="bedrock-runtime",
            region_name=region_name
        )
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        use_fallback: bool = False
    ) -> str:
        """
        Generate text using Claude.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            use_fallback: Force use of Haiku model

        Returns:
            Generated text response

        Raises:
            BedrockAPIError: On API failures after retries
        """
        pass

    def generate_with_retry(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_retries: int = 3
    ) -> str:
        """
        Generate with automatic fallback on throttling.
        Tries Sonnet first, falls back to Haiku if throttled.
        """
        pass

    def _invoke_model(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """Low-level model invocation."""
        pass
```

### 4. SignalService

**Purpose**: Generate trading signals from market context and retrieved knowledge

**Interface**:

```python
from typing import List, Dict, Any, Tuple
from langchain_core.documents import Document

class SignalService:
    """
    Service for generating trading signals using LLM.
    """

    def __init__(
        self,
        bedrock_service: BedrockService
    ):
        """Initialize with Bedrock service."""
        pass

    def generate_signal(
        self,
        market_context: MarketContext,
        retrieved_docs: List[Document]
    ) -> Tuple[TradingSignal, List[Dict[str, Any]]]:
        """
        Generate trading signal from context and knowledge.

        Args:
            market_context: Current market data
            retrieved_docs: Retrieved trading knowledge

        Returns:
            Tuple of (TradingSignal, raw_citations)
        """
        pass

    def _build_prompt(
        self,
        market_context: MarketContext,
        retrieved_docs: List[Document]
    ) -> str:
        """
        Build LLM prompt combining market data and knowledge.

        Prompt structure:
        1. System instructions
        2. Market context (price, indicators, patterns)
        3. Retrieved trading knowledge with citations
        4. Output format specification
        """
        pass

    def _parse_response(
        self,
        llm_response: str
    ) -> Dict[str, Any]:
        """
        Parse LLM response into signal components.

        Expected format:
        {
            "action": "BUY|SELL|HOLD",
            "entry_price": float,
            "target_price": float,
            "stop_loss": float,
            "holding_period_days": int,
            "reasoning": str,
            "citations": [
                {
                    "document_id": str,
                    "chunk_id": str,
                    "quote": str
                }
            ]
        }
        """
        pass

    def _validate_signal(
        self,
        parsed_signal: Dict[str, Any],
        market_context: MarketContext
    ) -> bool:
        """
        Validate signal components for reasonableness.

        Checks:
        - Entry price near current price
        - Stop-loss below entry (for BUY)
        - Target above entry (for BUY)
        - Risk/reward ratio > 1.5
        - Holding period reasonable (1-30 days)
        """
        pass

    def _extract_citations(
        self,
        parsed_signal: Dict[str, Any],
        retrieved_docs: List[Document]
    ) -> List[Dict[str, Any]]:
        """
        Extract and validate citations against retrieved docs.

        Returns:
            List of validated citations with metadata
        """
        pass
```

### 5. SignalScoringService

**Purpose**: Calculate confidence scores for generated signals

**Interface**:

```python
from typing import List, Dict, Any
from langchain_core.documents import Document

class SignalScoringService:
    """
    Service for calculating signal confidence scores.
    """

    def __init__(
        self,
        source_weight: float = 0.4,
        indicator_weight: float = 0.3,
        pattern_weight: float = 0.3
    ):
        """Initialize with scoring weights."""
        self.source_weight = source_weight
        self.indicator_weight = indicator_weight
        self.pattern_weight = pattern_weight

    def calculate_confidence(
        self,
        signal: TradingSignal,
        retrieved_docs: List[Document],
        market_context: MarketContext
    ) -> float:
        """
        Calculate weighted confidence score (0-1).

        Components:
        1. Source agreement (40%): How many sources support this action?
        2. Indicator strength (30%): How strong are the technical signals?
        3. Pattern confidence (30%): How reliable are detected patterns?

        Returns:
            Confidence score between 0 and 1
        """
        pass

    def _calculate_source_agreement(
        self,
        signal: TradingSignal,
        retrieved_docs: List[Document]
    ) -> float:
        """
        Score based on source consensus.

        - Multiple sources cite same strategy: high score
        - Sources conflict: low score
        - Few sources: medium score
        """
        pass

    def _calculate_indicator_strength(
        self,
        signal: TradingSignal,
        market_context: MarketContext
    ) -> float:
        """
        Score based on technical indicator alignment.

        - Multiple indicators confirm: high score
        - Indicators diverge: low score
        - Extreme readings (RSI >70 or <30): boost score
        """
        pass

    def _calculate_pattern_confidence(
        self,
        signal: TradingSignal,
        market_context: MarketContext
    ) -> float:
        """
        Score based on detected pattern reliability.

        - High-probability patterns (from Bulkowski): high score
        - Weak/ambiguous patterns: low score
        - No clear pattern: medium score
        """
        pass
```

## Data Models

### Core Data Structures

```python
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime

@dataclass
class MarketContext:
    """Market data for signal generation."""
    symbol: str
    current_price: float
    indicators: Dict[str, float]  # {indicator_name: value}
    volume: float
    price_change_pct: float
    patterns: List[str]
    timestamp: datetime

@dataclass
class TradingSignal:
    """Generated trading signal."""
    signal_id: str
    symbol: str
    action: str  # BUY, SELL, HOLD
    entry_price: float
    target_price: float
    stop_loss: float
    holding_period_days: int
    risk_reward_ratio: float
    confidence_score: float
    reasoning: str
    citations: List[Citation]
    generated_at: datetime
    market_context: MarketContext

@dataclass
class Citation:
    """Source citation for a signal."""
    document_id: str
    chunk_id: str
    source_title: str
    page_number: Optional[int]
    quote: str
    relevance_score: float
    has_image: bool
    image_description: Optional[str]

@dataclass
class SignalGenerationRequest:
    """Request for signal generation."""
    symbols: List[str]
    market_contexts: List[MarketContext]
    min_confidence: float = 0.6
    max_signals: int = 5

@dataclass
class SignalGenerationResponse:
    """Response with generated signals."""
    signals: List[TradingSignal]
    total_generated: int
    filtered_count: int
    generation_time_seconds: float
```

## Correctness Properties

_A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees._

### Property 1: Retrieval preserves multimodal context

_For any_ query to the MultimodalOpenSearchRetriever, all returned LangChain Documents should contain both text content and image descriptions (when images exist) in their metadata, matching the original OpenSearch results.

**Validates: Requirements 1.2**

### Property 2: All signals include required components

_For any_ generated TradingSignal, the signal must contain non-null values for action, entry_price, target_price, stop_loss, holding_period_days, risk_reward_ratio, confidence_score, reasoning, and at least one citation.

**Validates: Requirements 2.1, 2.5**

### Property 3: Citations reference retrieved documents

_For any_ citation in a TradingSignal, the cited document_id and chunk_id must exist in the list of documents retrieved by the MultimodalOpenSearchRetriever for that query.

**Validates: Requirements 4.3**

### Property 4: Confidence scores are bounded

_For any_ TradingSignal, the confidence_score must be a float between 0.0 and 1.0 inclusive.

**Validates: Requirements 3.1**

### Property 5: Risk/reward ratio matches prices

_For any_ BUY signal, the risk_reward_ratio should equal (target_price - entry_price) / (entry_price - stop_loss), within a tolerance of 0.01.

**Validates: Requirements 2.3**

### Property 6: Signal ranking is monotonic by confidence

_For any_ list of ranked signals returned by TradingRAGService.rank_signals(), each signal's confidence_score should be greater than or equal to the next signal's confidence_score.

**Validates: Requirements 7.1**

### Property 7: Bedrock fallback on throttling

_For any_ BedrockService.generate_with_retry() call that encounters a ThrottlingException with the primary model, the service should attempt to use the fallback model before raising an error.

**Validates: Requirements 5.3**

### Property 8: Query preprocessing is deterministic

_For any_ MarketContext, calling TradingRAGService.\_preprocess_query() multiple times with the same input should produce identical query strings.

**Validates: Requirements 6.1**

## Error Handling

### Error Categories

1. **Retrieval Errors**

   - OpenSearch connection failures
   - Empty result sets
   - Malformed search responses
   - **Handling**: Retry with exponential backoff, return empty list after max retries

2. **LLM Errors**

   - Bedrock API throttling
   - Model unavailability
   - Response parsing failures
   - **Handling**: Fallback to Haiku, retry with backoff, return HOLD signal with low confidence

3. **Validation Errors**

   - Invalid market context
   - Missing required fields
   - Out-of-range values
   - **Handling**: Raise ValueError with descriptive message, log for debugging

4. **Citation Errors**
   - Citations reference non-existent documents
   - Malformed citation format
   - **Handling**: Filter invalid citations, log warning, proceed with valid citations

### Error Response Format

```python
@dataclass
class SignalGenerationError:
    """Error during signal generation."""
    error_type: str  # RETRIEVAL, LLM, VALIDATION, CITATION
    message: str
    symbol: str
    timestamp: datetime
    recoverable: bool
    fallback_signal: Optional[TradingSignal]  # HOLD signal if recoverable
```

## Testing Strategy

### Unit Testing

**Retriever Tests**:

- Test conversion from OpenSearch results to LangChain Documents
- Verify metadata preservation (multimodal content)
- Test relevance filtering
- Test error handling for empty results

**Signal Service Tests**:

- Test prompt building with various market contexts
- Test response parsing with valid/invalid LLM outputs
- Test signal validation logic
- Test citation extraction and validation

**Scoring Service Tests**:

- Test confidence calculation with known inputs
- Test individual scoring components (source, indicator, pattern)
- Test weighted formula
- Test edge cases (no sources, conflicting indicators)

**Bedrock Service Tests**:

- Mock Bedrock API responses
- Test fallback logic on throttling
- Test retry mechanism
- Test error handling

### Property-Based Testing

The system will use **Hypothesis** (Python property-based testing library) to verify correctness properties.

**Configuration**: Each property test will run a minimum of 100 iterations to ensure statistical confidence.

**Test Tagging**: Each property-based test will include a comment with the format:

```python
# Feature: rag-signal-generation, Property 1: Retrieval preserves multimodal context
```

**Property Test Examples**:

```python
from hypothesis import given, strategies as st
import hypothesis

# Property 1: Retrieval preserves multimodal context
@given(
    query=st.text(min_size=10, max_size=200),
    mock_opensearch_results=st.lists(
        st.fixed_dictionaries({
            'text': st.text(min_size=50),
            'image_descriptions': st.lists(st.text(min_size=20), min_size=0, max_size=3),
            'document_id': st.uuids(),
            'chunk_id': st.uuids()
        }),
        min_size=1,
        max_size=10
    )
)
@hypothesis.settings(max_examples=100)
def test_retrieval_preserves_multimodal_context(query, mock_opensearch_results):
    """
    Feature: rag-signal-generation, Property 1: Retrieval preserves multimodal context
    """
    # Setup: Mock HybridSearchService to return mock_opensearch_results
    # Execute: Call retriever._get_relevant_documents(query)
    # Assert: All returned Documents contain image_descriptions in metadata
    #         matching the original mock_opensearch_results
    pass

# Property 2: All signals include required components
@given(
    market_context=st.builds(MarketContext, ...),
    retrieved_docs=st.lists(st.builds(Document, ...), min_size=1)
)
@hypothesis.settings(max_examples=100)
def test_signals_include_required_components(market_context, retrieved_docs):
    """
    Feature: rag-signal-generation, Property 2: All signals include required components
    """
    # Execute: Generate signal
    # Assert: All required fields are non-null
    pass

# Property 3: Citations reference retrieved documents
@given(
    signal=st.builds(TradingSignal, ...),
    retrieved_docs=st.lists(st.builds(Document, ...), min_size=1)
)
@hypothesis.settings(max_examples=100)
def test_citations_reference_retrieved_documents(signal, retrieved_docs):
    """
    Feature: rag-signal-generation, Property 3: Citations reference retrieved documents
    """
    # Assert: All citation document_ids exist in retrieved_docs
    pass
```

### Integration Testing

**End-to-End Signal Generation**:

- Test complete flow from market context to ranked signals
- Use real OpenSearch instance with test data
- Mock Bedrock API with realistic responses
- Verify signal quality and citation accuracy

**Retriever Integration**:

- Test with real OpenSearch queries
- Verify hybrid search results
- Test multimodal content retrieval

**LLM Integration**:

- Test with real Bedrock API (in staging environment)
- Verify response parsing
- Test fallback mechanism

### Performance Testing

- Measure signal generation latency (target: <5 seconds per stock)
- Test batch generation for 20 stocks (target: <2 minutes)
- Monitor token usage and costs
- Test under API throttling conditions
