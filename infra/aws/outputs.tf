output "database_endpoint" {
  value = aws_db_instance.olin.endpoint
}

output "database_master_secret_arn" {
  value     = aws_db_instance.olin.master_user_secret[0].secret_arn
  sensitive = true
}

output "kms_key_arn" {
  value = aws_kms_key.olin.arn
}

output "alert_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "application_url" {
  value = "https://${var.application_domain}"
}

output "load_balancer_dns_name" {
  value = aws_lb.olin.dns_name
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.olin.name
}

output "ecs_service_name" {
  value = aws_ecs_service.olin.name
}
