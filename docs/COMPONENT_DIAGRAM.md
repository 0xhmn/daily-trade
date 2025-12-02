# Component Architecture Diagram

## End-to-End System Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE LAYER                                │
└─────────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────────────────────────────────────────────────────┐
    │                     React Frontend (Vite)                     │
    │  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
    │  │ Dashboard  │  │ Watchlist  │  │  Journal   │             │
    │  │ Component  │  │  Manager   │  │   View     │             │
    │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘             │
    │        │                │                │                    │
    │        └────────────────┴────────────────┘                    │
    │                         │                                     │
    │                    ┌────▼────┐                                │
    │                    │  Axios  │  (API Client)                 │
    │                    │  Client │                                │
    │                    └────┬────┘                                │
    └─────────────────────────┼──────────────────────────────────────┘
                              │
                              │ HTTPS
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                               API GATEWAY LAYER                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────────────────────────────────────────────────────┐
    │              AWS API Gateway (REST API)                       │
    │                                                                │
    │  Endpoints:                                                    │
    │  • GET/POST    /signals                                       │
    │  • GET/POST    /watchlist                                     │
    │  • GET/POST    /journal/trades                                │
    │  • GET         /health                                        │
    │                                                                │
    │                    VPC Link                                    │
    └──────────────────────┬────────────────────────────────────────┘
                           │
                           ▼
    ┌──────────────────────────────────────────────────────────────┐
    │           Application Load Balancer (ALB)                     │
    └──────────────────────┬────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           APPLICATION LAYER (ECS Fargate)                        │
└─────────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────────────────────────────────────────────────────┐
    │                   FastAPI Application                         │
    │  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
    │  │  Watchlist │  │  Signals   │  │  Journal   │             │
    │  │   Router   │  │   Router   │  │   Router   │             │
    │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘             │
    │        │                │                │                    │
    │        └────────────────┴────────────────┘                    │
    │                         │                                     │
    │                    Dependencies                               │
    │                         │                                     │
    └─────────────────────────┼──────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            BUSINESS LOGIC LAYER                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

╔═══════════════════════════════════════════════════════════════════════════════╗
║                      SIGNAL GENERATION PIPELINE                                ║
╚═══════════════════════════════════════════════════════════════════════════════╝

┌────────────────────────────────────────────────────────────────────────────────┐
│ 1. Request Handler                                                              │
│    ┌─────────────────────────────────────────┐                                │
│    │     POST /signals/generate              │                                │
│    │     { symbols: ["AAPL", "MSFT"] }       │                                │
│    └──────────────────┬──────────────────────┘                                │
│                       │                                                         │
│                       ▼                                                         │
│    ┌─────────────────────────────────────────┐                                │
│    │   MockMarketDataGenerator               │  (Phase 2-4: Testing)          │
│    │   • Generate RSI, MACD, SMAs            │                                │
│    │   • Create support/resistance levels    │                                │
│    │   • Simulate market scenarios           │                                │
│    └──────────────────┬──────────────────────┘                                │
└────────────────────────┼──────────────────────────────────────────────────────┘
                         │
                         │ Market State Dict
                         ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│ 2. Signal Orchestration                                                         │
│    ┌─────────────────────────────────────────┐                                │
│    │         SignalService                    │                                │
│    │  • Auto-generate RAG query              │                                │
│    │  • Orchestrate context preparation      │                                │
│    │  • Coordinate LLM generation            │                                │
│    │  • Validate pricing logic               │                                │
│    │  • Calculate confidence score           │                                │
│    └──────────────┬─────────────┬────────────┘                                │
└───────────────────┼─────────────┼──────────────────────────────────────────────┘
                    │             │
        ┌───────────┘             └───────────┐
        │                                     │
        ▼                                     ▼
