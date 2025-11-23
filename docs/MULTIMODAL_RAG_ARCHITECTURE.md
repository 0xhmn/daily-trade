# Hybrid Multimodal RAG Architecture

## Overview

This document describes the complete hybrid multimodal RAG (Retrieval-Augmented Generation) system for the trading knowledge base, implementing maximum accuracy through 5-stream retrieval with Amazon Nova embeddings.

## Architecture Components

### 1. Embedding Layer

**File:** `backend/ingestion/multimodal_embedder.py`

**Model:** Amazon Nova Multimodal Embeddings (`amazon.nova-2-multimodal-embeddings-v1:0`)

**Features:**

- Unified semantic space for text and images
- Crossmodal retrieval capability
- Flexible dimensions: 3072, 1024, 384, 256 (using 1024 for balance)
- Purpose-specific embeddings:
  - `GENERIC_INDEX` for document indexing
  - `GENERIC_RETRIEVAL` for query processing
  - `DOCUMENT_RETRIEVAL` for document-specific queries

### 2. Document Processing Pipeline

#### Text Processing (`document_processor.py`)

- Extract text from PDFs using pdfplumber/PyPDF2
- Clean and chunk text (1000 chars, 200 overlap)
- Preserve sentence boundaries
- Track page numbers and metadata

#### Image Processing (`image_processor.py`)

- Three extraction methods:
  - `GET_IMAGES`: Embedded raster images (charts, diagrams)
  - `GET_SVG_IMAGE`: Vector graphics
  - `GET_DRAWINGS`: Vector drawings with filters
- Extract position metadata (bbox)
- Upload to S3 for storage
- Generate descriptions via Nova vision models

#### Full Page Processing

- Convert PDF pages to images (150 DPI)
- Generate comprehensive descriptions
- Capture complex layouts and text-image relationships

### 3. Storage Layer

**File:** `backend/repositories/multimodal_opensearch_repository.py`

**Three OpenSearch Indexes:**

#### A. `text_chunks_index`

```json
{
  "chunk_id": "doc123_chunk_001",
  "text_content": "...",
  "text_embedding": [1024-dim],
  "page_number": 42,
  "chunk_index": 1,
  "bbox": {"x0": 72, "y0": 100, "x1": 540, "y1": 200},
  "metadata": {
    "title": "Technical Analysis of Financial Markets",
    "author": "John Murphy",
    "strategy_type": "technical_analysis",
    "timeframe": "swing_trading",
    "market_conditions": ["trending", "ranging"],
    "asset_class": ["equities"],
    "key_concepts": ["chart_patterns", "RSI", "MACD"],
    "source_file": "murphy_technical_analysis.pdf",
    "document_type": "ebook"
  },
  "related_extracted_image_ids": ["doc123_p0042_img001"],
  "full_page_image_id": "doc123_fullpage_p0042"
}
```

#### B. `extracted_images_index`

```json
{
  "image_id": "doc123_p0042_img001",
  "image_type": "chart",
  "multimodal_embedding": [1024-dim],
  "text_embedding": [1024-dim],
  "text_description": "RSI chart showing divergence pattern...",
  "s3_uri": "s3://daily-trade-images/doc123/doc123_p0042_img001.png",
  "page_number": 42,
  "bbox": {"x0": 100, "y0": 200, "x1": 500, "y1": 400},
  "extraction_method": "get_images",
  "metadata": {
    "title": "Technical Analysis of Financial Markets",
    "author": "John Murphy",
    "strategy_type": "technical_analysis",
    "timeframe": "swing_trading",
    "market_conditions": ["trending", "ranging"],
    "asset_class": ["equities"],
    "key_concepts": ["chart_patterns", "RSI", "MACD"],
    "source_file": "murphy_technical_analysis.pdf",
    "document_type": "ebook",
    "width": 800,
    "height": 600,
    "file_size_kb": 125.5,
    "technical_elements": ["RSI", "price_chart", "divergence_lines"]
  },
  "related_text_chunk_ids": ["doc123_chunk_001"],
  "full_page_image_id": "doc123_fullpage_p0042"
}
```

#### C. `full_page_images_index`

