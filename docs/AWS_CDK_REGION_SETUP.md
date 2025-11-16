# AWS CDK Region Configuration Guide

## Understanding `cdk.Aws.REGION`

`cdk.Aws.REGION` is a CloudFormation pseudo-parameter that resolves to the region where the stack is deployed. It's dynamically resolved at deployment time, not during synthesis.

## Current Region Configuration

Your CDK app is configured in `infrastructure/bin/daily-trade-stack.ts`:

```typescript
new DailyTradeStack(app, "DailyTradeStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || "us-east-1", // ← Falls back to us-east-1
  },
  // ...
});
```

## How to Check Current Region

### Option 1: Check AWS CLI Configuration

```bash
# Show current AWS region from configuration
aws configure get region

# Show all AWS CLI configuration
aws configure list
```

### Option 2: Check Environment Variables

```bash
# Check if AWS_REGION or AWS_DEFAULT_REGION is set
echo $AWS_REGION
echo $AWS_DEFAULT_REGION
echo $CDK_DEFAULT_REGION
```

### Option 3: Use AWS STS to Get Current Identity

```bash
# This shows your account and region information
aws sts get-caller-identity

# To get just the region from AWS CLI config
aws configure get region
```

### Option 4: Check CDK Context

```bash
cd infrastructure

# See what CDK will use (during synth)
cdk context --clear
npx cdk synth --quiet | grep -A 5 "Environment"
```

## How to Set Region for CDK Deployment

### Method 1: AWS CLI Configuration (Recommended)

```bash
# Set default region globally
aws configure set region us-east-1

# Or configure interactively
aws configure
# Then enter your region when prompted
```

### Method 2: Environment Variable (Session-specific)

```bash
# Set for current terminal session
export AWS_REGION=us-east-1
export CDK_DEFAULT_REGION=us-east-1

# Then deploy
cd infrastructure
cdk deploy
```

### Method 3: Inline with Command

```bash
# Set region for single command
AWS_REGION=us-east-1 cdk deploy

# Or
CDK_DEFAULT_REGION=us-west-2 cdk deploy
```

### Method 4: Hardcode in CDK App (Not Recommended)

```typescript
// In infrastructure/bin/daily-trade-stack.ts
new DailyTradeStack(app, "DailyTradeStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: "us-east-1", // Hardcoded - less flexible
  },
});
```

### Method 5: Use AWS Profile with Specific Region

```bash
# Set up a profile in ~/.aws/config
[profile daily-trade]
region = us-west-2
output = json

# Use the profile
export AWS_PROFILE=daily-trade
cdk deploy
```

## Recommended Setup for This Project

### Step 1: Configure AWS CLI

```bash
# Set your preferred region
aws configure set region us-east-1

# Verify
aws configure get region
```

### Step 2: Add to Your Shell Profile (Optional)
