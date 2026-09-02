# Olin managed data infrastructure

This Terraform module defines the complete bank-shadow runtime: private AWS RDS PostgreSQL 16, a rotating KMS key, Secrets Manager-backed runtime configuration, ECS Fargate, an HTTPS Application Load Balancer, AWS WAF, rollback-on-failure deployments, private application tasks, CloudWatch logs and alarms, 14-day automated backups, deletion protection, Multi-AZ operation, PostgreSQL logs and Performance Insights.

It intentionally accepts an existing VPC, two or more private subnets, and the application security group. It does not create a public database or place credentials in Terraform variables.

## Activation

1. The bank/cloud owner creates a remote encrypted Terraform state and assumes an approved deployment role.
2. Build the Olin image in CI, scan it and set `application_image` to its immutable `@sha256:` digest.
3. Create one Secrets Manager JSON object containing the keys referenced by `application.tf`. Never use a `.tfvars` file for secret values.
4. Copy `terraform.tfvars.example` outside source control and replace the networking, certificate, domain and alert identifiers.
5. Confirm that the supplied application security group permits outbound TLS and PostgreSQL only as required.
6. Run `terraform init`, `terraform fmt -check`, `terraform validate`, and save `terraform plan` for approval.
7. Apply through the bank's CI/CD role, confirm the SNS subscription and map the approved DNS name to the load balancer.
8. Run the schema/migration step with the migration role, then run `python -m scripts.production_preflight` inside the task.
9. Perform a restore into an isolated subnet and store the ticket reference as `OLIN_BACKUP_RESTORE_EVIDENCE`.
10. Send one synthetic signed callback and require `/readyz` plus the audit event before enabling the first authorized real case.

The module has not been applied from this workstation. Creating cloud resources requires the bank's AWS account, deployment role, VPC/subnets, application security group, ACM certificate, DNS, Secrets Manager object, alert destination, approval and billing authority.
