# Local OpenSearch Access Guide

This guide explains how to access OpenSearch from your local machine for development.

## Overview

The system uses environment-based credential management:

- **STAGE=local** (default): Assumes IAM role for local development
- **STAGE=prod**: Uses default credentials (ECS task role in production)

## Prerequisites

1. AWS CLI configured with your IAM user credentials
2. CDK stack deployed (`cd infrastructure && cdk deploy`)
3. Your IAM user has permission to assume the local access role

## Setup Steps

### 1. Deploy Infrastructure

```bash
cd infrastructure
npm install
cdk bootstrap  # One-time per account/region
cdk deploy
```

Save the outputs, especially:

- `LocalOpenSearchRoleArn`: Role ARN for local access
- `OpenSearchEndpoint`: OpenSearch domain endpoint

### 2. Configure Environment

Create `backend/.env` from the example:

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```bash
STAGE=local
OPENSEARCH_ROLE_ARN=arn:aws:iam::123456789012:role/DailyTradeLocalOpenSearchAccess
OPENSEARCH_HOST=search-daily-trade-knowledge-xxxxx.us-east-1.es.amazonaws.com
```

Replace with your actual values from CDK outputs.

### 3. Grant Your IAM User Permission

Your IAM user needs `sts:AssumeRole` permission. Add this policy to your IAM user:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::YOUR_ACCOUNT_ID:role/DailyTradeLocalOpenSearchAccess"
    }
  ]
}
```

Or use AWS CLI:

```bash
# Get your account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Get your IAM username
IAM_USER=$(aws sts get-caller-identity --query 'Arn' --output text | cut -d'/' -f2)

# Attach inline policy
aws iam put-user-policy \
  --user-name $IAM_USER \
  --policy-name AssumeOpenSearchRole \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::'$ACCOUNT_ID':role/DailyTradeLocalOpenSearchAccess"
    }]
  }'
```

## How It Works

### Automatic Role Assumption

The system automatically handles credentials:

```python
from utils.aws_credentials import get_credentials_for_opensearch

# Automatically uses STAGE environment variable
# STAGE=local: Assumes role specified by local_role_arn
# STAGE=prod: Uses default credentials (task role)
session = get_credentials_for_opensearch(
    region="us-east-1",
    local_role_arn="arn:aws:iam::123456789012:role/DailyTradeLocalOpenSearchAccess"
)
```

### OpenSearch Repository

```python
from repositories.opensearch_repository import OpenSearchRepository

# Automatically handles credentials based on STAGE
repo = OpenSearchRepository(
    host="search-daily-trade-knowledge-xxxxx.us-east-1.es.amazonaws.com",
    region="us-east-1",
    local_role_arn="arn:aws:iam::123456789012:role/DailyTradeLocalOpenSearchAccess"
)
```

## Running the Ingestion Script

### Option 1: With Environment Variables

Set environment variables:

```bash
export STAGE=local
export OPENSEARCH_ROLE_ARN=arn:aws:iam::123456789012:role/DailyTradeLocalOpenSearchAccess
```

Run the script:

```bash
python scripts/ingest_documents.py \
  --pdf data/knowledge_base/swing_trading/Alan_Farley_The_Master_Swing_Trader.pdf \
  --title "The Master Swing Trader" \
  --author "Alan Farley" \
  --strategy-type swing_trading \
  --opensearch-host search-daily-trade-knowledge-xxxxx.us-east-1.es.amazonaws.com \
  --local-role-arn arn:aws:iam::123456789012:role/DailyTradeLocalOpenSearchAccess \
  --create-index
```

### Option 2: Command Line Only

Pass everything via command line:

```bash
STAGE=local python scripts/ingest_documents.py \
  --pdf data/knowledge_base/swing_trading/Alan_Farley_The_Master_Swing_Trader.pdf \
  --title "The Master Swing Trader" \
  --author "Alan Farley" \
  --strategy-type swing_trading \
  --opensearch-host search-daily-trade-knowledge-xxxxx.us-east-1.es.amazonaws.com \
  --local-role-arn arn:aws:iam::123456789012:role/DailyTradeLocalOpenSearchAccess \
  --create-index
```

## Troubleshooting

### Error: "Access denied when assuming role"

**Cause**: Your IAM user lacks permission to assume the role.

**Solution**: Add the `sts:AssumeRole` policy (see Setup Step 3).

### Error: "STAGE=local requires local_role_arn parameter"

**Cause**: Running with STAGE=local but no role ARN provided.

**Solutions**:

1. Set `OPENSEARCH_ROLE_ARN` environment variable
2. Pass `--local-role-arn` to the script
3. Set `STAGE=prod` (not recommended for local dev)

### Error: "403 Forbidden" from OpenSearch

**Causes**:

1. Role assumption succeeded but OpenSearch access policy doesn't include the role
2. Credentials expired (12-hour limit)

**Solutions**:

1. Verify CDK stack includes the role in OpenSearch access policy (it should by default)
2. Re-run the script (credentials will refresh automatically)

### Verify Your Setup

Test credential assumption:

```bash
python -c "
import os
os.environ['STAGE'] = 'local'
from backend.utils.aws_credentials import get_credentials_for_opensearch

session = get_credentials_for_opensearch(
    region='us-east-1',
    local_role_arn='arn:aws:iam::YOUR_ACCOUNT_ID:role/DailyTradeLocalOpenSearchAccess'
)

sts = session.client('sts')
identity = sts.get_caller_identity()
print(f'Using identity: {identity[\"Arn\"]}')
"
```

Expected output:

```
STAGE=local - Assuming role for local development
Assuming role: arn:aws:iam::123456789012:role/DailyTradeLocalOpenSearchAccess
Successfully assumed role
Credentials expire at: 2025-11-16 21:38:00+00:00
Using identity: arn:aws:sts::123456789012:assumed-role/DailyTradeLocalOpenSearchAccess/local-dev-12345
Using identity: arn:aws:sts::123456789012:assumed-role/DailyTradeLocalOpenSearchAccess/local-dev-12345
```

## Production Usage

In production (ECS/Fargate), set `STAGE=prod`:

```bash
# In ECS task definition environment variables
STAGE=prod
```

The system automatically uses the ECS task role. No role assumption needed.

## Security Notes

1. **Credentials expire after 12 hours**: Re-run commands to refresh
2. **Role has limited permissions**: Only OpenSearch, Bedrock, and S3 access
3. **Production uses task role**: No role assumption in prod for better security
4. **Audit trail**: All role assumptions logged in CloudTrail

## Quick Reference

| Environment | STAGE | Credentials Source      | Role Assumption |
| ----------- | ----- | ----------------------- | --------------- |
| Local Dev   | local | IAM user → Assumed role | Required        |
| ECS/Fargate | prod  | ECS task role           | Not needed      |

## Additional Resources

- [AWS STS AssumeRole Documentation](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html)
- [OpenSearch Fine-Grained Access Control](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/fgac.html)
- [CDK Stack Configuration](../infrastructure/lib/daily-trade-stack.ts)
