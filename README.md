# AI-Powered Trading Assistant

An AI-powered swing trading assistant that democratizes professional trading knowledge through natural language interaction and real-time market data analysis.

## Project Overview

This system combines:

- **Retrieval-Augmented Generation (RAG)** to query trading knowledge from books and articles
- **Real-time market data analysis** with technical indicators
- **AI-powered signal generation** using AWS Bedrock (Claude)
- **Hybrid search** (vector + lexical) for optimal information retrieval

**Phase 1 Goal**: Generate swing trading signals (3-14 day holds) targeting $1,000 profit with user-executed trades.

## Architecture

### Core Components

- **Backend**: Python FastAPI, LangChain RAG, technical analysis
- **Frontend**: React + TypeScript with Recharts visualization
- **Infrastructure**: AWS CDK (TypeScript) - single CloudFormation stack
- **Storage**: DynamoDB (structured data), S3 (documents/cache), OpenSearch (hybrid search)
- **AI**: AWS Bedrock (Claude for LLM, Titan for embeddings)
- **Compute**: ECS Fargate for containerized services

## Project Structure

```
daily-trade/
├── backend/              # Python FastAPI application
├── frontend/             # React + TypeScript UI
├── infrastructure/       # AWS CDK (single stack)
├── scripts/              # Utility scripts
├── data/                 # Knowledge base and sample data
├── tests/                # Unit, integration, e2e tests
└── docs/                 # Documentation
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- AWS CLI configured
- AWS CDK CLI

### Local Development Setup

1. **Clone and setup**:

```bash
git clone <repository-url>
cd daily-trade
```

2. **Backend setup**:

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your configuration
```

3. **Frontend setup**:

```bash
cd frontend
npm install
cp .env.example .env
# Edit .env with your configuration
```

4. **Infrastructure setup**:

```bash
cd infrastructure
npm install
# Configure AWS credentials
aws configure
# Bootstrap CDK (one-time)
cdk bootstrap
```

5. **Run locally with Docker Compose**:

```bash
docker-compose up
```

Access the application:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Development Workflow

1. Create feature branch: `git checkout -b feature/your-feature`
2. Make changes with tests
3. Run tests: `pytest` (backend) or `npm test` (frontend)
4. Submit PR for review
5. Merge to main after approval

## Deployment

Deploy to AWS using CDK:

```bash
cd infrastructure
cdk deploy
```

This creates a single CloudFormation stack with all resources:

- VPC, subnets, security groups
- ECS Fargate cluster and services
- DynamoDB tables
- OpenSearch domain
- S3 buckets
- API Gateway
- EventBridge rules
- CloudWatch logs and alarms

## Testing

**Backend**:

```bash
cd backend
pytest                    # All tests
pytest tests/unit        # Unit tests only
pytest --cov=app         # With coverage
```

**Frontend**:

```bash
cd frontend
npm test                 # Run tests
npm run test:coverage    # With coverage
```

## Documentation

- [HLD.md](./HLD.md) - High Level Design
- [LLD.md](./LLD.md) - Low Level Design (technical specifications)
- [IMPLEMENTATION.md](./IMPLEMENTATION.md) - Implementation progress tracker
- [docs/API.md](./docs/API.md) - API documentation
- [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) - Deployment guide

## Technology Stack

**Backend**:

- Python 3.11+, FastAPI, LangChain, pandas, yfinance
- boto3 (AWS SDK), opensearch-py

**Frontend**:

- React 18+, TypeScript, Vite
- TanStack Query, Axios, Recharts, Tailwind CSS

**Infrastructure**:

- AWS CDK (TypeScript)
- ECS Fargate, DynamoDB, OpenSearch, S3, Bedrock
- EventBridge, CloudWatch, API Gateway

## Key Features (Phase 1)

- ✅ Daily swing trading signals with AI-powered analysis
- ✅ Technical indicator calculations (SMA, RSI, MACD, Bollinger Bands)
- ✅ Pattern detection and support/resistance levels
- ✅ Source citations from trading books/articles
- ✅ Confidence scoring for signals
- ✅ Trade journal for performance tracking
- ✅ Watchlist management
- ✅ Risk parameter configuration

## Contributing

1. Follow the development workflow above
2. Write tests for new features
3. Maintain 80%+ code coverage
4. Follow code style: PEP 8 (Python), ESLint (TypeScript)
5. Document complex logic
6. Use type hints (Python) and strong typing (TypeScript)

## License

[License Type] - See LICENSE file

## Contact

[Contact Information]

---

**Note**: This is a research and educational tool, not investment advice. Users are responsible for their own trading decisions.
