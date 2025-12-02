# Requirements Document

## Introduction

This document specifies the requirements for the RAG & Signal Generation system for an AI-powered trading assistant. The system will integrate the existing multimodal RAG knowledge base (Phase 1) with LLM-powered signal generation to produce actionable trading signals with citations, confidence scores, and risk/reward analysis. This system uses a hybrid architecture combining LangChain's retriever abstraction with custom control over prompting, parsing, and multimodal context.

## Glossary

- **RAG System**: Retrieval-Augmented Generation system that retrieves relevant trading knowledge and generates signals using LLMs
- **Trading Signal**: A structured recommendation containing entry price, target price, stop-loss, holding period, risk/reward ratio, and confidence score
- **TradingRAGService**: The core service that orchestrates query preprocessing, context retrieval, and signal generation
- **Retriever**: LangChain abstraction wrapping the existing OpenSearch hybrid search service
- **Multimodal Context**: Trading knowledge from text and images (charts, diagrams) in ingested books
- **Confidence Score**: A weighted numerical value (0-1) indicating signal reliability based on source agreement, indicator strength, and pattern confidence
- **Citation**: A reference to source documents and chunks that support the generated signal
- **BedrockService**: The service managing AWS Bedrock LLM interactions (Claude 3 Sonnet/Haiku)
- **SignalService**: The service responsible for generating trading signals from market context and RAG-retrieved knowledge
- **SignalScoringService**: The service that calculates confidence scores for generated signals

## Requirements

### Requirement 1

**User Story:** As a trader, I want the system to retrieve relevant trading knowledge from the knowledge base, so that generated signals are grounded in proven strategies and patterns.

#### Acceptance Criteria

1. WHEN the TradingRAGService receives a query THEN the RAG System SHALL use the MultimodalOpenSearchRetriever to retrieve relevant document chunks
2. WHEN retrieving context THEN the RAG System SHALL preserve multimodal content including text and image descriptions in Document metadata
3. WHEN documents are retrieved THEN the RAG System SHALL use the existing hybrid search combining vector similarity and lexical matching
4. WHEN context is retrieved THEN the RAG System SHALL filter results by relevance threshold before passing to the LLM
5. WHEN the retriever returns results THEN the RAG System SHALL extract source citations from Document metadata

### Requirement 2

**User Story:** As a trader, I want trading signals to include entry price, target price, stop-loss, and holding period, so that I can execute trades with clear parameters.

#### Acceptance Criteria

1. WHEN the SignalService generates a signal THEN the RAG System SHALL include entry price, target price, stop-loss price, and estimated holding period
2. WHEN calculating prices THEN the SignalService SHALL use current market data and retrieved trading strategies
3. WHEN determining stop-loss THEN the SignalService SHALL calculate risk/reward ratio
4. WHEN estimating holding period THEN the SignalService SHALL base the estimate on strategy type and market conditions
5. WHEN signal generation completes THEN the SignalService SHALL validate that all required fields are present

### Requirement 3

**User Story:** As a trader, I want signals to include confidence scores, so that I can prioritize high-confidence opportunities.

#### Acceptance Criteria

1. WHEN a signal is generated THEN the SignalScoringService SHALL calculate a weighted confidence score between 0 and 1
2. WHEN calculating confidence THEN the SignalScoringService SHALL incorporate source agreement scoring
3. WHEN calculating confidence THEN the SignalScoringService SHALL incorporate indicator strength scoring
4. WHEN calculating confidence THEN the SignalScoringService SHALL incorporate pattern confidence scoring
5. WHEN the confidence score is computed THEN the SignalScoringService SHALL include the score in the signal output

### Requirement 4

**User Story:** As a trader, I want signals to cite their sources, so that I can verify the reasoning and learn from the underlying strategies.

#### Acceptance Criteria

1. WHEN a signal is generated THEN the SignalService SHALL extract citations from the LLM response
2. WHEN citations are extracted THEN the SignalService SHALL include document IDs and chunk IDs
3. WHEN formatting citations THEN the SignalService SHALL validate that cited sources exist in the retrieved context
4. WHEN multiple sources support a signal THEN the SignalService SHALL rank citations by relevance
5. WHEN storing signals THEN the RAG System SHALL persist citations in the SignalHistory table

### Requirement 5

**User Story:** As a trader, I want the system to use Claude 3 Sonnet for signal generation with fallback to Haiku, so that I get high-quality signals while managing costs.

#### Acceptance Criteria

1. WHEN the BedrockService is initialized THEN the RAG System SHALL configure access to Claude 3 Sonnet via AWS Bedrock
2. WHEN generating signals THEN the BedrockService SHALL use Claude 3 Sonnet as the primary model
3. WHEN API limits are reached THEN the BedrockService SHALL fall back to Claude 3 Haiku
4. WHEN calling the LLM THEN the BedrockService SHALL implement error handling for API failures
5. WHEN responses are received THEN the BedrockService SHALL parse the LLM output according to the expected format

### Requirement 6

**User Story:** As a trader, I want signals to incorporate both market data and knowledge base context, so that recommendations are data-driven and strategy-informed.

#### Acceptance Criteria

1. WHEN generating a signal THEN the SignalService SHALL inject current market context into the prompt
2. WHEN building the prompt THEN the SignalService SHALL include technical indicators, price data, and volume information
3. WHEN building the prompt THEN the SignalService SHALL include retrieved trading knowledge from the RAG system
4. WHEN combining contexts THEN the SignalService SHALL use a prompt template that structures market data and knowledge appropriately
5. WHEN the LLM generates a response THEN the SignalService SHALL parse the response to extract signal components

### Requirement 7

**User Story:** As a trader analyzing multiple stocks, I want signals to be ranked by quality, so that I can focus on the best opportunities.

#### Acceptance Criteria

1. WHEN multiple signals are generated THEN the RAG System SHALL rank signals using a signal ranking algorithm
2. WHEN ranking signals THEN the RAG System SHALL compare signals across multiple stocks
3. WHEN ranking signals THEN the RAG System SHALL consider confidence scores and risk/reward ratios
4. WHEN ranking signals THEN the RAG System SHALL consider portfolio diversification
5. WHEN filtering signals THEN the RAG System SHALL exclude signals below a minimum confidence threshold

### Requirement 8

**User Story:** As a developer, I want the RAG system to use LangChain's retriever abstraction, so that the system can be extended with GraphRAG or other retrieval methods in the future.

#### Acceptance Criteria

1. WHEN implementing the retriever THEN the RAG System SHALL create a BaseRetriever wrapper for the existing OpenSearch service
2. WHEN the MultimodalOpenSearchRetriever is called THEN the RAG System SHALL return results in LangChain Document format
3. WHEN preserving context THEN the MultimodalOpenSearchRetriever SHALL include all metadata from OpenSearch results
4. WHEN the retriever interface is used THEN the TradingRAGService SHALL remain decoupled from the specific retrieval implementation
5. WHEN testing the retriever THEN the RAG System SHALL verify compatibility with the existing hybrid search functionality
