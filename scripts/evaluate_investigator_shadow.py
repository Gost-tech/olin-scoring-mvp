"""Bounded synthetic evaluation. Prepare with operator custody; infer in env-i worker.

No model is downloaded or started. Reports are private research artifacts, not
canonical evidence or analyst comparison records. See PHASE5B_EVALUATION.md.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from functools import partial
from pathlib import Path
from uuid import UUID, uuid5

from olin.investigator_shadow import (
    CONTEXT_VERSION,
    OUTPUT_SCHEMA,
    PROMPT,
    PROMPT_VERSION,
    VERSION,
    canonical,
    digest,
    project,
    validate_output,
)
from olin.investigator_shadow_openai import HostedFailure, read_dedicated_credential
from olin.investigator_shadow_runner import Runner

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "tests/fixtures/shadow_evaluation_v1.json"
DATASET_SHA = "32978bf2c44fa0fe0eb35ec4c2c8ad35fcd3f336ad6c1e2052cb2701f5c5282c"
PROMPT_SHA = "ccba763aae3b8216fbd8100d8eea4234bc86ac4d990dda10599a04dc3be61d61"
SCHEMA_SHA = "3389c069351f8d3273d4114e44e8b50f5bfd3c1eb962a41a31705a8fcbb58843"
GAPS = {
    "period-mismatch": (
        "UNSUPPORTED_SETUP",
        "Closed operator has no period-mismatch fixture; baseline periods agree.",
    ),
    "scope-mismatch": (
        "UNSUPPORTED_SETUP",
        "Closed operator has no personal-versus-business scope fixture.",
    ),
    "duplicate-source": (
        "FILTERED_AT_INPUT_BOUNDARY",
        "Duplicate operator response adds no canonical evidence; response history is not projected.",
    ),
    "permission-missing": (
        "UNSUPPORTED_PROJECTION",
        "Permission for NEW acquisition is not represented; existing analysis consent is active, not missing.",
    ),
    "insufficient": (
        "UNSUPPORTED_SETUP",
        "Closed target fixture supplies admissible facts; no empty-case fixture supplied here.",
    ),
    "stop-limit": (
        "UNSUPPORTED_PROJECTION",
        "Administrative investigation limits are not projected into model context.",
    ),
    "prompt-injection": (
        "FILTERED_AT_INPUT_BOUNDARY",
        "Rubric free text is not admitted by the closed fixture/projection; no claim of model resistance.",
    ),
}


def frozen_dataset():
    import hashlib

    if (
        hashlib.sha256(DATASET.read_bytes()).hexdigest() != DATASET_SHA
        or digest(PROMPT) != PROMPT_SHA
        or digest(OUTPUT_SCHEMA) != SCHEMA_SHA
    ):
        raise ValueError(
            "first-evaluation versions changed; explicit new protocol required"
        )
    return json.loads(DATASET.read_text())


def configuration(mode, config):
    if mode == "dry-run":
        if config is not None:
            raise ValueError("dry run accepts no real configuration")
        return {"mode": "fake"}
    if (
        mode != "real"
        or not isinstance(config, dict)
        or config.get("mode") not in {"ollama", "openai"}
    ):
        raise ValueError(
            "real mode requires explicit local adapter approval/configuration"
        )
    Runner(config)  # Configuration validation only: no generation or network call.
    if (
        not isinstance(config["approval_reference"], str)
        or not config["approval_reference"].strip()
        or config["max_requests"] > 10
        or config["max_input_tokens"] != 16384
        or config["max_output_tokens"] != 1024
        or config["timeout_seconds"] != 30
    ):
        raise ValueError("first-run approval and frozen resource limits required")
    return dict(config)


def private_directory(path):
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("evaluation directory must be owned by this user, mode 0700")
    return path


def save_once(path, value):
    write_once(path, canonical(value) + "\n")


def write_once(path, text):
    # Publish only complete bytes; link is atomic and never overwrites a record.
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.unlink(temporary)  # Only this invocation's private temporary file.


def load_private(path):
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("private regular evaluation file required")
    return json.loads(path.read_text())


def candidate_sha():
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def binding_without_time(binding):
    return {k: v for k, v in binding.items() if k != "checked_at"}


def current_context(workflow, identity, case_id):
    record = workflow.current_analysis(identity, case_id)["reconstruction"]
    context, manifest = project(record)
    # These are closed development source profiles, never a caller trust label.
    for group in ("observed_values", "claimed_values", "coverage_diagnostics"):
        for value in record[group]:
            for ref in value.get("provenance", []):
                if ref["source_id"] not in {
                    "fixture_bank_registry",
                    "fixture_merchant_registry",
                }:
                    raise ValueError(
                        "non-fixture source excluded from synthetic evaluation"
                    )
    return context, record["input_assessment"], manifest


def representability(case, context):
    if case["id"] in GAPS:
        status, why = GAPS[case["id"]]
        return {"status": status, "model_observable": False, "reason": why}
    facts = context["facts"]
    coverage = {
        x.get("coverage_type"): x.get("status")
        for x in facts
        if x["kind"] == "coverage_diagnostics"
    }
    unknown = {x.get("quantity") for x in facts if x["kind"] == "unresolved_quantities"}
    observable = {
        "coverage-unknown": coverage.get("BANK_ACCOUNT_COVERAGE") == "UNKNOWN"
        and coverage.get("REVENUE_CHANNEL_COVERAGE") == "UNKNOWN",
        "account-complete": coverage.get("BANK_ACCOUNT_COVERAGE") == "COMPLETE"
        and coverage.get("REVENUE_CHANNEL_COVERAGE") == "UNKNOWN",
        "cost-debt-unknown": {"total_debt_service", "total_operating_costs"} <= unknown,
    }.get(case["id"], False)
    return {
        "status": "MODEL_VISIBLE" if observable else "PROJECTION_MISMATCH",
        "model_observable": observable,
        "reason": "Checked against actual authorized projection; no rubric text injected.",
    }


def prepare(operator, workflow, identity, namespace, directory):
    """Separate development operator operation; creates only existing closed fixtures."""
    directory = private_directory(directory)
    dataset = frozen_dataset()
    rows = []
    for case in dataset["cases"]:
        case_id = uuid5(namespace, case["id"])
        operator.setup_target_case(tenant_id=identity.tenant_id, case_id=case_id)
        if case["id"] == "account-complete":
            _, binding, _ = current_context(workflow, identity, case_id)
            # Fixed fixture setup identifier, NOT a performed human action.
            operator.useful_coverage(
                tenant_id=identity.tenant_id,
                case_id=case_id,
                action_id=uuid5(namespace, "coverage-setup"),
                expected_revision=binding["authority_revision"],
            )
        if case["id"] == "duplicate-source":
            operator.handle({"fixture": "duplicate_response"})
        row = {
            "rubric_id": case["id"],
            "case_id": str(case_id),
            "split": case["split"],
            "fixture": "phase5a-target"
            + ("+useful_coverage" if case["id"] == "account-complete" else ""),
            "human_selection": "NONE; setup is not a human comparison",
        }
        try:
            context, binding, manifest = current_context(workflow, identity, case_id)
            row.update(
                representability(case, context),
                binding=binding,
                context=context,
                input_digest=digest(context),
                reference_manifest=manifest,
            )
        except Exception as exc:  # noqa: BLE001 - fail closed; record class/code, never DB details
            row.update(
                status="AUTHORIZATION_REJECTED",
                model_observable=False,
                reason=getattr(exc, "code", type(exc).__name__),
            )
        rows.append(row)
    result = {
        "protocol": "shadow-evaluation-harness-1",
        "dataset": dataset["version"],
        "dataset_sha256": DATASET_SHA,
        "prompt_version": PROMPT_VERSION,
        "prompt_digest": PROMPT_SHA,
        "schema_version": VERSION,
        "schema_digest": SCHEMA_SHA,
        "context_version": CONTEXT_VERSION,
        "candidate_sha": candidate_sha(),
        "tenant_id": str(identity.tenant_id),
        "namespace": str(namespace),
        "cases": rows,
    }
    save_once(directory / "manifest.json", result)
    return result


def worker(payload):
    """Runs in a sanitized process. Receives config + minimized context ONLY."""
    raw = []
    known_usage = None
    failure_details = {}
    started = time.monotonic()
    runner = Runner(
        payload["config"],
        response_observer=lambda b: raw.append(base64.b64encode(b).decode()),
        credential_loader=(
            partial(read_dedicated_credential, payload.get("credential_file"))
            if payload["config"].get("mode") == "openai"
            else None
        ),
    )
    try:
        result = runner.generate(payload["context"])
        known_usage = result.get("usage")
        value = validate_output(result["proposal"], payload["context"])
        return {
            **result,
            "status": "VALID" if value["proposals"] else "ABSTAINED",
            "proposal_digest": digest(value),
            "raw_response_base64": raw,
        }
    except HostedFailure as exc:
        status = exc.status
        failure_details = exc.details
    except TimeoutError:
        status = "TIMEOUT_AMBIGUOUS"
    except (ValueError, KeyError, TypeError):
        status = "INVALID_OUTPUT"
    except OSError:
        status = "TRANSPORT_FAILURE_AMBIGUOUS"
    return {
        "status": status,
        "proposal": None,
        "raw_response_base64": raw,
        "latency_ms": round((time.monotonic() - started) * 1000),
        "usage": known_usage,
        "cost": None,
        "endpoint_computation_stopped": "UNKNOWN",
        "failure_details": failure_details,
    }


def isolated_attempt(config, context, *, credential_file=None):
    # No DB, canonical/action credentials, rubrics, human choices or artifacts.
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "scripts.evaluate_investigator_shadow",
                "worker",
            ],
            input=canonical(
                {
                    "config": config,
                    "context": context,
                    **(
                        {"credential_file": str(credential_file)}
                        if credential_file is not None
                        else {}
                    ),
                }
            ),
            text=True,
            capture_output=True,
            timeout=35,
            cwd=ROOT,
            env={
                "PATH": os.defpath,
                "PYTHONPATH": str(ROOT),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            check=False,
        )
        if completed.returncode != 0:
            return {"status": "TRANSPORT_FAILURE_AMBIGUOUS", "proposal": None}
        return json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT_AMBIGUOUS",
            "proposal": None,
            "endpoint_computation_stopped": "UNKNOWN",
        }


def evaluate(
    workflow, identity, directory, *, mode, config=None, attempt=isolated_attempt
):
    config = configuration(mode, config)
    frozen_dataset()
    directory = private_directory(directory)
    lock_fd = os.open(
        directory / "run.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(lock_fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _evaluate_locked(workflow, identity, directory, mode, config, attempt)


def hosted_stop_reason(config, result):
    if config.get("mode") != "openai":
        return None
    stops = {
        "AUTHENTICATION_FAILED",
        "ACCESS_DENIED",
        "BILLING_OR_QUOTA_BLOCKED",
        "RATE_LIMITED",
        "TRANSPORT_FAILURE_AMBIGUOUS",
        "TIMEOUT_AMBIGUOUS",
        "AMBIGUOUS",
        "REDACTED_PROVIDER_RESPONSE",
    }
    for field in ("generation_status", "status"):
        if result.get(field) in stops:
            return result[field]
    return None


def _evaluate_locked(workflow, identity, directory, mode, config, attempt):
    manifest = load_private(directory / "manifest.json")
    if (
        manifest["tenant_id"] != str(identity.tenant_id)
        or manifest["dataset_sha256"] != DATASET_SHA
    ):
        raise ValueError("evaluation manifest principal/version mismatch")
    run = {
        "mode": mode,
        "config": config,
        "candidate_sha": candidate_sha(),
        "manifest_digest": digest(manifest),
    }
    run_file = directory / "run.json"
    if run_file.exists():
        if load_private(run_file) != run:
            raise ValueError(
                "immutable run/configuration conflict; no automatic restart"
            )
    else:
        save_once(run_file, run)
    results = []
    attempted = 0
    expected_ids = [c["id"] for c in frozen_dataset()["cases"]]
    if [r["rubric_id"] for r in manifest["cases"]] != expected_ids:
        raise ValueError("frozen case list required")
    # Recover the stop BEFORE any new request. Receipt-only attempts are ambiguous.
    stop_reason = None
    for case in expected_ids:
        final = directory / (case + ".result.json")
        if final.exists():
            previous = load_private(final)
        elif (directory / (case + ".started.json")).exists():
            previous = {"status": "AMBIGUOUS"}
        else:
            continue
        stop_reason = stop_reason or hosted_stop_reason(config, previous)
    for row in manifest["cases"]:
        case = row["rubric_id"]
        start_path, final_path = (
            directory / (case + ".started.json"),
            directory / (case + ".result.json"),
        )
        if start_path.exists():
            attempted += 1
        if final_path.exists():
            results.append(
                load_private(final_path)
            )  # Historical result, never authority.
            continue
        result = {
            "rubric_id": case,
            "pipeline_status": row["status"],
            "attempted": False,
            "human_review": "NOT_REVIEWED",
            "investigation_outcome": "UNKNOWN",
            "input_digest": row.get("input_digest"),
            "status": "NOT_ATTEMPTED",
        }
        result.update(
            human_judgments={
                name: "NOT_REVIEWED"
                for name in (
                    "relevance",
                    "redundancy",
                    "usefulness",
                    "economic_interpretation",
                    "resolving_evidence",
                )
            },
            admissibility="NOT_CHECKED",
            model=config.get("model", "deterministic-fake-1"),
            provider=config["mode"],
            usage=None,
            latency_ms=None,
            cost=None,
        )
        if start_path.exists():
            result.update(
                attempted=True,
                status="AMBIGUOUS",
                endpoint_computation_stopped="UNKNOWN",
            )
        elif row["status"] == "MODEL_VISIBLE" and stop_reason:
            result.update(pipeline_status="RUN_STOPPED", stop_reason=stop_reason)
        elif row["status"] == "MODEL_VISIBLE":
            case_id = uuid5(UUID(manifest["namespace"]), case)
            if str(case_id) != row["case_id"]:
                raise ValueError("fixture identity mismatch")
            try:
                context, binding, _ = current_context(workflow, identity, case_id)
                rubric = next(c for c in frozen_dataset()["cases"] if c["id"] == case)
                if not representability(rubric, context)["model_observable"]:
                    raise ValueError("scenario not model-visible")
                if digest(context) != row["input_digest"] or binding_without_time(
                    binding
                ) != binding_without_time(row["binding"]):
                    raise ValueError("stale prepared context")
            except Exception as exc:  # noqa: BLE001 - denied/unavailable case never reaches worker
                result.update(
                    pipeline_status="AUTHORIZATION_REJECTED",
                    reason=getattr(exc, "code", type(exc).__name__),
                )
            else:
                limit = config.get("max_requests", 10)
                if attempted >= limit:
                    result.update(pipeline_status="REQUEST_LIMIT_REACHED")
                else:
                    save_once(
                        start_path,
                        {
                            "input_digest": digest(context),
                            "binding": binding,
                            "state": "STARTED",
                        },
                    )
                    attempted += 1
                    result.update(attempted=True)
                    try:
                        response = attempt(config, context)
                        result.update(response)
                        if result["status"] in {"VALID", "ABSTAINED"}:
                            # Independently validate even the isolated worker's envelope.
                            try:
                                validated = validate_output(result["proposal"], context)
                                result.update(
                                    admissibility="PASSED",
                                    proposal_digest=digest(validated),
                                )
                            except (ValueError, TypeError, KeyError):
                                result.update(
                                    status="INVALID_OUTPUT",
                                    proposal=None,
                                    admissibility="FAILED",
                                )
                    except Exception:  # noqa: BLE001 - receipt may outlive worker; never reinfer
                        result.update(status="AMBIGUOUS", proposal=None)
                    try:
                        fresh, fresh_binding, _ = current_context(
                            workflow, identity, case_id
                        )
                        if digest(fresh) != row["input_digest"] or binding_without_time(
                            fresh_binding
                        ) != binding_without_time(binding):
                            raise ValueError("changed context")
                    except Exception:  # noqa: BLE001 - any recheck failure excludes the result
                        result["generation_status"] = result["status"]
                        result["status"] = "STALE_CONTEXT_EXCLUDED"
        stop_reason = stop_reason or hosted_stop_reason(config, result)
        save_once(final_path, result)
        results.append(result)
    report = {
        "run": run,
        "dataset": manifest["dataset"],
        "results": results,
        "pipeline_cases": len(results),
        "attempted_cases": sum(r["attempted"] for r in results),
        "real_inference": "NOT_EXECUTED" if mode == "dry-run" else "ATTEMPTS_RECORDED",
        "limitations": "Fake is transport testing only; no human ratings or observed outcomes invented.",
    }
    report_file = directory / "report.json"
    if not report_file.exists():
        save_once(report_file, report)
    summary = {
        "mode": mode,
        "pipeline_cases": len(results),
        "attempted_cases": report["attempted_cases"],
        "cases": [
            {k: r[k] for k in ("rubric_id", "pipeline_status", "status", "attempted")}
            for r in results
        ],
    }
    if not (directory / "summary.json").exists():
        save_once(directory / "summary.json", summary)
    if not (directory / "summary.md").exists():
        write_once(
            directory / "summary.md",
            "# Synthetic shadow evaluation\n\n"
            + f"Mode: {mode}; attempted {report['attempted_cases']}/{len(results)} cases.\n"
            + "Fake results are not model intelligence. Human review: NOT_REVIEWED.\n\n"
            + "\n".join(
                f"- {r['rubric_id']}: {r['pipeline_status']} / {r['status']}"
                for r in results
            )
            + "\n\nUnperformed investigations: UNKNOWN. No credit-performance claim.\n",
        )
    return report


def connections(tenant):
    from olin.investigator_app import (
        AnalystIdentity,
        InvestigatorWorkflowService,
        _connect,
    )

    workflow = InvestigatorWorkflowService(
        runtime_connect=_connect("OLIN_INVESTIGATOR_DATABASE_URL"),
        canonical_connect=_connect("OLIN_INVESTIGATOR_CANONICAL_READER_DATABASE_URL"),
        action_connect=_connect("OLIN_INVESTIGATOR_ACTION_DATABASE_URL"),
    )
    return workflow, AnalystIdentity(
        "synthetic-evaluation-operator", UUID(tenant), "analyst"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "dry-run", "real", "worker"])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--tenant")
    parser.add_argument("--namespace", type=UUID)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--credential-file", type=Path)
    args = parser.parse_args()
    if args.operation == "worker":
        print(canonical(worker(json.loads(sys.stdin.read(64000)))))
        return
    config = None if args.config is None else json.loads(args.config.read_text())
    if args.operation != "prepare":
        configuration(args.operation, config)  # Refuse before DB setup or inference.
    if config and config.get("mode") == "openai":
        if args.credential_file is None or not args.credential_file.is_absolute():
            parser.error("hosted mode requires an absolute dedicated --credential-file")
    elif args.credential_file is not None:
        parser.error("credential file is permitted only for explicit hosted real mode")
    if not args.directory or not args.tenant:
        parser.error("--directory and --tenant required")
    workflow, identity = connections(args.tenant)
    if args.operation == "prepare":
        if args.namespace is None:
            parser.error("prepare requires --namespace UUID")
        from olin.investigator_synthetic_operator import (
            SyntheticEvidenceOperator,
            _connect,
        )

        operator = SyntheticEvidenceOperator(
            _connect("OLIN_SYNTHETIC_RUNTIME_DATABASE_URL"),
            _connect("OLIN_SYNTHETIC_EVIDENCE_AUTHORITY_DATABASE_URL"),
        )
        prepare(operator, workflow, identity, args.namespace, args.directory)
        print("Prepared private authorized manifest; no inference.")
    else:
        report = evaluate(
            workflow,
            identity,
            args.directory,
            mode=args.operation,
            config=config,
            attempt=partial(isolated_attempt, credential_file=args.credential_file),
        )
        print(
            f"{args.operation}: {report['attempted_cases']}/{report['pipeline_cases']} cases attempted; private report written."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - CLI must not print credentials from driver errors
        print("Evaluation refused/failed: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(2) from None
