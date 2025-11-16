# AI-Powered Trading Assistant - Low Level Design Document

## Document Overview

**Purpose**: Technical specification and implementation guide for the AI-powered trading assistant
**Related Documents**: HLD.md (High Level Design)
**Last Updated**: November 16, 2025
**Version**: 1.0

---

## 1. Technology Stack

### 1.1 Backend Stack

**Core Framework**

- Python 3.11+
- FastAPI 0.104+ (REST API framework)
- Uvicorn (ASGI server)
- Pydantic 2.0+ (data validation)

**Data Processing & Analysis**

- pandas 2.1+ (data manipulation)
- numpy 1.26+ (numerical computing)
- pandas-ta or TA-Lib (technical indicators)
- yfinance (market data - free tier for PoC)

**AI & Machine Learning**

- LangChain 0.1+ (RAG orchestration)
- boto3 1.34+ (AWS SDK)
- opensearch-py (OpenSearch client)
- sentence-transformers (for local embedding testing)

**Infrastructure & DevOps**

- Docker (containerization)
- pytest (testing)
- python-dotenv (configuration)
- loguru (structured logging)

### 1.2 Frontend Stack

**Core Framework**

- React 18+
- TypeScript 5.0+
- Vite 5.0+ (build tool)

**State & Data Management**

- TanStack Query (React Query v5)
- Zustand or React Context (state management)
- Axios (HTTP client)

**UI & Visualization**

- Tailwind CSS 3.3+ (styling)
- shadcn/ui (component library)
- Recharts 2.5+ (chart visualization)
- Lucide React (icons)
- React Router 6+ (routing)

### 1.3 Infrastructure (AWS)

**Compute**

- ECS Fargate (container orchestration)
- ECR (Docker image registry)
- Lambda (future: serverless functions)

**Storage & Database**

- DynamoDB (NoSQL database)
- S3 (object storage)
- OpenSearch Service (hybrid vector + lexical search)

**AI Services**

- Bedrock (Claude 3 Sonnet/Haiku for LLM)
- Bedrock (Titan Embeddings for vectors)

**Integration & Automation**

- API Gateway (REST API endpoint)
- EventBridge (scheduled tasks)
- SNS (notifications)
- CloudWatch (logging, metrics, alarms)

**Infrastructure as Code**

- AWS CDK with TypeScript
- CloudFormation (CDK synthesized)

### 1.4 Development Tools

- Git (version control)
- Docker Compose (local development)
- VS Code (IDE)
- Postman/Thunder Client (API testing)
- AWS CLI (AWS operations)

---

## 2. Project Structure

