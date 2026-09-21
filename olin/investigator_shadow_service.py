"""Trusted research coordinator; inference is outside all database transactions."""

from __future__ import annotations

import http.client
import json
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid4, uuid5

from .investigator_app import InvestigatorAppError
from .investigator_shadow import (
    OUTPUT_SCHEMA,
    PROMPT,
    PROMPT_VERSION,
    assess_applicability,
    canonical,
    digest,
    project,
    validate_output,
)


class ShadowTransport:
    def __init__(
        self, url: str, token: str, *, provider="fake", model="deterministic-fake-1"
    ):
        target = urlparse(url)
        if (
            target.scheme != "http"
            or target.hostname != "127.0.0.1"
            or target.path not in ("", "/")
            or target.query
            or target.fragment
            or target.username
        ):
            raise ValueError("isolated loopback runner required")
        if len(token) < 24:
            raise ValueError("dedicated runner token required")
        self.port = target.port or 8087
        self.token = token
        if provider not in {"fake", "ollama", "openai"} or not model:
            raise ValueError("explicit runner identity required")
        self.mode, self.model = provider, model

    def generate(self, context: dict) -> dict:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=35)
        try:
            connection.request(
                "POST",
                "/generate",
                body=canonical(context),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + self.token,
                },
            )
            response = connection.getresponse()
            data = response.read(16001)
            if response.status != 200 or len(data) > 16000:
                raise ValueError("runner response invalid")
            return json.loads(data)
        finally:
            connection.close()


