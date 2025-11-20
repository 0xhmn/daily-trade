"""
AWS Credentials Helper

Handles credential management based on STAGE environment variable:
- STAGE=local: Assumes specified role (required)
- STAGE=prod: Uses default credentials (task role in ECS/Fargate)

Default: STAGE=local
"""

import logging
import os
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def get_credentials_for_opensearch(
    region: str = "us-east-1", local_role_arn: Optional[str] = None
) -> boto3.Session:
    """
    Get appropriate AWS credentials based on STAGE environment variable.

    STAGE=local (default): Assumes the specified role (throws if not provided)
    STAGE=prod: Uses default credentials (task role in deployed environment)

    Args:
        region: AWS region
        local_role_arn: ARN of role to assume when STAGE=local (required for local)

    Returns:
        boto3.Session with appropriate credentials

    Raises:
        ValueError: If STAGE=local but no role ARN provided, or if role assumption fails
    """
    stage = os.getenv("STAGE", "local").lower()

    if stage == "local":
        # Local development - role assumption required
        if not local_role_arn:
            raise ValueError(
                "STAGE=local requires local_role_arn parameter. "
                "Pass the IAM role ARN for local OpenSearch access. "
                "Get it from CDK outputs: LocalOpenSearchRoleArn"
            )

        logger.info(f"STAGE=local - Assuming role for local development")
        return _assume_role(local_role_arn, region)

    else:
        # Production - use default credentials (task role)
        logger.info(f"STAGE={stage} - Using default credentials (task role)")
        return boto3.Session(region_name=region)


def _assume_role(role_arn: str, region: str) -> boto3.Session:
    """
    Assume an IAM role and return session with temporary credentials.

    Args:
        role_arn: ARN of the role to assume
        region: AWS region

    Returns:
        boto3.Session with assumed role credentials

    Raises:
        ValueError: If role assumption fails
    """
    try:
        # Create STS client with default credentials
        sts_client = boto3.client("sts", region_name=region)

        # Assume the role
        logger.info(f"Assuming role: {role_arn}")
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=f"local-dev-{os.getpid()}",
            DurationSeconds=3600,  # 1hr limit
        )

        credentials = response["Credentials"]

        logger.info("Successfully assumed role")
        logger.info(f"Credentials expire at: {credentials['Expiration']}")

        # Create session with assumed role credentials
        session = boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=region,
        )

        # Verify the assumed identity
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        logger.info(f"Using identity: {identity['Arn']}")

        return session

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")

        if error_code == "AccessDenied":
            raise ValueError(
                f"Access denied when assuming role {role_arn}.\n"
                "Make sure:\n"
                "1. Your IAM user has sts:AssumeRole permission\n"
                "2. The role's trust policy allows your IAM user to assume it\n"
                "3. The CDK stack has been deployed (cd infrastructure && cdk deploy)"
            ) from e
        else:
            raise ValueError(f"Failed to assume role {role_arn}: {e}") from e


def get_stage() -> str:
    """Get the current stage from environment variable. Defaults to 'local'."""
    return os.getenv("STAGE", "local").lower()


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    stage = get_stage()
    print(f"Current STAGE: {stage}")

    if stage == "local":
        # For local testing, provide role ARN
        role_arn = os.getenv("OPENSEARCH_ROLE_ARN")
        if not role_arn:
            print("Error: STAGE=local requires OPENSEARCH_ROLE_ARN environment variable")
            print("Set it to: arn:aws:iam::ACCOUNT_ID:role/DailyTradeLocalOpenSearchAccess")
        else:
            try:
                session = get_credentials_for_opensearch(
                    region="us-east-1", local_role_arn=role_arn
                )
                print("Successfully configured credentials for local development")
            except Exception as e:
                print(f"Error: {e}")
    else:
        session = get_credentials_for_opensearch(region="us-east-1")
        print("Using production credentials")
