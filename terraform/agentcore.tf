# ── IAM Role for Agentcore Runtime ──────────────────────────────────

resource "aws_iam_role" "agentcore" {
  name = "${local.name_prefix}-agentcore-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = [
            "bedrock.amazonaws.com",
            "ecs-tasks.amazonaws.com",
          ]
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "agentcore_permissions" {
  name = "${local.name_prefix}-agentcore-policy"
  role = aws_iam_role.agentcore.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockAccess"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ]
        Resource = "arn:aws:bedrock:${var.region}::foundation-model/*"
      },
      {
        Sid    = "S3Access"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.documents.arn,
          "${aws_s3_bucket.documents.arn}/*",
        ]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Sid    = "CognitoReadOnly"
        Effect = "Allow"
        Action = [
          "cognito-idp:GetUser",
          "cognito-idp:AdminGetUser",
        ]
        Resource = aws_cognito_user_pool.main.arn
      },
      {
        Sid    = "ECRPull"
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:GetAuthorizationToken",
        ]
        Resource = "*"
      },
    ]
  })
}

# ── S3 Bucket for documents / knowledge base ──────────────────────

resource "aws_s3_bucket" "documents" {
  bucket = "${local.name_prefix}-documents-${data.aws_caller_identity.current.account_id}"
  tags   = local.common_tags
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ── CloudWatch Log Group ───────────────────────────────────────────

resource "aws_cloudwatch_log_group" "agentcore" {
  name              = "/aws/agentcore/${local.name_prefix}"
  retention_in_days = 30
  tags              = local.common_tags
}

# ── VPC & Security Group ──────────────────────────────────────────

resource "aws_default_vpc" "default" {}

resource "aws_security_group" "agentcore" {
  name        = "${local.name_prefix}-agentcore-sg"
  description = "Security group for Agentcore FastAPI runtime"
  vpc_id      = aws_default_vpc.default.id

  ingress {
    description = "FastAPI HTTP"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

# ── ECS Cluster (Agentcore runtime host) ──────────────────────────

resource "aws_ecs_cluster" "agentcore" {
  name = "${local.name_prefix}-agentcore"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.common_tags
}

# ── ECS Task Definition (FastAPI container on Agentcore) ──────────

resource "aws_ecs_task_definition" "agent" {
  family                   = "${local.name_prefix}-agent"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.agentcore.arn
  task_role_arn            = aws_iam_role.agentcore.arn

  container_definitions = jsonencode([
    {
      name      = "stock-agent"
      image     = var.api_container_image
      essential = true

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "AWS_REGION", value = var.region },
        { name = "COGNITO_USER_POOL_ID", value = aws_cognito_user_pool.main.id },
        { name = "COGNITO_CLIENT_ID", value = aws_cognito_user_pool_client.app.id },
        { name = "BEDROCK_MODEL_ID", value = "anthropic.claude-sonnet-4-20250514" },
        { name = "APP_ENV", value = var.environment },
        { name = "LOG_LEVEL", value = "INFO" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.agentcore.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "agent"
        }
      }
    }
  ])

  tags = local.common_tags
}

# ── ECS Service ───────────────────────────────────────────────────

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [aws_default_vpc.default.id]
  }
}

resource "aws_ecs_service" "agent" {
  name            = "${local.name_prefix}-agent-svc"
  cluster         = aws_ecs_cluster.agentcore.id
  task_definition = aws_ecs_task_definition.agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.agentcore.id]
    assign_public_ip = true
  }

  tags = local.common_tags
}