```
daily-trade/
├── infrastructure/                           # AWS CDK Infrastructure
│   ├── bin/
│   │   └── daily-trade-stack.ts             # CDK app entry point
│   ├── lib/
│   │   ├── compute-stack.ts                 # ECS Fargate, Task Definitions
│   │   ├── data-stack.ts                    # DynamoDB, S3, OpenSearch
│   │   ├── ai-stack.ts                      # Bedrock configuration
│   │   ├── api-stack.ts                     # API Gateway, VPC Links
│   │   ├── pipeline-stack.ts                # EventBridge schedules
│   │   └── monitoring-stack.ts              # CloudWatch dashboards, alarms
│   ├── cdk.json
│   ├── package.json
│   ├── tsconfig.json
│   └── README.md
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                          # FastAPI application
│   │   ├── config.py                        # Configuration management
│   │   └── dependencies.py                  # Dependency injection
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── market_data_service.py           # yfinance wrapper
│   │   ├── rag_service.py                   # RAG orchestration
│   │   ├── analysis_service.py              # Technical analysis
│   │   ├── signal_service.py                # Signal generation
│   │   ├── opensearch_service.py            # Hybrid search implementation
│   │   └── bedrock_service.py               # AWS Bedrock client
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── domain.py                        # Domain models (Trade, Signal, Stock)
│   │   └── schemas.py                       # API schemas (requests/responses)
│   │
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── dynamodb_repo.py                 # DynamoDB operations
│   │   └── s3_repo.py                       # S3 operations
│   │
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── document_processor.py            # PDF/text extraction, chunking
│   │   ├── embedder.py                      # Generate embeddings
│   │   └── indexer.py                       # Index to OpenSearch
│   │
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── indicators.py                    # Technical indicators calculation
│   │   ├── patterns.py                      # Chart pattern detection
│   │   └── market_state.py                  # Market context builder
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── watchlist.py                     # Watchlist CRUD endpoints
│   │   ├── signals.py                       # Signal generation endpoints
│   │   ├── journal.py                       # Trade journal endpoints
│   │   ├── analysis.py                      # On-demand analysis endpoints
│   │   └── health.py                        # Health check endpoints
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logging.py                       # Logging configuration
│   │   ├── exceptions.py                    # Custom exceptions
│   │   └── helpers.py                       # Utility functions
│   │
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── .env.example
│   └── README.md
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Header.tsx
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   └── Layout.tsx
│   │   │   ├── dashboard/
│   │   │   │   ├── Dashboard.tsx
│   │   │   │   ├── SignalCard.tsx
│   │   │   │   ├── PerformanceMetrics.tsx
│   │   │   │   └── GoalProgress.tsx
│   │   │   ├── watchlist/
│   │   │   │   ├── WatchlistManager.tsx
│   │   │   │   ├── StockSearch.tsx
│   │   │   │   └── WatchlistTable.tsx
│   │   │   ├── journal/
│   │   │   │   ├── TradeJournal.tsx
│   │   │   │   ├── TradeForm.tsx
│   │   │   │   └── TradeList.tsx
│   │   │   ├── analysis/
│   │   │   │   ├── ChartView.tsx
│   │   │   │   ├── TechnicalIndicators.tsx
│   │   │   │   └── SourceCitations.tsx
│   │   │   └── common/
│   │   │       ├── Button.tsx
│   │   │       ├── Card.tsx
│   │   │       └── Loading.tsx
│   │   │
│   │   ├── hooks/
│   │   │   ├── useApi.ts                    # API integration hook
│   │   │   ├── useWatchlist.ts
│   │   │   ├── useSignals.ts
│   │   │   └── useJournal.ts
│   │   │
│   │   ├── services/
│   │   │   └── api.ts                       # API client with Axios
│   │   │
│   │   ├── types/
│   │   │   ├── index.ts                     # TypeScript type definitions
│   │   │   ├── signal.ts
│   │   │   └── trade.ts
│   │   │
│   │   ├── utils/
│   │   │   ├── formatters.ts                # Data formatting utilities
│   │   │   └── validators.ts                # Input validation
│   │   │
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   │
│   ├── public/
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── README.md
│
├── scripts/
│   ├── ingest_documents.py                  # Document ingestion script
│   ├── test_rag.py                          # Test RAG retrieval
│   ├── setup_aws.sh                         # AWS setup automation
│   ├── seed_data.py                         # Seed test data
│   └── deploy.sh                            # Deployment script
│
├── data/
│   ├── knowledge_base/                      # Trading books (PDFs)
│   │   ├── technical_analysis/
│   │   ├── swing_trading/
│   │   └── risk_management/
│   ├── sample_data/                         # Test data
│   └── .gitkeep
│
├── tests/
│   ├── unit/
│   │   ├── test_indicators.py
│   │   ├── test_rag_service.py
│   │   └── test_signal_service.py
│   ├── integration/
│   │   ├── test_opensearch.py
│   │   └── test_api_endpoints.py
│   └── e2e/
│       └── test_signal_generation.py
│
├── docs/
│   ├── HLD.md                               # High Level Design
│   ├── LLD.md                               # Low Level Design (this doc)
│   ├── ARCHITECTURE.md                      # Architecture diagrams
│   ├── API.md                               # API documentation
│   └── DEPLOYMENT.md                        # Deployment guide
│
├── .github/
│   └── workflows/
│       ├── ci.yml                           # CI pipeline
│       └── deploy.yml                       # CD pipeline
│
├── docker-compose.yml                       # Local development
├── .gitignore
├── .env.example
├── README.md
└── LICENSE
```

---

## 3. AWS Infrastructure Architecture

### 3.1 DynamoDB Tables

**Table: Users**

```
Partition Key: userId (String)
Attributes:
  - email (String)
  - createdAt (Number - Unix timestamp)
  - lastLogin (Number)
```

