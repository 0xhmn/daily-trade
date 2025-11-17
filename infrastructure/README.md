# Infrastructure - AWS CDK

Single CloudFormation stack for Daily Trade AI Trading Assistant.

## Quick Commands

```bash
# Install dependencies
npm install

# Bootstrap CDK (one-time per account/region)
cdk bootstrap

# View changes before deployment
cdk diff

# Deploy stack
cdk deploy

# Destroy stack
cdk destroy
```

## Stack Details

**Resources:**

All resources created in `us-east-1`

- 5 DynamoDB tables
- 4 S3 buckets
- OpenSearch domain
- ECS cluster + 2 ECR repos
- EventBridge rules
- SNS topic
- IAM roles
