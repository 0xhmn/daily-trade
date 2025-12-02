# Testing Notebooks

## End-to-End Signal Generation Test

**File**: `test_signal_generation.ipynb`

### Purpose

Interactive testing of the complete signal generation pipeline without requiring API or frontend implementations. Tests each component step-by-step:

1. Service initialization
2. Mock market data generation
3. PromptProvider verification
4. RAG retrieval from OpenSearch
5. Signal generation (SWING + POSITION styles)
6. Multi-scenario testing
7. Results comparison and export

### Prerequisites

#### 1. Python Environment

```bash
# Ensure all dependencies installed
pip install -r ../backend/requirements.txt

# Install Jupyter if not already installed
pip install jupyter notebook ipykernel pandas
```

#### 2. AWS Credentials

```bash
# Configure AWS CLI
aws configure

# Or set environment variables
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx
export AWS_REGION=us-east-1
```

#### 3. OpenSearch Access

```bash
# Set OpenSearch endpoint in .env file
cd ../backend
cp .env.example .env

# Edit .env and set:
# OPENSEARCH_HOST=search-daily-trade-xxxxx.us-east-1.es.amazonaws.com
# STAGE=local
```

#### 4. Trading Books Ingested

Ensure you've ingested at least one trading book to OpenSearch:

```bash
# From project root
python scripts/ingest_multimodal_documents.py \
    --file data/knowledge_base/swing_trading/book.pdf \
    --metadata '{"document_type": "book", "topics": ["swing_trading"]}' \
    --stage local
```

### Running the Notebook

#### Option 1: Jupyter Notebook (Classic)

```bash
# From notebooks directory
cd notebooks
jupyter notebook

# Browser will open
# Click on test_signal_generation.ipynb
# Run cells sequentially with Shift+Enter
```

#### Option 2: JupyterLab (Modern UI)

```bash
pip install jupyterlab
jupyter lab

# Navigate to test_signal_generation.ipynb
```

#### Option 3: VS Code

```bash
# Install Jupyter extension in VS Code
# Open test_signal_generation.ipynb
# Select Python kernel
# Run cells with play button or Shift+Enter
```

### What the Notebook Tests

#### Section 1-2: Setup

- Python path configuration
- Import validation
- Configuration loading from .env

#### Section 3: Service Initialization

- OpenSearch Repository connection
- Nova Embedder setup
- Hybrid Search initialization
- LangChain Retriever setup
- RAG Service creation
- Bedrock Service (Claude 4.5)
- PromptProvider loading (SWING + POSITION)
- SignalService orchestration
- Mock Data Generator

#### Section 4: Mock Data

- Generate realistic market scenarios
- Display technical indicators
- Show support/resistance levels
- Display detected patterns

#### Section 5: RAG Testing

- Query OpenSearch with trading queries
- Display retrieved documents
- Show relevance scores
- Display citations with page numbers

#### Section 6-7: Signal Generation

- Generate SWING trading signal
- Generate POSITION trading signal
- Display complete signal details
- Show reasoning and citations

#### Section 8: Comparison

- Side-by-side comparison table
- Highlight differences between styles
- Compare holding periods and risk parameters

#### Section 9: Multi-Scenario Testing

- Test 3 different market scenarios
- Generate signals for multiple symbols
- Display success/failure summary

#### Section 10: Export

- Save results to JSON file
- Include all signals and metadata

### Expected Output

Each cell will display:

- ✅ Success indicators
- Detailed component information
- Retrieved documents with scores
- Generated signals with full details
- Confidence scores and reasoning
- Citations from knowledge base
- Validation results

### Troubleshooting

#### OpenSearch Connection Error

```python
# In notebook, manually check connectivity:
from backend.repositories.multimodal_opensearch_repository import MultimodalOpenSearchRepository

repo = MultimodalOpenSearchRepository(host="your-host.es.amazonaws.com", stage="local")
info = repo.client.info()
print(info)
```

#### AWS Credentials Error

```bash
# Verify credentials
aws sts get-caller-identity

# Check region
echo $AWS_REGION
```

#### Import Errors

```bash
# Reinstall dependencies
pip install -r ../backend/requirements.txt --force-reinstall

# Verify langchain-core installed
pip show langchain-core
```

#### No Documents Retrieved

```bash
# Check if books are indexed
python scripts/opensearch_query_helper.py

# Re-ingest if needed
python scripts/ingest_multimodal_documents.py --file path/to/book.pdf
```

### Cost Considerations

**Per Signal Generation:**

- Claude Opus 4.5: ~$0.01-0.03 per call
- Nova Embeddings: ~$0.0001 per query
- OpenSearch queries: Free (already deployed)

**Total per notebook run**: ~$0.10-0.30 (generates ~10 signals)

### Next Steps After Testing

Once notebook validates the pipeline:

1. **Phase 3**: Build FastAPI endpoints
2. **Phase 4**: Create React frontend
3. **Phase 5**: Replace mock data with real market data
4. **Phase 6**: Add automated daily analysis

### Notes

- Run cells sequentially (dependencies flow through cells)
- First run takes longer (service initialization)
- Subsequent cells execute quickly
- Results saved to `test_results.json` in notebooks directory
- Use `Kernel > Restart & Clear Output` to reset state