┌────────────────────────────────────┐  ┌────────────────────────────────────┐
│ 3a. Context Preparation            │  │ 3b. LLM Generation                 │
│  ┌──────────────────────────────┐  │  │  ┌──────────────────────────────┐  │
│  │   TradingRAGService          │  │  │  │      BedrockService          │  │
│  │  • Prepare context           │  │  │  │  • Claude 3 Sonnet (primary) │  │
│  │  • Format market state       │  │  │  │  • Claude Haiku (fallback)   │  │
│  │  • Extract citations         │  │  │  │  • Parse JSON responses      │  │
│  │  • Filter by relevance       │  │  │  │  • Retry with backoff        │  │
│  └───────────┬──────────────────┘  │  │  └────────────┬─────────────────┘  │
│              │                      │  │               │                    │
│              ▼                      │  │               │ Prompt + Context   │
│  ┌──────────────────────────────┐  │  │               │                    │
│  │  MultimodalOpenSearchRetriever│ │  │               ▼                    │
│  │  (LangChain BaseRetriever)   │  │  │  ┌──────────────────────────────┐  │
│  │  • Invoke hybrid search      │  │  │  │    AWS Bedrock API           │  │
│  │  • Convert to Documents      │  │  │  │  ┌──────────────────────┐    │  │
│  │  • Preserve metadata         │  │  │  │  │ Claude 3 LLM         │    │  │
│  └───────────┬──────────────────┘  │  │  │  │ • Analyze context    │    │  │
│              │                      │  │  │  │ • Generate signal    │    │  │
│              ▼                      │  │  │  │ • Provide reasoning  │    │  │
│  ┌──────────────────────────────┐  │  │  │  └──────────────────────┘    │  │
│  │  HybridMultimodalSearch      │  │  │  └────────────┬─────────────────┘  │
│  │  • 5-stream parallel search  │  │  │               │                    │
│  │  • Vector (kNN)              │  │  │               │ Structured JSON    │
│  │  • Lexical (BM25)            │  │  │               ▼                    │
│  │  • Reciprocal Rank Fusion    │  │  │  ┌──────────────────────────────┐  │
│  │  • Contextual expansion      │  │  │  │    Signal Validation         │  │
│  └───────────┬──────────────────┘  │  │  │  • Parse LLM response        │  │
│              │                      │  │  │  • Validate pricing          │  │
│              ▼                      │  │  │  • Calculate R/R ratio       │  │
│  ┌──────────────────────────────┐  │  │  │  • Extract citations         │  │
│  │  MultimodalOpenSearchRepo    │  │  │  └──────────────────────────────┘  │
│  │  • Query 3 indexes           │  │  │                                    │
│  │    - text (chunks)           │  │  │                                    │
│  │    - extracted_images        │  │  │                                    │
│  │    - full_pages              │  │  │                                    │
│  │  • Dual embeddings           │  │  │                                    │
│  └───────────┬──────────────────┘  │  │                                    │
└──────────────┼──────────────────────┘  └────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             DATA STORAGE LAYER                                   │
└─────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
    │   OpenSearch        │  │     DynamoDB        │  │        S3           │
    │   Domain            │  │     Tables          │  │      Buckets        │
    │                     │  │                     │  │                     │
    │  3 Indexes:         │  │  • Users            │  │  • Documents        │
    │  • text (chunks)    │  │  • Watchlists       │  │  • Images           │
    │  • extracted_images │  │  • SignalHistory    │  │  • Embeddings       │
    │  • full_pages       │  │  • TradeJournal     │  │  • Market Data      │
    │                     │  │  • RiskParameters   │  │    Cache            │
    │  Features:          │  │                     │  │                     │
    │  • kNN vector       │  │  GSIs:              │  │  Lifecycle:         │
    │  • BM25 lexical     │  │  • userId-timestamp │  │  • Versioning       │
    │  • Hybrid search    │  │  • symbol-timestamp │  │  • Glacier archive  │
    └─────────────────────┘  └─────────────────────┘  └─────────────────────┘

╔═══════════════════════════════════════════════════════════════════════════════╗
║                      DOCUMENT INGESTION PIPELINE                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝

