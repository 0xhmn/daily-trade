import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as opensearch from "aws-cdk-lib/aws-opensearchservice";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as events from "aws-cdk-lib/aws-events";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as sns from "aws-cdk-lib/aws-sns";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";

/**
 * Single CloudFormation Stack containing ALL AWS resources for Daily Trade
 *
 * This stack includes:
 * - DynamoDB tables
 * - S3 buckets
 * - OpenSearch domain
 * - ECS Fargate cluster
 * - ECR repositories
 * - EventBridge rules
 * - CloudWatch logs and alarms
 * - SNS topics
 * - IAM roles and policies
 */
export class DailyTradeStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // =================================================================
    // DYNAMODB TABLES
    // =================================================================

    // Users Table
    const usersTable = new dynamodb.Table(this, "UsersTable", {
      partitionKey: { name: "userId", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      pointInTimeRecovery: true,
      tableName: "daily-trade-users",
    });

    // Watchlists Table
    const watchlistsTable = new dynamodb.Table(this, "WatchlistsTable", {
      partitionKey: { name: "userId", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "symbol", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      pointInTimeRecovery: true,
      tableName: "daily-trade-watchlists",
    });

    // GSI for querying: Get all stocks in a user's watchlist sorted by when they were added
    // Query pattern: userId = :userId AND addedAt BETWEEN :startTime AND :endTime
    watchlistsTable.addGlobalSecondaryIndex({
      indexName: "userId-addedAt-index",
      partitionKey: { name: "userId", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "addedAt", type: dynamodb.AttributeType.NUMBER },
    });

    // Risk Parameters Table
    const riskParametersTable = new dynamodb.Table(
      this,
      "RiskParametersTable",
      {
        partitionKey: { name: "userId", type: dynamodb.AttributeType.STRING },
        billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
        removalPolicy: cdk.RemovalPolicy.RETAIN,
        pointInTimeRecovery: true,
        tableName: "daily-trade-risk-parameters",
      }
    );

    // Trade Journal Table
    const tradeJournalTable = new dynamodb.Table(this, "TradeJournalTable", {
      partitionKey: { name: "userId", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "tradeId", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      pointInTimeRecovery: true,
      tableName: "daily-trade-trade-journal",
    });

    // GSI for querying: Get all trades for a user sorted by entry date
    // Query pattern: userId = :userId AND entryDate BETWEEN :startDate AND :endDate
    tradeJournalTable.addGlobalSecondaryIndex({
      indexName: "userId-entryDate-index",
      partitionKey: { name: "userId", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "entryDate", type: dynamodb.AttributeType.NUMBER },
    });

    // GSI for querying: Get all trades for a specific symbol sorted by entry date
    // Query pattern: symbol = :symbol AND entryDate BETWEEN :startDate AND :endDate
    tradeJournalTable.addGlobalSecondaryIndex({
      indexName: "symbol-entryDate-index",
      partitionKey: { name: "symbol", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "entryDate", type: dynamodb.AttributeType.NUMBER },
    });

    // Signal History Table
    const signalHistoryTable = new dynamodb.Table(this, "SignalHistoryTable", {
      partitionKey: { name: "signalId", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "timestamp", type: dynamodb.AttributeType.NUMBER },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      pointInTimeRecovery: true,
      tableName: "daily-trade-signal-history",
    });

    // GSI for querying: Get all signals for a user sorted by time
    // Query pattern: userId = :userId AND timestamp BETWEEN :startTime AND :endTime
    signalHistoryTable.addGlobalSecondaryIndex({
      indexName: "userId-timestamp-index",
      partitionKey: { name: "userId", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "timestamp", type: dynamodb.AttributeType.NUMBER },
    });

    // GSI for querying: Get all signals for a specific symbol sorted by time
    // Query pattern: symbol = :symbol AND timestamp BETWEEN :startTime AND :endTime
    signalHistoryTable.addGlobalSecondaryIndex({
      indexName: "symbol-timestamp-index",
      partitionKey: { name: "symbol", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "timestamp", type: dynamodb.AttributeType.NUMBER },
    });

    // =================================================================
    // S3 BUCKETS
    // =================================================================

    // Documents Bucket
    const documentsBucket = new s3.Bucket(this, "DocumentsBucket", {
      bucketName: `daily-trade-documents-${cdk.Aws.ACCOUNT_ID}`,
      versioned: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      lifecycleRules: [
        {
          transitions: [
            {
              storageClass: s3.StorageClass.GLACIER,
              transitionAfter: cdk.Duration.days(90),
            },
          ],
        },
      ],
    });

    // Embeddings Bucket
    const embeddingsBucket = new s3.Bucket(this, "EmbeddingsBucket", {
      bucketName: `daily-trade-embeddings-${cdk.Aws.ACCOUNT_ID}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // Market Data Bucket
    const marketDataBucket = new s3.Bucket(this, "MarketDataBucket", {
      bucketName: `daily-trade-market-data-${cdk.Aws.ACCOUNT_ID}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // Images Bucket
    const imagesBucket = new s3.Bucket(this, "ImagesBucket", {
      bucketName: `daily-trade-images-${cdk.Aws.ACCOUNT_ID}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      cors: [
        {
          allowedMethods: [s3.HttpMethods.GET, s3.HttpMethods.PUT],
          allowedOrigins: ["*"],
          allowedHeaders: ["*"],
        },
      ],
    });

    // Logs Bucket
    const logsBucket = new s3.Bucket(this, "LogsBucket", {
      bucketName: `daily-trade-logs-${cdk.Aws.ACCOUNT_ID}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      lifecycleRules: [
        {
          expiration: cdk.Duration.days(30),
        },
      ],
    });

    // =================================================================
    // ECS CLUSTER
    // =================================================================

    const cluster = new ecs.Cluster(this, "DailyTradeCluster", {
      clusterName: "daily-trade-cluster",
      containerInsights: true,
    });

    // ECR Repositories
    const backendRepo = new ecr.Repository(this, "BackendRepository", {
      repositoryName: "daily-trade-backend",
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      imageScanOnPush: true,
    });

    const analyzerRepo = new ecr.Repository(this, "AnalyzerRepository", {
      repositoryName: "daily-trade-analyzer",
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      imageScanOnPush: true,
    });

    // Task Execution Role
    const taskExecutionRole = new iam.Role(this, "EcsTaskExecutionRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AmazonECSTaskExecutionRolePolicy"
        ),
      ],
    });

    // Task Role (for application permissions)
    const taskRole = new iam.Role(this, "EcsTaskRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
    });

    // Grant permissions to task role
    usersTable.grantReadWriteData(taskRole);
    watchlistsTable.grantReadWriteData(taskRole);
    riskParametersTable.grantReadWriteData(taskRole);
    tradeJournalTable.grantReadWriteData(taskRole);
    signalHistoryTable.grantReadWriteData(taskRole);
    documentsBucket.grantReadWrite(taskRole);
    embeddingsBucket.grantReadWrite(taskRole);
    marketDataBucket.grantReadWrite(taskRole);
    imagesBucket.grantReadWrite(taskRole);

    // Grant Bedrock permissions
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ],
        resources: ["*"],
      })
    );

    // =================================================================
    // OPENSEARCH DOMAIN
    // =================================================================

    // Role for local development access to OpenSearch
    const localOpenSearchRole = new iam.Role(
      this,
      "LocalOpenSearchAccessRole",
      {
        roleName: "DailyTradeLocalOpenSearchAccess",
        description: "Role for local development access to OpenSearch domain",
        assumedBy: new iam.AccountPrincipal(cdk.Aws.ACCOUNT_ID),
        maxSessionDuration: cdk.Duration.hours(12),
      }
    );

    // OpenSearch Log Groups
    const openSearchSearchSlowLogGroup = new logs.LogGroup(
      this,
      "OpenSearchSearchSlowLogGroup",
      {
        logGroupName:
          "/aws/opensearch/domains/daily-trade-knowledge-001/search-slow-logs",
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }
    );

    const openSearchIndexSlowLogGroup = new logs.LogGroup(
      this,
      "OpenSearchIndexSlowLogGroup",
      {
        logGroupName:
          "/aws/opensearch/domains/daily-trade-knowledge-001/index-slow-logs",
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }
    );

    const openSearchErrorLogGroup = new logs.LogGroup(
      this,
      "OpenSearchErrorLogGroup",
      {
        logGroupName:
          "/aws/opensearch/domains/daily-trade-knowledge-001/error-logs",
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }
    );

    // OpenSearch domain with access policy including both roles
    const openSearchDomain = new opensearch.Domain(this, "OpenSearchDomain", {
      version: opensearch.EngineVersion.OPENSEARCH_3_1,
      domainName: "daily-trade-knowledge-001",
      capacity: {
        dataNodes: 2,
        dataNodeInstanceType: "t3.small.search",
        multiAzWithStandbyEnabled: false,
      },
      ebs: {
        volumeSize: 100,
        volumeType: ec2.EbsDeviceVolumeType.GP3,
      },
      zoneAwareness: {
        enabled: false,
      },
      enforceHttps: true,
      nodeToNodeEncryption: true,
      encryptionAtRest: {
        enabled: true,
      },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      logging: {
        slowSearchLogEnabled: true,
        slowSearchLogGroup: openSearchSearchSlowLogGroup,
        slowIndexLogEnabled: true,
        slowIndexLogGroup: openSearchIndexSlowLogGroup,
        appLogEnabled: true,
        appLogGroup: openSearchErrorLogGroup,
      },
      accessPolicies: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          principals: [
            new iam.ArnPrincipal(localOpenSearchRole.roleArn),
            new iam.ArnPrincipal(taskRole.roleArn),
          ],
          actions: ["es:*"],
          resources: [
            `arn:aws:es:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:domain/daily-trade-knowledge-001/*`,
          ],
        }),
      ],
    });

    // Grant OpenSearch permissions
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "es:ESHttpGet",
          "es:ESHttpPut",
          "es:ESHttpPost",
          "es:ESHttpDelete",
        ],
        resources: [`${openSearchDomain.domainArn}/*`],
      })
    );

    localOpenSearchRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "es:ESHttpGet",
          "es:ESHttpPut",
          "es:ESHttpPost",
          "es:ESHttpDelete",
          "es:ESHttpHead",
        ],
        resources: [`${openSearchDomain.domainArn}/*`],
      })
    );

    localOpenSearchRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ],
        resources: ["*"],
      })
    );

    documentsBucket.grantReadWrite(localOpenSearchRole);
    embeddingsBucket.grantReadWrite(localOpenSearchRole);
    imagesBucket.grantReadWrite(localOpenSearchRole);

    // CloudWatch Logs
    const logGroup = new logs.LogGroup(this, "ApplicationLogGroup", {
      logGroupName: "/ecs/daily-trade",
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // =================================================================
    // SNS TOPIC FOR NOTIFICATIONS
    // =================================================================

    const notificationTopic = new sns.Topic(this, "NotificationTopic", {
      topicName: "daily-trade-notifications",
      displayName: "Daily Trade Signal Notifications",
    });

    // =================================================================
    // EVENTBRIDGE RULES
    // =================================================================

    // Daily Analysis Rule (4 PM ET = 9 PM UTC)
    const dailyAnalysisRule = new events.Rule(this, "DailyAnalysisRule", {
      ruleName: "daily-trade-analysis",
      schedule: events.Schedule.cron({
        minute: "0",
        hour: "21",
        weekDay: "MON-FRI",
      }),
      description: "Trigger daily trading signal analysis",
    });

    // Data Refresh Rule (3:30 PM ET = 8:30 PM UTC)
    const dataRefreshRule = new events.Rule(this, "DataRefreshRule", {
      ruleName: "market-data-refresh",
      schedule: events.Schedule.cron({
        minute: "30",
        hour: "20",
        weekDay: "MON-FRI",
      }),
      description: "Refresh market data cache",
    });

    // =================================================================
    // CLOUDWATCH ALARMS
    // =================================================================

    // OpenSearch cluster health alarm
    new cloudwatch.Alarm(this, "OpenSearchHealthAlarm", {
      alarmName: "daily-trade-opensearch-health",
      metric: openSearchDomain.metricClusterStatusRed(),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator:
        cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    // =================================================================
    // OUTPUTS
    // =================================================================

    new cdk.CfnOutput(this, "ClusterName", {
      value: cluster.clusterName,
      description: "ECS Cluster Name",
    });

    new cdk.CfnOutput(this, "OpenSearchEndpoint", {
      value: openSearchDomain.domainEndpoint,
      description: "OpenSearch Domain Endpoint",
      exportName: "DailyTradeOpenSearchEndpoint",
    });

    new cdk.CfnOutput(this, "OpenSearchDomainArn", {
      value: openSearchDomain.domainArn,
      description: "OpenSearch Domain ARN",
    });

    new cdk.CfnOutput(this, "DocumentsBucketName", {
      value: documentsBucket.bucketName,
      description: "Documents S3 Bucket",
      exportName: "DailyTradeDocumentsBucket",
    });

    new cdk.CfnOutput(this, "EmbeddingsBucketName", {
      value: embeddingsBucket.bucketName,
      description: "Embeddings S3 Bucket",
    });

    new cdk.CfnOutput(this, "MarketDataBucketName", {
      value: marketDataBucket.bucketName,
      description: "Market Data S3 Bucket",
    });

    new cdk.CfnOutput(this, "ImagesBucketName", {
      value: imagesBucket.bucketName,
      description: "Images S3 Bucket",
      exportName: "DailyTradeImagesBucket",
    });

    new cdk.CfnOutput(this, "BackendRepositoryUri", {
      value: backendRepo.repositoryUri,
      description: "Backend ECR Repository URI",
    });

    new cdk.CfnOutput(this, "AnalyzerRepositoryUri", {
      value: analyzerRepo.repositoryUri,
      description: "Analyzer ECR Repository URI",
    });

    new cdk.CfnOutput(this, "TaskRoleArn", {
      value: taskRole.roleArn,
      description: "ECS Task Role ARN",
    });

    new cdk.CfnOutput(this, "NotificationTopicArn", {
      value: notificationTopic.topicArn,
      description: "SNS Topic ARN for notifications",
    });

    new cdk.CfnOutput(this, "DynamoDBTablesPrefix", {
      value: "daily-trade-",
      description: "DynamoDB Tables Prefix",
    });

    new cdk.CfnOutput(this, "LocalOpenSearchRoleArn", {
      value: localOpenSearchRole.roleArn,
      description: "ARN of the IAM role for local OpenSearch access",
      exportName: "DailyTradeLocalOpenSearchRoleArn",
    });
  }
}