```json
{
  "page_image_id": "doc123_fullpage_p0042",
  "multimodal_embedding": [1024-dim],
  "text_embedding": [1024-dim],
  "text_description": "Full page showing RSI divergence explanation...",
  "s3_uri": "s3://daily-trade-images/doc123/doc123_fullpage_p0042.png",
  "page_number": 42,
  "dpi": 150,
  "metadata": {
    "title": "Technical Analysis of Financial Markets",
    "author": "John Murphy",
    "strategy_type": "technical_analysis",
    "timeframe": "swing_trading",
    "market_conditions": ["trending", "ranging"],
    "asset_class": ["equities"],
    "key_concepts": ["chart_patterns", "RSI", "MACD"],
    "source_file": "murphy_technical_analysis.pdf",
    "document_type": "ebook",
    "width": 1275,
    "height": 1650,
    "file_size_kb": 450.2,
    "layout_complexity": "high",
    "contains_elements": ["text", "chart", "diagram"]
  },
  "text_chunk_ids": ["doc123_chunk_001", "doc123_chunk_002"],
  "extracted_image_ids": ["doc123_p0042_img001"]
}
```

### 4. Hybrid Search Engine

**File:** `backend/services/hybrid_multimodal_search.py`

**5-Stream Parallel Retrieval:**

1. **Text-to-Text:** `query_text_emb → text_chunks.text_embedding`
2. **Text-to-Extracted-Image (Text):** `query_text_emb → extracted_images.text_embedding`
3. **Text-to-Extracted-Image (Multimodal):** `query_text_emb → extracted_images.multimodal_embedding`
4. **Text-to-Full-Page (Text):** `query_text_emb → full_pages.text_embedding`
5. **Text-to-Full-Page (Multimodal):** `query_text_emb → full_pages.multimodal_embedding`

**Reciprocal Rank Fusion (RRF):**

```
RRF_score(doc) = Σ [1 / (k + rank_i)] for all streams
where k = 60 (standard constant)
```

**Contextual Expansion:**

- Text chunk → Add related images + full page
- Extracted image → Add related text + full page
- Full page → Add top images + text chunks

## Complete Workflow

### Ingestion Phase

```
PDF Document
    │
    ├─→ Text Extraction (document_processor.py)
    │   ├─→ Chunk text (1000 chars, 200 overlap)
    │   ├─→ Generate text embeddings (Nova)
    │   └─→ Index to text_chunks_index
    │
    ├─→ Image Extraction (image_processor.py)
    │   ├─→ Extract charts/diagrams (GET_IMAGES)
    │   ├─→ Upload to S3
    │   ├─→ Generate description (Nova vision)
    │   ├─→ Generate dual embeddings (Nova)
    │   │   ├─→ Text embedding (from description)
    │   │   └─→ Multimodal embedding (from image)
    │   └─→ Index to extracted_images_index
    │
    └─→ Full Page Imaging
        ├─→ Convert page to image (150 DPI)
        ├─→ Upload to S3
        ├─→ Generate description (Nova vision)
        ├─→ Generate dual embeddings (Nova)
        └─→ Index to full_page_images_index

Cross-Reference Linking
    ├─→ Link text chunks ↔ extracted images (spatial proximity)
    ├─→ Link text chunks → full page
    ├─→ Link extracted images → full page
    └─→ Link full page → text chunks + images
```

### Query Phase

```
User Query: "Explain RSI divergence with examples"
    │
    ├─→ Generate Query Embedding (Nova, purpose=GENERIC_RETRIEVAL)
    │
    ├─→ Parallel 5-Stream Search (k=15 each)
    │   ├─→ Stream 1: Text-to-Text
    │   ├─→ Stream 2: Text-to-Extracted-Image (Text)
    │   ├─→ Stream 3: Text-to-Extracted-Image (Multimodal)
    │   ├─→ Stream 4: Text-to-Full-Page (Text)
    │   └─→ Stream 5: Text-to-Full-Page (Multimodal)
    │
    ├─→ Reciprocal Rank Fusion
    │   └─→ Top 10 results
    │
    ├─→ Contextual Expansion
    │   ├─→ For each result, add related content
    │   ├─→ Deduplicate
    │   └─→ Max 20 results
    │
    └─→ Format for Nova Converse API
        ├─→ Image 1 (extracted chart with RSI)
        ├─→ Image 2 (full page with context)
        ├─→ Text chunk 1 (explanation)
        ├─→ Text chunk 2 (examples)
        └─→ Query + System Prompt
            │
            └─→ Nova Response with Citations
```