┌────────────────────────────────────────────────────────────────────────────────┐
│ 1. Document Upload                                                              │
│    ┌─────────────────────────────────────────┐                                │
│    │  scripts/ingest_multimodal_documents.py │                                │
│    │  • CLI ingestion script                 │                                │
│    │  • Metadata specification               │                                │
│    └──────────────────┬──────────────────────┘                                │
└────────────────────────┼──────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│ 2. Document Processing                                                          │
│    ┌─────────────────────────────────────────┐                                │
│    │   DocumentIngestionOrchestrator         │                                │
│    │  • Coordinate processing steps          │                                │
│    │  • Track progress                       │                                │
│    └──────────┬─────────────┬────────────────┘                                │
│               │             │                                                  │
│    ┌──────────▼──────────┐  │  ┌────────────▼─────────────┐                  │
│    │  DocumentProcessor  │  │  │   ImageProcessor         │                  │
│    │  • Extract text     │  │  │  • Extract images        │                  │
│    │  • Chunk text       │  │  │  • Capture position      │                  │
│    │  • Preserve bounds  │  │  │  • Render full pages     │                  │
│    └──────────┬──────────┘  │  └────────────┬─────────────┘                  │
└───────────────┼─────────────┼───────────────┼─────────────────────────────────┘
                │             │               │
                │             │               ▼
                │             │  ┌────────────────────────────┐
                │             │  │   NovaVisionService        │
                │             │  │  • Analyze charts          │
                │             │  │  • Detect indicators       │
                │             │  │  • Extract patterns        │
                │             │  └────────────┬───────────────┘
                │             │               │
                ▼             ▼               ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│ 3. Cross-Reference & Embedding                                                  │
│    ┌─────────────────────────────────────────┐                                │
│    │    CrossReferenceLinker                 │                                │
│    │  • Link images to text (spatial)        │                                │
│    │  • Create combined content              │                                │
│    └──────────────────┬──────────────────────┘                                │
│                       │                                                         │
│                       ▼                                                         │
│    ┌─────────────────────────────────────────┐                                │
│    │  NovaMultimodalEmbeddingService         │                                │
│    │  • Generate text embeddings             │                                │
│    │  • Generate multimodal embeddings       │                                │
│    │  • Batch processing                     │                                │
│    └──────────────────┬──────────────────────┘                                │
│                       │                                                         │
│                       │ Embeddings                                             │
│                       ▼                                                         │
│    ┌─────────────────────────────────────────┐                                │
│    │         AWS Bedrock                     │                                │
│    │  • Amazon Nova Embedding                │                                │
│    │  • Titan Embeddings                     │                                │
│    │  • 1024 dimensions                      │                                │
│    └──────────────────┬──────────────────────┘                                │
└────────────────────────┼──────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│ 4. Indexing                                                                     │
│    ┌─────────────────────────────────────────┐                                │
│    │  MultimodalOpenSearchRepository         │                                │
│    │  • Bulk index to 3 indexes              │                                │
│    │  • Store metadata                       │                                │
│    │  • Create cross-references              │                                │
│    └──────────────────┬──────────────────────┘                                │
│                       │                                                         │
│                       ▼                                                         │
│              OpenSearch Domain                                                  │
│         (Ready for hybrid search)                                              │
└────────────────────────────────────────────────────────────────────────────────┘

╔═══════════════════════════════════════════════════════════════════════════════╗
║                         SCHEDULED AUTOMATION                                   ║
╚═══════════════════════════════════════════════════════════════════════════════╝

    ┌─────────────────────────────────────────┐
    │        AWS EventBridge                   │
    │  • Daily Analysis: cron(0 21 * * ? *)   │
    │    (4 PM ET daily)                       │
    │  • Data Refresh: cron(30 20 * * ? *)    │
    │    (3:30 PM ET daily)                    │
    └──────────────────┬──────────────────────┘
                       │
                       │ Trigger
                       ▼
    ┌─────────────────────────────────────────┐
    │         ECS Fargate Task                 │
    │  daily_analysis.py                       │
    │  • Iterate watchlist                     │
    │  • Generate signals                      │
    │  • Persist to DynamoDB                   │
    │  • Send notifications (SNS)              │
    └─────────────────────────────────────────┘

