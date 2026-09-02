"""Static safety contract for the managed AWS database definition."""
from pathlib import Path
import unittest


class InfrastructureContractTests(unittest.TestCase):
    def test_rds_is_private_encrypted_backed_up_and_monitored(self):
        source = Path("infra/aws/main.tf").read_text(encoding="utf-8")
        for required in (
            'engine                         = "postgres"',
            "storage_encrypted              = true",
            "publicly_accessible            = false",
            "backup_retention_period        = 14",
            "deletion_protection            = true",
            "manage_master_user_password    = true",
            "enable_key_rotation     = true",
            'metric_name         = "CPUUtilization"',
            'metric_name         = "FreeStorageSpace"',
            'metric_name         = "DatabaseConnections"',
        ):
            self.assertIn(required, source)

    def test_application_runtime_has_tls_rollback_waf_and_readiness(self):
        source = Path("infra/aws/application.tf").read_text(encoding="utf-8")
        for required in (
            'requires_compatibilities = ["FARGATE"]',
            "readonlyRootFilesystem = true",
            'protocol          = "HTTPS"',
            'path                = "/readyz"',
            "deployment_circuit_breaker",
            "rollback = true",
            'name        = "AWSManagedRulesCommonRuleSet"',
            "rate_based_statement",
            'assign_public_ip = false',
            "application_secrets_arn",
            'value = "0" },',
        ):
            self.assertIn(required, source)

    def test_container_uses_runtime_database_target_and_readiness_probe(self):
        source = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("/data/olin_scoring.db", source)
        self.assertIn("/readyz", source)


if __name__ == "__main__":
    unittest.main()