class ShadowResearchService:
    def __init__(self, workflow, research_connect, runner, *, synthetic_cases):
        self.workflow = workflow
        self.connect = research_connect
        self.runner = runner
        self.synthetic_cases = frozenset(str(c) for c in synthetic_cases)

    def _call(self, identity, case_id, round_id, op=None, payload=None, key=""):
        if identity.role != "analyst" or str(case_id) not in self.synthetic_cases:
            raise InvestigatorAppError(
                404, "RESEARCH_UNAVAILABLE", "Synthetic research unavailable"
            )
        with closing(self.connect()) as connection, connection.transaction():
            connection.execute("SET LOCAL ROLE olin_investigator_research")
            connection.execute("SET LOCAL statement_timeout='5s'")
            connection.execute("SET LOCAL lock_timeout='1s'")
            connection.execute(
                "SELECT set_config('olin.tenant_id',%s,true)",
                (str(identity.tenant_id),),
            )
            args = (identity.tenant_id, case_id, round_id, identity.name)
            if op is None:
                result = connection.execute(
                    "SELECT investigator.shadow_read(%s,%s,%s,%s)", args
                ).fetchone()[0]
            else:
                result = connection.execute(
                    "SELECT investigator.shadow_command(%s,%s,%s,%s,%s,%s::jsonb,%s)",
                    (*args, op, canonical(payload), key),
                ).fetchone()[0]
        if result is None:
            raise InvestigatorAppError(
                404, "ROUND_NOT_FOUND", "Research round not found"
            )
        return result

    @staticmethod
    def _event(record, kind):
        return next((e for e in record["events"] if e["kind"] == kind), None)

    def create(self, identity, case_id, key):
        if not isinstance(key, str) or not 1 <= len(key) <= 120:
            raise ValueError("bounded request key required")
        round_id = uuid5(
            NAMESPACE_URL,
            f"shadow:{identity.tenant_id}:{case_id}:{identity.name}:{key}",
        )
        current = self.workflow.current_analysis(identity, case_id)["reconstruction"]
        context, manifest = project(current)
        record = self._call(
            identity,
            case_id,
            round_id,
            "CREATE",
            {
                "binding": current["input_assessment"],
                "context": context,
                "manifest": manifest,
                "context_digest": digest(context),
                "prompt_digest": digest(PROMPT),
                "schema_digest": digest(OUTPUT_SCHEMA),
            },
            key,
        )
        return {
            "round_id": record["round_id"],
            "status": "AWAITING_HUMAN_SELECTION",
            "prompt_version": PROMPT_VERSION,
            "comparison_rule": "APPLICABLE_ACTION_TYPE_OVERLAP_V2",
        }

    def resume(self, identity, case_id):
        record = self._call(identity, case_id, None)
        return {
            "round_id": record["round_id"],
            "status": "EXISTING_HISTORICAL_ROUND",
            "proposal_withheld": True,
            "created_at": record["created_at"],
        }

    def _fresh(self, identity, case_id, round_id, record):
        if self._event(record, "EXCLUDED"):
            raise InvestigatorAppError(
                409, "STALE_RESEARCH", "Research context is excluded"
            )
        try:
            current = self.workflow.current_analysis(identity, case_id)[
                "reconstruction"
            ]
            bound = dict(current["input_assessment"])
            old = dict(record["binding"])
            bound.pop("checked_at", None)
            old.pop("checked_at", None)
            context, _ = project(current)
            if bound != old or digest(context) != record["context_digest"]:
                raise ValueError("research context no longer current")
            return current["input_assessment"]["checked_at"]
        except Exception as exc:
            self._call(
                identity,
                case_id,
                round_id,
                "EXCLUDED",
                {"reason": "STALE_OR_UNUSABLE_CONTEXT"},
                "excluded",
            )
            raise InvestigatorAppError(
                409, "STALE_RESEARCH", "Research context is stale or unusable"
            ) from exc

    def _bind_human(self, identity, case_id, round_id, record):
        if self._event(record, "HUMAN_SELECTED"):
            return record
        actions = self.workflow.list_actions(identity, case_id)
        eligible = [
            a["action"]
            for a in actions
            if a["action"]["selected_by_analyst"] == identity.name
            and datetime.fromisoformat(
                a["action"]["selected_at"].replace("Z", "+00:00")
            )
            >= datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
        ]
        if not eligible:
            raise InvestigatorAppError(
                409,
                "HUMAN_SELECTION_REQUIRED",
                "Record your initial action before disclosure",
            )
        first = min(eligible, key=lambda a: (a["selected_at"], a["action_id"]))
        return self._call(
            identity,
            case_id,
            round_id,
            "HUMAN_SELECTED",
            {"action_id": first["action_id"]},
            "human",
        )

    def generate(self, identity, case_id, round_id):
        record = self._call(identity, case_id, round_id)
        self._fresh(identity, case_id, round_id, record)
        record = self._bind_human(identity, case_id, round_id, record)
        if self._event(record, "FINISHED"):
            return {
                "round_id": str(round_id),
                "status": "PROCESSING_FINISHED_NOT_DISCLOSED",
            }
        started = self._event(record, "STARTED")
        if started:
            elapsed = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(started["recorded_at"].replace("Z", "+00:00"))
            ).total_seconds()
            if elapsed < 65:
                return {"round_id": str(round_id), "status": "PROCESSING"}
            self._call(
                identity,
                case_id,
                round_id,
                "FINISHED",
                {"status": "AMBIGUOUS", "proposal": None},
                "finished",
            )
            return {"round_id": str(round_id), "status": "AMBIGUOUS"}
        # Competing start commands must not both invoke the runner. A unique
        # per-request claim key makes a losing contender fail at the SQL boundary.
        self._call(
            identity,
            case_id,
            round_id,
            "STARTED",
            {
                "prompt_version": PROMPT_VERSION,
                "provider": self.runner.mode,
                "model": self.runner.model,
            },
            str(uuid4()),
        )
        # All connections and reasoning capabilities are now closed.
        try:
            result = self.runner.generate(record["context"])
            if "failure" in result:
                final = {
                    "status": result["failure"]
                    if result["failure"] in {"TIMEOUT", "REFUSAL", "INVALID_OUTPUT"}
                    else "FAILED",
                    "proposal": None,
                }
            else:
                if (
                    result.get("provider") != self.runner.mode
                    or result.get("model") != self.runner.model
                ):
                    raise ValueError("runner identity changed")
                output = validate_output(result["proposal"], record["context"])
                final = {
                    "status": "VALID" if output["proposals"] else "ABSTAINED",
                    "proposal": output,
                    "provider": result["provider"],
                    "model": result["model"],
                    "usage": result.get("usage"),
                    "cost": result.get("cost"),
                    "latency_ms": result.get("latency_ms"),
                    "prompt_version": PROMPT_VERSION,
                }
        except TimeoutError:
            final = {"status": "TIMEOUT", "proposal": None}
        except (ValueError, KeyError, TypeError):
            final = {"status": "INVALID_OUTPUT", "proposal": None}
        except OSError:
            final = {"status": "FAILED", "proposal": None}
        self._call(identity, case_id, round_id, "FINISHED", final, "finished")
        return {
            "round_id": str(round_id),
            "status": "PROCESSING_FINISHED_NOT_DISCLOSED",
        }

    def disclose(self, identity, case_id, round_id):
        record = self._call(identity, case_id, round_id)
        checked_at = self._fresh(identity, case_id, round_id, record)
        record = self._bind_human(identity, case_id, round_id, record)
        final = self._event(record, "FINISHED")
        if final is None:
            raise InvestigatorAppError(
                409, "NOT_FINISHED", "Research processing is not finished"
            )
        record = self._call(identity, case_id, round_id, "DISCLOSED", {}, "disclosed")
        selected = self._event(record, "HUMAN_SELECTED")["payload"]["action_id"]
        actions = self.workflow.list_actions(identity, case_id)
        human = next(a for a in actions if a["action"]["action_id"] == selected)
        proposed = final["payload"].get("proposal")
        applicability = (
            assess_applicability(proposed, record["context"]) if proposed else None
        )
        proposed_types = (
            [
                p["action_type"]
                for p in applicability["proposals"]
                if p["status"] == "APPLICABLE"
            ]
            if applicability
            else []
        )
        return {
            "round_id": str(round_id),
            "research_only": True,
            "checked_as_of": checked_at,
            "untrusted": True,
            "result": final["payload"],
            "action_applicability": applicability,
            "human_action_id": selected,
            "human_action_type": human["action"]["action_type"],
            "comparison_rule": "APPLICABLE_ACTION_TYPE_OVERLAP_V2",
            "agreement": human["action"]["action_type"] in proposed_types
            if proposed
            else None,
            "unperformed_proposal_outcomes": "UNKNOWN",
            "performed_action_history": human["transitions"],
            "first_disclosed_at": self._event(record, "DISCLOSED")["recorded_at"],
            "reference_manifest": record["manifest"],
            "limitations": "Applicable means bounded action/target fit, not acquisition permission or semantic correctness. Model narrative requires review; server capability is reported separately. Agreement is not correctness; unperformed actions have unknown outcomes. Later choices are post-exposure.",
        }

    def rate(self, identity, case_id, round_id, usefulness, reason, key):
        if (
            usefulness not in {"USEFUL", "NOT_USEFUL", "UNCERTAIN"}
            or not isinstance(reason, str)
            or not 1 <= len(reason.strip()) <= 500
        ):
            raise ValueError("bounded human rating and reason required")
        self._call(
            identity,
            case_id,
            round_id,
            "RATED",
            {"usefulness": usefulness, "reason": reason},
            key,
        )
        return {"recorded": True, "interpretation": "HUMAN_RESEARCH_ANNOTATION"}

    def history(self, identity, case_id, round_id):
        """Outcome linkage is historical; never reveal proposal text on this route."""
        record = self._call(identity, case_id, round_id)
        human = self._event(record, "HUMAN_SELECTED")
        actions = self.workflow.list_actions(identity, case_id)
        selected = next(
            (
                a
                for a in actions
                if human and a["action"]["action_id"] == human["payload"]["action_id"]
            ),
            None,
        )
        references = (
            {
                ref
                for transition in selected["transitions"]
                if transition["to_status"] == "EVIDENCE_ACCEPTED"
                for ref in transition["evidence_references"]
            }
            if selected
            else set()
        )
        current_coverage = None
        try:
            current = self.workflow.current_analysis(identity, case_id)[
                "reconstruction"
            ]
            current_coverage = [
                item["coverage_type"]
                for item in current["coverage_diagnostics"]
                if item["status"] == "COMPLETE"
                and any(p["reference_id"] in references for p in item["provenance"])
            ]
        except InvestigatorAppError:
            pass  # Explicitly unavailable, not invented no-change or success.
        return {
            "round_id": str(round_id),
            "historical_research": True,
            "events": [
                {
                    "kind": e["kind"],
                    "at": e["recorded_at"],
                    "actor": e["actor"],
                    "status": e["payload"].get("status"),
                }
                for e in record["events"]
            ],
            "original_human_action_id": selected["action"]["action_id"]
            if selected
            else None,
            "performed_action_history": selected["transitions"] if selected else [],
            "current_coverage_supported_by_performed_action": current_coverage,
            "unperformed_proposal_outcomes": "UNKNOWN",
            "post_exposure_action_ids": [
                a["action"]["action_id"]
                for a in actions
                if self._event(record, "DISCLOSED")
                and datetime.fromisoformat(
                    a["action"]["selected_at"].replace("Z", "+00:00")
                )
                > datetime.fromisoformat(
                    self._event(record, "DISCLOSED")["recorded_at"].replace(
                        "Z", "+00:00"
                    )
                )
            ],
        }