**Table: Watchlists**

```
Partition Key: userId (String)
Sort Key: symbol (String)
Attributes:
  - addedAt (Number)
  - sector (String)
  - liquidity (Number)
GSI: userId-addedAt-index
```

**Table: RiskParameters**

```
Partition Key: userId (String)
Attributes:
  - maxPositionSizePct (Number)
  - maxDrawdownPct (Number)
  - preferredHoldingPeriodDays (Number)
  - profitTarget (Number)
  - profitTargetTimeframe (String)
  - sectorRestrictions (List<String>)
  - updatedAt (Number)
```

**Table: TradeJournal**

```
Partition Key: userId (String)
Sort Key: tradeId (String - UUID)
Attributes:
  - symbol (String)
  - action (String - BUY/SELL)
  - entryDate (Number)
  - entryPrice (Number)
  - quantity (Number)
  - exitDate (Number)
  - exitPrice (Number)
  - profitLoss (Number)
  - signalId (String)
  - notes (String)
GSI: userId-entryDate-index
GSI: symbol-entryDate-index
```

**Table: SignalHistory**

```
Partition Key: signalId (String - UUID)
Sort Key: timestamp (Number)
Attributes:
  - userId (String)
  - symbol (String)
  - action (String - BUY/SELL/HOLD)
  - confidenceScore (Number)
  - entryPrice (Number)
  - targetPrice (Number)
  - stopLoss (Number)
  - reasoning (String)
  - citations (List<Map>)
  - marketState (Map)
  - followed (Boolean)
  - outcome (String)
GSI: userId-timestamp-index
GSI: symbol-timestamp-index
```

### 3.2 OpenSearch Domain Configuration

**Domain Name**: `daily-trade-knowledge`

**Index: trading-knowledge**

```json
{
  "mappings": {
    "properties": {
      "text": {
        "type": "text",
        "analyzer": "standard"
      },
      "embedding": {
        "type": "knn_vector",
        "dimension": 1024,
        "method": {
          "name": "hnsw",
          "space_type": "cosinesimilarity",
          "engine": "nmslib"
        }
      },
      "metadata": {
        "properties": {
          "source": { "type": "keyword" },
          "book_title": { "type": "text" },
          "chapter": { "type": "text" },
          "page": { "type": "integer" },
          "strategy_type": { "type": "keyword" },
          "timeframe": { "type": "keyword" },
          "market_condition": { "type": "keyword" },
          "asset_class": { "type": "keyword" },
          "concepts": { "type": "keyword" }
        }
      },
      "chunk_id": { "type": "keyword" },
      "created_at": { "type": "date" }
    }
  }
}
```

**Instance Configuration**

- Instance Type: `t3.small.search` (PoC), scale to `m5.large.search` for production
- Nodes: 1 (PoC), 2+ with replicas for HA
- Storage: 100 GB EBS (PoC)
- Network: VPC deployment with security group

### 3.3 S3 Buckets

**Bucket: daily-trade-documents**

- Purpose: Store original PDF/text documents
- Versioning: Enabled
- Lifecycle: Archive to Glacier after 90 days
- Structure: `/books/{book_name}.pdf`, `/articles/{article_name}.pdf`

**Bucket: daily-trade-embeddings**

- Purpose: Backup embeddings and processed chunks
- Format: JSON or Parquet
- Structure: `/embeddings/{date}/{source_id}.json`

**Bucket: daily-trade-market-data**

- Purpose: Cache historical price data
- Format: Parquet or CSV
- Structure: `/prices/{symbol}/{date}.parquet`

**Bucket: daily-trade-logs**

- Purpose: Application logs backup
- Lifecycle: Delete after 30 days

### 3.4 ECS Fargate Architecture

**Cluster**: `daily-trade-cluster`

**Service 1: Backend API**