╔═══════════════════════════════════════════════════════════════════════════════╗
║                          DATA FLOW SUMMARY                                     ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Signal Generation Flow:
1. User requests signal → API Gateway
2. SignalService receives request with symbol
3. MockMarketData generates market state (RSI, MACD, etc.)
4. TradingRAGService prepares context
   └→ Retriever queries OpenSearch (5-stream hybrid)
   └→ Returns Documents with citations & images
5. SignalService formats prompt with context
6. BedrockService calls Claude 3 Sonnet
7. Claude analyzes and generates structured signal
8. SignalService validates & scores confidence
9. Signal returned to user via API Gateway
10. Frontend displays in SignalCard component

Document Ingestion Flow:
1. Admin uploads PDF via ingestion script
2. DocumentProcessor extracts text & chunks
3. ImageProcessor extracts images & positions
4. NovaVisionService analyzes chart images
5. CrossReferenceLinker connects images to text
6. NovaEmbedder generates dual embeddings
7. Repository bulk indexes to 3 OpenSearch indexes
8. Knowledge base ready for retrieval

Key Characteristics:
• Hybrid Architecture: Custom control + LangChain abstractions
• Non-Agentic: Fixed pipeline (agents in Phase 6+)
• Multimodal: Text + images with cross-references
• 5-Stream Search: kNN + BM25 + RRF + expansion
• Dual Embeddings: Text & multimodal for comprehensive matching
• Mock-First: Test with realistic data before live integration
```

## Component Dependencies

```
┌─────────────────────────────────────────────────────────────┐
│                     Dependency Graph                         │
└─────────────────────────────────────────────────────────────┘

SignalService
    ├── TradingRAGService
    │   └── MultimodalOpenSearchRetriever
    │       └── HybridMultimodalSearch
    │           ├── MultimodalOpenSearchRepository
    │           │   └── OpenSearch (AWS)
    │           └── NovaMultimodalEmbeddingService
    │               └── Bedrock (AWS)
    └── BedrockService
        └── Bedrock (AWS)

DocumentIngestionOrchestrator
    ├── DocumentProcessor
    ├── ImageProcessor
    │   └── S3 (AWS)
    ├── NovaVisionService
    │   └── Bedrock (AWS)
    ├── CrossReferenceLinker
    ├── NovaMultimodalEmbeddingService
    │   └── Bedrock (AWS)
    └── MultimodalOpenSearchRepository
        └── OpenSearch (AWS)
```

## Technology Stack Summary

| Layer             | Technology                | Purpose                     |
| ----------------- | ------------------------- | --------------------------- |
| **Frontend**      | React + Vite + TypeScript | User interface              |
| **API**           | AWS API Gateway + ALB     | REST API endpoints          |
| **Backend**       | FastAPI + Python 3.11     | Business logic              |
| **Retrieval**     | LangChain Core            | Abstraction layer           |
| **Search**        | OpenSearch (3 indexes)    | Hybrid vector + lexical     |
| **LLM**           | Claude 3 Sonnet/Haiku     | Signal generation           |
| **Vision**        | Amazon Nova Vision        | Image analysis              |
| **Embeddings**    | Nova/Titan Embeddings     | Vector generation           |
| **Storage**       | DynamoDB + S3             | Structured + object storage |
| **Orchestration** | ECS Fargate               | Container management        |
| **Scheduling**    | EventBridge               | Automated jobs              |
| **Monitoring**    | CloudWatch                | Logs, metrics, alarms       |
| **IaC**           | AWS CDK (TypeScript)      | Infrastructure deployment   |

## Ports & Interfaces

```
External Interfaces:
├── Frontend → API Gateway: HTTPS (443)
├── API Gateway → ALB: Private VPC
├── Backend → OpenSearch: HTTPS (9200)
├── Backend → DynamoDB: HTTPS (443)
├── Backend → Bedrock: HTTPS (443)
└── Backend → S3: HTTPS (443)

Internal Interfaces:
├── SignalService → TradingRAGService: Python API
├── TradingRAGService → Retriever: LangChain BaseRetriever
├── Retriever → HybridSearch: Python API
├── HybridSearch → OpenSearchRepo: Python API
└── SignalService → BedrockService: Python API
```
