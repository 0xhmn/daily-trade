# Multimodal Document Ingestion Setup Guide

Complete setup guide for ingesting trading books with charts and graphs into the multimodal RAG system.

## Architecture Overview

The multimodal ingestion system processes PDFs and creates:

- **Text Chunks** with text embeddings
- **Extracted Images** (charts, graphs) with dual embeddings (text + multimodal)
- **Full Page Images** with dual embeddings for context
- **Cross-references** linking related content spatially

## Infrastructure Status

### ✅ Deployed Resources

All required infrastructure is deployed via CDK:

1. **S3 Bucket for Images**

   - Name: `daily-trade-images-560271561561`
   - Location: CDK stack output `ImagesBucketName`
   - Purpose: Store extracted images and full-page images

2. **OpenSearch Domain**

   - Name: `daily-trade-knowledge-001`
   - Endpoint: From CDK output `OpenSearchEndpoint`
   - Indexes: 3 indexes (created on first ingestion)
     - `text-chunks`
     - `extracted-images`
     - `full-page-images`

3. **IAM Roles with Permissions**
   - **ECS Task Role**: For production ingestion
   - **Local OpenSearch Role**: For local development
   - Both roles have required permissions:
     - ✅ Bedrock: `bedrock:InvokeModel`
     - ✅ S3: Read/Write to images bucket
     - ✅ OpenSearch: Full access to domain

### AWS Bedrock Models Required

The following Nova models must be **enabled in your AWS account**:

```
Region: us-east-1

Multimodal Embedding Model:
- amazon.nova-2-multimodal-embeddings-v1:0
  - Dimension: 1024 (default, supports 256/384/1024/3072)
  - Use: Both text and image embeddings in unified semantic space
  - Enables crossmodal retrieval (text query → image results, vice versa)

Vision Model:
- amazon.nova-pro-v1:0
  - Use: Generate descriptions of charts, graphs, and pages
  - Specialized prompts for financial trading content
```

### Verify Bedrock Access

```bash
# Check if models are available
aws bedrock list-foundation-models --region us-east-1 \
  --query 'modelSummaries[?contains(modelId, `nova`)].[modelId, modelName]' \
  --output table

# Test text embedding model
aws bedrock invoke-model \
  --region us-east-1 \
  --model-id amazon.nova-embed-text-v1:0 \
  --body '{"inputText":"test"}' \
  --cli-binary-format raw-in-base64-out \
  response.json

# Test multimodal embedding model
aws bedrock invoke-model \
  --region us-east-1 \
  --model-id amazon.nova-embed-image-v1:0 \
  --body '{"inputText":"test"}' \
  --cli-binary-format raw-in-base64-out \
  response.json

# Test vision model
aws bedrock invoke-model \
  --region us-east-1 \
  --model-id us.amazon.nova-pro-v1:0 \
  --body '{"messages":[{"role":"user","content":[{"text":"Hello"}]}],"inferenceConfig":{}}' \
  --cli-binary-format raw-in-base64-out \
  response.json
```

If any model is not available, enable it in the AWS Console:

1. Go to Amazon Bedrock console
2. Navigate to "Base models" or "Model access"
3. Request access for Nova models if needed

## Installation

### Python Dependencies

All required packages are in `backend/requirements.txt`:

```txt
boto3>=1.34.0
opensearch-py>=2.3.0
PyMuPDF>=1.23.0  # fitz for image extraction
pdfplumber>=0.10.0
Pillow>=10.0.0
requests-aws4auth>=1.2.0
tqdm>=4.66.0
```

Install:

```bash
cd backend
pip install -r requirements.txt
```

### AWS Credentials

For local development, assume the OpenSearch access role:

```bash
# Set in your environment
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-1

# Or use AWS SSO
aws sso login --profile your-profile

# Verify credentials
aws sts get-caller-identity
```

## Usage

### Basic Example (Test Document)

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

**Note**: Use `--create-indexes` flag on first run to create the 3 OpenSearch indexes.

### Production Example (William O'Neil Book)

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
  --concepts \
    CAN_SLIM \
    cup_with_handle \
    relative_strength \
    institutional_sponsorship \
    volume_analysis \
    market_direction