```yaml
Task Definition:
  - CPU: 512 (0.5 vCPU)
  - Memory: 1024 MB
  - Container:
      - Image: {account}.dkr.ecr.{region}.amazonaws.com/daily-trade-backend:latest
      - Port: 8000
      - Environment:
          - AWS_REGION
          - DYNAMODB_TABLE_PREFIX
          - OPENSEARCH_ENDPOINT
          - S3_BUCKET_DOCUMENTS
  - Task Role: DailyTradeBackendTaskRole
  - Execution Role: ECSTaskExecutionRole

Service:
  - Desired Count: 2
  - Launch Type: FARGATE
  - Network: Private subnets with NAT Gateway
  - Load Balancer: Application Load Balancer
  - Auto Scaling: Target tracking (CPU 70%)
```

**Service 2: Scheduled Analysis Job**

```yaml
Task Definition:
  - CPU: 1024 (1 vCPU)
  - Memory: 2048 MB
  - Container:
      - Image: {account}.dkr.ecr.{region}.amazonaws.com/daily-trade-analyzer:latest
      - Command: ["python", "-m", "app.jobs.daily_analysis"]

Trigger:
  - EventBridge Rule: cron(0 21 * * ? *)  # 4 PM ET = 9 PM UTC
  - Target: ECS Task (run once)
```

### 3.5 API Gateway Configuration

**REST API**: `daily-trade-api`

**Endpoints**

```
/watchlist
  GET    /                   # List watchlist
  POST   /                   # Add stock
  DELETE /{symbol}           # Remove stock

/signals
  GET    /                   # Get latest signals
  GET    /{signalId}         # Get signal details
  POST   /generate           # On-demand signal generation

/journal
  GET    /trades             # List trades
  POST   /trades             # Record trade
  GET    /trades/{tradeId}   # Get trade details
  PUT    /trades/{tradeId}   # Update trade
  GET    /performance        # Get performance metrics

/analysis
  POST   /stock/{symbol}     # Analyze specific stock
  GET    /indicators/{symbol} # Get technical indicators

/user
  GET    /risk-parameters    # Get risk config
  PUT    /risk-parameters    # Update risk config
  GET    /profile            # Get user profile

/health
  GET    /                   # Health check
```

**Integration**: VPC Link to ALB fronting ECS services

**Authorization**: IAM (future: Cognito for multi-user)

### 3.6 EventBridge Rules

**Rule 1: Daily Analysis**

```yaml
Name: daily-trade-analysis
Schedule: cron(0 21 * * ? *) # 9 PM UTC = 4 PM ET
Target: ECS Task (daily-trade-analyzer)
Input: { "type": "daily_analysis" }
```

**Rule 2: Data Refresh**

```yaml
Name: market-data-refresh
Schedule: cron(30 20 * * ? *) # 3:30 PM ET
Target: ECS Task (data-refresh-job)
```

---

## 4. Core Service Specifications

### 4.1 RAG Service

**Hybrid Search Implementation**

```python
class HybridSearchService:
    def search(self, query: str, k: int = 10) -> List[Document]:
        # 1. Generate embedding for semantic search
        embedding = self.bedrock.create_embedding(query)

        # 2. Vector search (kNN)
        vector_results = self.opensearch.knn_search(
            index="trading-knowledge",
            vector=embedding,
            k=k,
            filter={"strategy_type": "swing_trading"}
        )

        # 3. Lexical search (BM25)
        lexical_results = self.opensearch.bm25_search(
            index="trading-knowledge",
            query=query,
            k=k,
            fields=["text", "metadata.concepts"]
        )

        # 4. Reciprocal Rank Fusion
        combined = self._rrf_merge(vector_results, lexical_results)

        return combined[:k]

    def _rrf_merge(self, results_a, results_b, k=60):
        """Reciprocal Rank Fusion algorithm"""
        scores = {}
        for rank, doc in enumerate(results_a, 1):
            scores[doc.id] = scores.get(doc.id, 0) + 1 / (k + rank)
        for rank, doc in enumerate(results_b, 1):
            scores[doc.id] = scores.get(doc.id, 0) + 1 / (k + rank)

        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [self._get_doc_by_id(doc_id) for doc_id, _ in sorted_docs]
```

**RAG Prompt Template**

