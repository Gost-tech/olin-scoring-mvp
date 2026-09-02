variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "bank-shadow"
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "application_security_group_id" {
  type = string
}

variable "alert_email" {
  type = string
}

variable "database_name" {
  type    = string
  default = "olin"
}

variable "database_username" {
  type    = string
  default = "olin_runtime"
}

variable "instance_class" {
  type    = string
  default = "db.t4g.small"
}

variable "multi_az" {
  type    = bool
  default = true
}
variable "application_image" {
  type        = string
  description = "Immutable Olin container image digest, for example ECR repo@sha256:..."
  validation {
    condition     = strcontains(var.application_image, "@sha256:")
    error_message = "application_image must be pinned to an immutable sha256 digest."
  }
}
variable "application_secrets_arn" {
  type        = string
  description = "Secrets Manager JSON object containing the Olin runtime values"
}
variable "application_domain" {
  type = string
}

variable "certificate_arn" {
  type = string
}

variable "load_balancer_subnet_ids" {
  type = list(string)
}

variable "allowed_ingress_cidrs" {
  type    = list(string)
  default = []
}

variable "internal_load_balancer" {
  type    = bool
  default = true
}
variable "data_classification" {
  type    = string
  default = "pseudonymized_historical"
  validation {
    condition = contains([
      "pseudonymized_historical", "identifiable_historical", "prospective"
    ], var.data_classification)
    error_message = "Use a supported Olin data classification."
  }
}
variable "consent_otp_mode" {
  type    = string
  default = "bank_approved_adapter"
}
variable "retention_days" {
  type    = number
  default = 45
  validation {
    condition     = var.retention_days >= 1 && var.retention_days <= 365
    error_message = "retention_days must be between 1 and 365."
  }
}
variable "log_retention_days" {
  type    = number
  default = 90
}

variable "task_cpu" {
  type    = number
  default = 512
}

variable "task_memory" {
  type    = number
  default = 1024
}

variable "desired_count" {
  type    = number
  default = 2
}

variable "waf_requests_per_five_minutes" {
  type    = number
  default = 2000
}
