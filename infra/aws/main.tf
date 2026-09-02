resource "aws_kms_key" "olin" {
  description             = "Olin bank-shadow database and backup encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "olin" {
  name          = "alias/olin-${var.environment}"
  target_key_id = aws_kms_key.olin.key_id
}

resource "aws_db_subnet_group" "olin" {
  name       = "olin-${var.environment}"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "database" {
  name        = "olin-${var.environment}-postgres"
  description = "PostgreSQL reachable only from the Olin application security group"
  vpc_id      = var.vpc_id

  ingress {
    protocol        = "tcp"
    from_port       = 5432
    to_port         = 5432
    security_groups = [var.application_security_group_id]
  }

}

resource "aws_db_instance" "olin" {
  identifier                     = "olin-${var.environment}"
  engine                         = "postgres"
  engine_version                 = "16"
  instance_class                 = var.instance_class
  allocated_storage              = 20
  max_allocated_storage          = 100
  storage_type                   = "gp3"
  storage_encrypted              = true
  kms_key_id                     = aws_kms_key.olin.arn
  db_name                        = var.database_name
  username                       = var.database_username
  manage_master_user_password    = true
  db_subnet_group_name           = aws_db_subnet_group.olin.name
  vpc_security_group_ids         = [aws_security_group.database.id]
  publicly_accessible            = false
  multi_az                       = var.multi_az
  backup_retention_period        = 14
  backup_window                  = "08:00-09:00"
  maintenance_window             = "sun:09:00-sun:10:00"
  deletion_protection            = true
  skip_final_snapshot            = false
  final_snapshot_identifier      = "olin-${var.environment}-final"
  copy_tags_to_snapshot          = true
  auto_minor_version_upgrade     = true
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  performance_insights_enabled   = true
  performance_insights_kms_key_id = aws_kms_key.olin.arn
  apply_immediately              = false
}

resource "aws_sns_topic" "alerts" {
  name              = "olin-${var.environment}-alerts"
  kms_master_key_id = aws_kms_key.olin.id
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "cpu" {
  alarm_name          = "olin-${var.environment}-database-high-cpu"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.olin.id }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "storage" {
  alarm_name          = "olin-${var.environment}-database-low-storage"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 5368709120
  comparison_operator = "LessThanThreshold"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.olin.id }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "connections" {
  alarm_name          = "olin-${var.environment}-database-connections"
  namespace           = "AWS/RDS"
  metric_name         = "DatabaseConnections"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.olin.id }
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