```python
SIGNAL_GENERATION_PROMPT = """
You are an expert swing trading analyst. Based on the provided trading knowledge
and current market data, generate a trading signal.

## Trading Knowledge Context:
{retrieved_passages}

## Current Market State:
Stock Symbol: {symbol}
Current Price: ${current_price}
Price Change (1D): {price_change_1d}%
Volume (vs avg): {volume_ratio}x

Technical Indicators:
- RSI(14): {rsi}
- MACD: {macd_value} (Signal: {macd_signal})
- SMA(20): ${sma_20}
- SMA(50): ${sma_50}
- Bollinger Bands: ${bb_lower} - ${bb_upper}
- Price vs SMA(200): {sma200_position}%

Recent News Sentiment: {news_sentiment}

## Task:
Generate a swing trading signal (BUY/SELL/HOLD) following this structure:

1. ACTION: [BUY/SELL/HOLD]
2. CONFIDENCE: [0-100]%
3. ENTRY_PRICE: $X.XX
4. TARGET_PRICE: $X.XX
5. STOP_LOSS: $X.XX
6. HOLDING_PERIOD: X days
7. RISK_REWARD_RATIO: X:1
8. REASONING:
   - Key pattern/setup identified
   - Indicator confluence
   - Historical precedent from sources
9. CITATIONS:
   - [Book/Article, Chapter/Section, Page]
   - Quote specific passage that supports recommendation

Ensure all recommendations are grounded in the provided trading knowledge.
If insufficient context, recommend HOLD and explain why.
"""
```

### 4.2 Technical Indicators Service

**Core Indicators Implementation**

```python
class TechnicalIndicatorsService:
    def calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """
        Calculate all required technical indicators
        Input: DataFrame with OHLCV columns
        Output: Dictionary of indicator values
        """
        return {
            'sma_20': self._sma(df, 20),
            'sma_50': self._sma(df, 50),
            'sma_200': self._sma(df, 200),
            'rsi_14': self._rsi(df, 14),
            'macd': self._macd(df),
            'bollinger_bands': self._bollinger_bands(df),
            'volume_ma': self._volume_ma(df, 20),
            'atr': self._atr(df, 14),
            'stochastic': self._stochastic(df)
        }

    def detect_patterns(self, df: pd.DataFrame) -> List[str]:
        """Detect common chart patterns"""
        patterns = []

        if self._is_bullish_engulfing(df):
            patterns.append("Bullish Engulfing")
        if self._is_hammer(df):
            patterns.append("Hammer")
        if self._is_double_bottom(df):
            patterns.append("Double Bottom")
        # ... more patterns

        return patterns

    def calculate_support_resistance(self, df: pd.DataFrame) -> Dict:
        """Calculate key support/resistance levels"""
        pivots = self._pivot_points(df)
        return {
            'resistance_levels': [pivots['r1'], pivots['r2']],
            'support_levels': [pivots['s1'], pivots['s2']],
            'pivot': pivots['pivot']
        }
```

### 4.3 Signal Scoring Algorithm

```python
class SignalScoringService:
    def calculate_confidence(
        self,
        llm_confidence: float,
        source_agreement: float,
        indicator_strength: float,
        pattern_confidence: float
    ) -> float:
        """
        Weighted confidence score calculation

        Weights:
        - LLM confidence: 30%
        - Source agreement (how many sources align): 35%
        - Indicator strength (confluence): 25%
        - Pattern confidence: 10%
        """
        weights = {
            'llm': 0.30,
            'sources': 0.35,
            'indicators': 0.25,
            'patterns': 0.10
        }

        confidence = (
            llm_confidence * weights['llm'] +
            source_agreement * weights['sources'] +
            indicator_strength * weights['indicators'] +
            pattern_confidence * weights['patterns']
        )

        return min(100, max(0, confidence))

    def calculate_source_agreement(self, citations: List[Dict]) -> float:
        """
        Calculate agreement score from multiple sources
        Higher score when multiple independent sources recommend same action
        """
        unique_sources = len(set(c['book_title'] for c in citations))
        total_sources = len(citations)

        # Bonus for diverse sources agreeing
        diversity_bonus = unique_sources / max(total_sources, 1)

        return min(100, (total_sources * 15) + (diversity_bonus * 20))
```

### 4.4 Document Ingestion Pipeline

