# Quick Start: Test Multimodal Ingestion

Quick guide to test the multimodal document ingestion system.

## ✅ Prerequisites Verified

Based on your Bedrock model list, you have access to:

- ✅ `amazon.nova-2-multimodal-embeddings-v1:0` - Multimodal embeddings
- ✅ `amazon.nova-pro-v1:0` - Vision model
- ✅ S3 bucket: `daily-trade-images-560271561561`
- ✅ OpenSearch domain: `daily-trade-knowledge-001-l5zwovvaduyu5jorkbqfcrpspe.us-east-1.es.amazonaws.com`

## 🚀 Test with Sample PDF (4 pages)

Run this command to test with the small sample PDF:

```bash
python scripts/ingest_multimodal_documents.py \
  --pdf data/sample_data/4_page_with_image.pdf \
  --opensearch-host search-daily-trade-knowledge-001-l5zwovvaduyu5jorkbqfcrpspe.us-east-1.es.amazonaws.com \
  --local-role-arn arn:aws:iam::560271561561:role/DailyTradeLocalOpenSearchAccess \
  --s3-bucket daily-trade-images-560271561561 \
  --title "Technical Analysis Sample" \
  --author "Test Author" \
  --strategy-type test \
  --document-type test-doc \
  --create-indexes
```

**Expected Duration**: ~2-3 minutes

**What It Does**:

1. Creates 3 OpenSearch indexes (first run only)
2. Extracts text and images from PDF
3. Generates descriptions with Nova Vision
4. Creates dual embeddings (text + multimodal)
5. Links content spatially
6. Indexes to OpenSearch

## 📊 Expected Output

```
================================================================================
MULTIMODAL DOCUMENT INGESTION
Document: Technical Analysis Sample
PDF: data/sample_data/4_page_with_image.pdf
================================================================================

[1/2] Initializing multimodal orchestrator...
✓ S3 Bucket: daily-trade-images-560271561561
✓ OpenSearch: search-daily-trade-knowledge-001-...
✓ Embedding Dimension: 1024
✓ Image Extraction: get_images

[2/2] Initializing OpenSearch repository...
Creating OpenSearch indexes...
✓ Indexes created successfully

================================================================================
STARTING INGESTION PIPELINE
================================================================================

[Phase 1/4] Extracting text chunks...
[Phase 2/4] Extracting images...
[Phase 3/4] Rendering full pages...
[Phase 4/4] Generating embeddings and indexing...

================================================================================
✓ INGESTION COMPLETED SUCCESSFULLY!
================================================================================
Document ID: 4_page_with_image
Status: success

Indexed Documents:
  • Text Chunks: 15
  • Extracted Images: 3
  • Full Page Images: 4
  • Total: 22
================================================================================

OpenSearch Index Statistics:
  • text:
    - Documents: 15
  • extracted_images:
    - Documents: 3
  • full_pages:
    - Documents: 4
================================================================================
```

## 🔍 Verify Results

### Check S3 Bucket

```bash
aws s3 ls s3://daily-trade-images-560271561561/images/4_page_with_image/
```

You should see uploaded images.

### Check OpenSearch Indexes

```bash
# Check index stats
curl -X GET "https://search-daily-trade-knowledge-001-l5zwovvaduyu5jorkbqfcrpspe.us-east-1.es.amazonaws.com/text-chunks/_count" \
  --aws-sigv4 "aws:amz:us-east-1:es"
```

## 📚 Next: Process Real Trading Book

After successful test, process the William O'Neil book:

```bash
python scripts/ingest_multimodal_documents.py \
  --pdf "data/knowledge_base/swing_trading/O'Neil - 2009 - How to make money in stocks.pdf" \
  --opensearch-host search-daily-trade-knowledge-001-l5zwovvaduyu5jorkbqfcrpspe.us-east-1.es.amazonaws.com \
  --local-role-arn arn:aws:iam::560271561561:role/DailyTradeLocalOpenSearchAccess \
  --s3-bucket daily-trade-images-560271561561 \
  --title "How to Make Money in Stocks" \
  --author "William O'Neil" \
  --strategy-type swing_trading \
  --document-type ebook \
  --timeframe "3-8_weeks" \
  --market-conditions trending bullish \
  --asset-class equities \
  --concepts CAN_SLIM cup_with_handle relative_strength
```

**Note**: Remove `--create-indexes` flag since indexes already exist.

**Expected Duration**: ~20-30 minutes (large book with many charts)

## ⚠️ Troubleshooting

### If Bedrock Access Denied

```bash
# Verify you can list models
aws bedrock list-foundation-models --region us-east-1

# If models not showing, enable in AWS Console:
# Bedrock → Model access → Request access for Nova models
```

### If OpenSearch Connection Fails

```bash
# Verify credentials
aws sts get-caller-identity

# Test OpenSearch endpoint
curl -X GET "https://search-daily-trade-knowledge-001-l5zwovvaduyu5jorkbqfcrpspe.us-east-1.es.amazonaws.com/_cluster/health" \
  --aws-sigv4 "aws:amz:us-east-1:es"
```

### If Python Dependencies Missing

```bash
cd backend
pip install -r requirements.txt
```

## 📖 Full Documentation

For complete details, see:

- [Multimodal Ingestion Setup Guide](docs/MULTIMODAL_INGESTION_SETUP.md)
- [Multimodal RAG Architecture](docs/MULTIMODAL_RAG_ARCHITECTURE.md)