```

### Command-Line Options

#### Required Arguments

- `--pdf`: Path to PDF file
- `--title`: Document title
- `--strategy-type`: Strategy type (swing_trading, technical_analysis, risk_management, test)
- `--document-type`: Document type (test-doc, ebook, article)
- `--opensearch-host`: OpenSearch domain endpoint
- `--s3-bucket`: S3 bucket name for images

#### Optional Arguments

- `--author`: Document author
- `--timeframe`: Trading timeframe (default: "swing_trading")
- `--market-conditions`: Space-separated list (default: trending ranging)
- `--asset-class`: Space-separated list (default: equities)
- `--concepts`: Space-separated key concepts
- `--region`: AWS region (default: us-east-1)
- `--local-role-arn`: IAM role for local access
- `--chunk-size`: Text chunk size in characters (default: 1000)
- `--chunk-overlap`: Chunk overlap in characters (default: 200)
- `--embedding-dimension`: Nova dimension (default: 1024, choices: 256/384/1024/3072)
- `--image-extraction-method`: Method for extracting images (default: get_images)
  - `get_images`: Extract embedded raster images (photos, screenshots)
  - `get_svg_image`: Extract vector graphics as SVG
  - `get_drawings`: Extract vector drawings (charts, graphs) - **recommended for financial books**
- `--full-page-dpi`: DPI for full-page rendering (default: 150)
- `--create-indexes`: Create OpenSearch indexes if they don't exist
- `--skip-indexing`: Process locally without indexing to OpenSearch

## Ingestion Pipeline

The script orchestrates the complete multimodal pipeline:

### Phase 1: Extraction

1. **Text Extraction**: Extract text from PDF and chunk intelligently
2. **Image Extraction**: Extract embedded images (charts, graphs)
3. **Page Rendering**: Convert each page to full-page image

### Phase 2: Analysis & Embedding

4. **Vision Analysis**: Generate descriptions of images and pages with Nova Vision
   - Chart-specific descriptions for trading content
   - Identify technical indicators (RSI, MACD, Bollinger Bands)
   - Recognize patterns (head & shoulders, triangles, etc.)
5. **Text Embeddings**: Generate embeddings for text chunks and descriptions
6. **Multimodal Embeddings**: Generate embeddings from image bytes

### Phase 3: Cross-Referencing

7. **Spatial Linking**: Link images to nearby text based on page position
8. **Page Linking**: Link all content on same page
9. **Bidirectional References**: Create two-way relationships

### Phase 4: Indexing

10. **Bulk Index**: Index to 3 OpenSearch indexes simultaneously
    - Text chunks → `text-chunks` index
    - Extracted images → `extracted-images` index
    - Full pages → `full-page-images` index

## Expected Output

Successful ingestion shows:

```
================================================================================
✓ INGESTION COMPLETED SUCCESSFULLY!
================================================================================
Document ID: oneil_how_to_make_money
Status: success

Indexed Documents:
  • Text Chunks: 245
  • Extracted Images: 87
  • Full Page Images: 350
  • Total: 682
================================================================================

OpenSearch Index Statistics:
  • text:
    - Documents: 245
  • extracted_images:
    - Documents: 87
  • full_pages:
    - Documents: 350
================================================================================
```

## Troubleshooting

### Permission Errors

**Error**: `AccessDeniedException` when calling Bedrock

**Solution**: Verify Bedrock model access in AWS Console

```bash
aws bedrock list-foundation-models --region us-east-1
```

### OpenSearch Connection Errors

**Error**: `ConnectionTimeout` or `AuthenticationException`

**Solution**:

1. Verify OpenSearch endpoint is correct
2. Check IAM role has proper permissions
3. Ensure you're assuming the correct role

```bash
# Test OpenSearch connectivity
curl -X GET "https://YOUR-OPENSEARCH-ENDPOINT/_cluster/health" \
  --aws-sigv4 "aws:amz:us-east-1:es"
```

### S3 Upload Errors

**Error**: `NoSuchBucket` or `AccessDenied`

**Solution**:

1. Verify S3 bucket name matches CDK output
2. Check IAM role has S3 permissions
3. Ensure bucket is in correct region

```bash
# List bucket contents
aws s3 ls s3://daily-trade-images-560271561561/
```

### Large File Processing

**Error**: Memory issues with large PDFs

**Solution**:

- Use `--image-extraction-method get_images` instead of `get_drawings`
- Process pages in smaller batches
- Increase available memory

## Next Steps

After successful ingestion:

1. **Query the System**: Use hybrid multimodal search

   ```python
   from services.hybrid_multimodal_search import HybridMultimodalSearch

   search = HybridMultimodalSearch(opensearch_host, s3_bucket)
   results = await search.search("RSI divergence patterns", k=10)
   ```

2. **Verify Cross-References**: Check that images link to text

   ```python
   # Get an extracted image
   images = repository.get_by_ids([image_id], "extracted_images")

   # Check its related text chunks
   related_chunks = images[0]["related_text_chunk_ids"]
   ```

3. **Test Retrieval Quality**: Query for specific concepts
   - Technical indicators
   - Chart patterns
   - Trading strategies

## Performance Considerations

- **Processing Time**: ~2-5 minutes per 100 pages (with images)
- **API Costs**: Nova Vision + Embeddings (check AWS pricing)
- **Storage**: ~500KB per full-page image at 150 DPI
- **OpenSearch**: kNN search scales well up to millions of vectors

## Additional Resources

- [Multimodal RAG Architecture](./MULTIMODAL_RAG_ARCHITECTURE.md)
- [AWS Nova Models](https://docs.aws.amazon.com/nova/)
- [OpenSearch k-NN Plugin](https://opensearch.org/docs/latest/search-plugins/knn/)