```python
class DocumentIngestionService:
    async def ingest_document(self, file_path: str, metadata: Dict):
        """
        Complete document ingestion pipeline

        Steps:
        1. Extract text from PDF
        2. Chunk text intelligently
        3. Generate embeddings
        4. Index to OpenSearch with metadata
        """
        # 1. Extract text
        text = self._extract_text(file_path)

        # 2. Chunk with overlap
        chunks = self._chunk_text(
            text,
            chunk_size=1000,
            overlap=200,
            preserve_sentences=True
        )

        # 3. Generate embeddings (batch)
        embeddings = await self._batch_embed(chunks)

        # 4. Index to OpenSearch
        documents = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            doc = {
                'text': chunk,
                'embedding': embedding,
                'metadata': {
                    **metadata,
                    'chunk_index': i,
                    'chunk_id': f"{metadata['source_id']}_chunk_{i}"
                },
                'created_at': datetime.utcnow().isoformat()
            }
            documents.append(doc)

        await self.opensearch.bulk_index(
            index='trading-knowledge',
            documents=documents
        )

    def _chunk_text(self, text: str, chunk_size: int, overlap: int,
                    preserve_sentences: bool = True) -> List[str]:
        """
        Smart chunking that preserves sentence boundaries
        """
        if preserve_sentences:
            sentences = sent_tokenize(text)
            chunks = []
            current_chunk = []
            current_size = 0

            for sentence in sentences:
                sentence_size = len(sentence.split())
                if current_size + sentence_size > chunk_size and current_chunk:
                    chunks.append(' '.join(current_chunk))
                    # Keep overlap
                    overlap_sentences = current_chunk[-overlap:]
                    current_chunk = overlap_sentences + [sentence]
                    current_size = sum(len(s.split()) for s in current_chunk)
                else:
                    current_chunk.append(sentence)
                    current_size += sentence_size

            if current_chunk:
                chunks.append(' '.join(current_chunk))

            return chunks
        else:
            # Simple word-based chunking
            words = text.split()
            return [
                ' '.join(words[i:i+chunk_size])
                for i in range(0, len(words), chunk_size - overlap)
            ]
```

---

## 5. API Specifications

### 5.1 Watchlist Endpoints

**GET /watchlist**

```typescript
Response: {
  watchlist: Array<{
    symbol: string;
    sector: string;
    addedAt: number;
    currentPrice: number;
    priceChange: number;
  }>;
}
```

**POST /watchlist**

```typescript
Request: {
  symbol: string;
  sector?: string;
}

Response: {
  success: boolean;
  symbol: string;
  message: string;
}
```

### 5.2 Signal Endpoints

**GET /signals**

```typescript
Request Query Params: {
  limit?: number;  // default 10
  offset?: number;
}

Response: {
  signals: Array<{
    signalId: string;
    symbol: string;
    action: 'BUY' | 'SELL' | 'HOLD';
    confidence: number;  // 0-100
    entryPrice: number;
    targetPrice: number;
    stopLoss: number;
    riskRewardRatio: number;
    holdingPeriodDays: number;
    reasoning: string;
    citations: Array<{
      source: string;
      book: string;
      chapter: string;
      page: number;
      quote: string;
    }>;
    marketState: {
      currentPrice: number;
      rsi: number;
      macd: number;
      patterns: string[];
    };
    timestamp: number;
  }>;
  total: number;
}
```

**POST /signals/generate**

```typescript
Request: {
  symbols: string[];  // Force regenerate for specific symbols
}

Response: {
  jobId: string;
  status: 'processing' | 'completed';
  signalsGenerated: number;
}
```

### 5.3 Journal Endpoints

**GET /journal/trades**

```typescript
Request Query Params: {
  status?: 'open' | 'closed';
  startDate?: string;  // ISO date
  endDate?: string;
}

Response: {
  trades: Array<{
    tradeId: string;
    symbol: string;
    action: 'BUY' | 'SELL';
    entryDate: number;
    entryPrice: number;
    quantity: number;
    exitDate?: number;
    exitPrice?: number;
    profitLoss?: number;
    profitLossPct?: number;
    signalId?: string;
    notes: string;
  }>;
}
```

**POST /journal/trades**

```typescript
Request: {
  symbol: string;
  action: 'BUY' | 'SELL';
  entryDate: string;  // ISO date
  entryPrice: number;
  quantity: number;
  signalId?: string;
  notes?: string;
}
```