## Key Advantages

### 1. Maximum Accuracy

- **5 retrieval streams** vs standard 1-2 streams
- **Dual embeddings** for images (text + multimodal)
- **Full page context** captures layouts and relationships
- **Spatial linking** connects related content

### 2. Comprehensive Coverage

- **Granular:** Extracted charts provide detail
- **Holistic:** Full pages provide context
- **Crossmodal:** Text can find images, images can find text

### 3. Robust Retrieval

- **Text fallback:** If multimodal fails, text embeddings work
- **Contextual expansion:** Automatically brings related content
- **RRF fusion:** Balanced ranking across modalities

### 4. Financial Document Optimized

- **Chart extraction:** Captures technical indicators (RSI, MACD)
- **Diagram processing:** Handles complex trading diagrams
- **Table extraction:** Preserves tabular data
- **Full page imaging:** Captures infographics and layouts

## Storage Estimates

Per 100-page financial book with 50 charts:

- **Text chunks:** ~200 chunks × 1KB = 200KB
- **Extracted images:** 50 images × ~100KB = 5MB (S3)
- **Full pages:** 100 pages × ~300KB = 30MB (S3)
- **Embeddings:** (200 + 50×2 + 100×2) × 1024×4 bytes = ~1.6MB
- **Total per book:** ~36MB + metadata

## Performance Considerations

### Retrieval Latency

- 5 parallel streams: ~200-300ms total
- RRF fusion: ~10ms
- Contextual expansion: ~50-100ms
- **Total:** ~300-400ms for comprehensive retrieval

### Accuracy vs Speed Tradeoffs

- **Current (1024-dim):** Balanced for accuracy and speed
- **High accuracy (3072-dim):** +30% storage, +20% latency
- **Fast (384-dim):** -60% storage, -30% latency, -5% accuracy

### Scalability

- **1000 books:** ~36GB storage, handles 10-20 QPS
- **10,000 books:** ~360GB storage, requires OpenSearch sharding
- **Horizontal scaling:** Add OpenSearch nodes for capacity

## Implementation Checklist

- [x] Create multimodal OpenSearch repository (3 indexes)
- [x] Build Nova multimodal embedder
- [x] Implement 5-stream hybrid search with RRF
- [ ] Create document ingestion orchestrator
- [ ] Build cross-reference linking logic
- [ ] Create Nova vision service for image descriptions
- [ ] Implement full page image generation
- [ ] Build spatial proximity calculation
- [ ] Create ingestion pipeline script
- [ ] Add monitoring and logging
- [ ] Build Nova Converse API integration
- [ ] Create retrieval quality metrics
- [ ] Add caching layer for frequent queries

## Next Steps

1. **Create Ingestion Orchestrator** that coordinates:

   - Text processing
   - Image extraction
   - Full page generation
   - Embedding generation
   - Cross-reference linking
   - Bulk indexing

2. **Build Nova Vision Service** for:

   - Image-to-text description generation
   - Technical element detection (RSI, MACD, etc.)
   - Chart type classification

3. **Implement Spatial Linking** logic:

   - Calculate bbox overlaps
   - Link text chunks to nearby images
   - Handle multi-column layouts

4. **Create Response Formatter** for Nova Converse:
   - Organize images by relevance
   - Format text chunks
   - Build citation system
   - Handle token limits

## References

- AWS Nova Multimodal RAG: https://docs.aws.amazon.com/nova/latest/userguide/rag-multimodal.html
- AWS Nova Embeddings Blog: https://aws.amazon.com/blogs/aws/amazon-nova-multimodal-embeddings-now-available-in-amazon-bedrock/
- RRF Paper: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf
- MRL Embeddings: https://arxiv.org/abs/2205.13147
