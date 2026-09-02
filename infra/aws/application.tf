locals {
  application_port = 8080
  secret_keys = toset([
    "OLIN_DATABASE_URL",
    "OLIN_USERS",
    "OLIN_BANK_WEBHOOK_SECRETS",
    "OLIN_CONSENT_OTP_SECRET",
    "OLIN_SESSION_SECRET",
    "OLIN_KMS_KEY_ID",
    "OLIN_BACKUP_RESTORE_EVIDENCE",
    "OLIN_REAL_DATA_SCOPE_REF",
    "OLIN_DATA_PROCESSING_APPROVAL_REF",
    "OLIN_INCIDENT_OWNER",
    "OLIN_INCIDENT_CONTACT",
  ])
}

resource "aws_security_group" "load_balancer" {
  name        = "olin-${var.environment}-alb"
  description = "TLS ingress for the Olin bank shadow service"
  vpc_id      = var.vpc_id

  dynamic "ingress" {
    for_each = var.allowed_ingress_cidrs
    content {
      description = "Approved bank or operator network"
      protocol    = "tcp"
      from_port   = 443
      to_port     = 443
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    description     = "Application health and API traffic"
    protocol        = "tcp"
    from_port       = local.application_port
    to_port         = local.application_port
    security_groups = [var.application_security_group_id]
  }
}

resource "aws_vpc_security_group_ingress_rule" "application_from_alb" {
  security_group_id            = var.application_security_group_id
  referenced_security_group_id = aws_security_group.load_balancer.id
  from_port                    = local.application_port
  to_port                      = local.application_port
  ip_protocol                  = "tcp"
  description                  = "Only the Olin ALB may reach the application"
}

resource "aws_cloudwatch_log_group" "application" {
  name              = "/olin/${var.environment}/application"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.olin.arn
}

resource "aws_ecs_cluster" "olin" {
  name = "olin-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_iam_role" "task_execution" {
  name = "olin-${var.environment}-task-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "task_secrets" {
  name = "runtime-secret-read"
  role = aws_iam_role.task_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [var.application_secrets_arn]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = [aws_kms_key.olin.arn]
      }
    ]
  })
}

resource "aws_iam_role" "application_task" {
  name = "olin-${var.environment}-application"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_ecs_task_definition" "olin" {
  family                   = "olin-${var.environment}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.application_task.arn

  container_definitions = jsonencode([{
    name                   = "olin"
    image                  = var.application_image
    essential              = true
    readonlyRootFilesystem = true
    user                   = "olin"
    portMappings = [{
      containerPort = local.application_port
      hostPort      = local.application_port
      protocol      = "tcp"
    }]
    environment = [
      { name = "OLIN_MODE", value = "production" },
      { name = "OLIN_REAL_DATA_ENABLED", value = "1" },
      { name = "OLIN_DATABASE_ENCRYPTION_AT_REST", value = "attested" },
      { name = "OLIN_DATABASE_TLS_ATTESTED", value = "attested" },
      { name = "OLIN_PUBLIC_BASE_URL", value = "https://${var.application_domain}" },
      { name = "OLIN_DATA_CLASSIFICATION", value = var.data_classification },
      { name = "OLIN_RETENTION_DAYS", value = tostring(var.retention_days) },
      { name = "OLIN_REQUIRE_TRUST_REGISTRY", value = "1" },
      { name = "OLIN_TRUSTED_SOURCE_REGISTRY_FILE", value = "config/trusted-sources.example.json" },
      { name = "OLIN_LIVE_LENDING_ENABLED", value = "0" },
      { name = "OLIN_LIVE_LENDING_KILL_SWITCH", value = "1" },
      { name = "OLIN_REQUIRE_SHORT_LIVED_SESSIONS", value = "1" },
      { name = "OLIN_SESSION_TTL_MINUTES", value = "15" },
      { name = "OLIN_CONSENT_OTP_MODE", value = var.consent_otp_mode },
    ]
    secrets = [for key in local.secret_keys : {
      name      = key
      valueFrom = "${var.application_secrets_arn}:${key}::"
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.application.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "olin"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "python3 -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=2)\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 20
    }
  }])
}

resource "aws_lb" "olin" {
  name               = "olin-${var.environment}"
  internal           = var.internal_load_balancer
  load_balancer_type = "application"
  security_groups    = [aws_security_group.load_balancer.id]
  subnets            = var.load_balancer_subnet_ids
  enable_deletion_protection = true
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "olin" {
  name        = "olin-${var.environment}"
  port        = local.application_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    path                = "/readyz"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.olin.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.olin.arn
  }
}

resource "aws_ecs_service" "olin" {
  name            = "olin-${var.environment}"
  cluster         = aws_ecs_cluster.olin.id
  task_definition = aws_ecs_task_definition.olin.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  platform_version = "1.4.0"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.application_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.olin.arn
    container_name   = "olin"
    container_port   = local.application_port
  }

  depends_on = [aws_lb_listener.https]
}

resource "aws_wafv2_web_acl" "olin" {
  name  = "olin-${var.environment}"
  scope = "REGIONAL"

  default_action { allow {} }

  rule {
    name     = "aws-common-rules"
    priority = 10
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "olin-common-rules"
      sampled_requests_enabled   = false
    }
  }

  rule {
    name     = "rate-limit"
    priority = 20
    action { block {} }
    statement {
      rate_based_statement {
        limit              = var.waf_requests_per_five_minutes
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "olin-rate-limit"
      sampled_requests_enabled   = false
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "olin-${var.environment}"
    sampled_requests_enabled   = false
  }
}

resource "aws_wafv2_web_acl_association" "olin" {
  resource_arn = aws_lb.olin.arn
  web_acl_arn  = aws_wafv2_web_acl.olin.arn
}

resource "aws_cloudwatch_metric_alarm" "application_unhealthy" {
  alarm_name          = "olin-${var.environment}-unhealthy-targets"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  dimensions = {
    LoadBalancer = aws_lb.olin.arn_suffix
    TargetGroup  = aws_lb_target_group.olin.arn_suffix
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "application_errors" {
  alarm_name          = "olin-${var.environment}-http-5xx"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  dimensions = { LoadBalancer = aws_lb.olin.arn_suffix }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}
