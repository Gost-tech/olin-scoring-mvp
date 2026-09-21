"""Phase 5A human-selected investigation workflow.

This module owns administrative investigation state only.  It cannot create,
verify, or mutate canonical evidence and it never persists Phase 3 or Phase 4
reasoning results.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType

ACTION_CATALOGUE_VERSION = "investigator-action-catalogue-1.0"
ACTION_SCHEMA_VERSION = 1
MAX_RATIONALE_LENGTH = 1000
MAX_REASON_DETAIL_LENGTH = 1000


class WorkflowValidationError(ValueError):
    """Raised when an action command is outside the closed Phase 5A contract."""


class ActionType(str, Enum):
    REQUEST_ACCOUNT_CHANNEL_RECORD = "REQUEST_ACCOUNT_CHANNEL_RECORD"
    CLARIFY_MERCHANT_ASSERTION_SCOPE = "CLARIFY_MERCHANT_ASSERTION_SCOPE"


class ActionStatus(str, Enum):
    SELECTED = "SELECTED"
    REQUESTED = "REQUESTED"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    EVIDENCE_ACCEPTED = "EVIDENCE_ACCEPTED"
    COMPLETED_RESOLVED = "COMPLETED_RESOLVED"
    COMPLETED_UNRESOLVED = "COMPLETED_UNRESOLVED"
    STOPPED = "STOPPED"
    ESCALATED = "ESCALATED"


class StopReason(str, Enum):
    EVIDENCE_UNAVAILABLE = "EVIDENCE_UNAVAILABLE"
    PERMISSION_MISSING_OR_WITHDRAWN = "PERMISSION_MISSING_OR_WITHDRAWN"
    QUESTION_STILL_UNRESOLVED = "QUESTION_STILL_UNRESOLVED"
    FURTHER_INVESTIGATION_NOT_JUSTIFIED = "FURTHER_INVESTIGATION_NOT_JUSTIFIED"
    SYNTHETIC_DEMO_LIMIT_REACHED = "SYNTHETIC_DEMO_LIMIT_REACHED"


@dataclass(frozen=True)
class ActionDefinition:
    action_type: ActionType
    question_id: str
    unresolved_question: str
    purpose: str
    permitted_data_scope: str
    requested_source: str
    prerequisites: tuple[str, ...]
    resolution_criteria: tuple[str, ...]
    relevant_finding_types: tuple[str, ...]
    catalogue_version: str = ACTION_CATALOGUE_VERSION

    def canonical_record(self) -> dict[str, object]:
        return {
            "action_type": self.action_type.value,
            "catalogue_version": self.catalogue_version,
            "permitted_data_scope": self.permitted_data_scope,
            "prerequisites": list(self.prerequisites),
            "purpose": self.purpose,
            "question_id": self.question_id,
            "relevant_finding_types": list(self.relevant_finding_types),
            "requested_source": self.requested_source,
            "resolution_criteria": list(self.resolution_criteria),
            "unresolved_question": self.unresolved_question,
        }


_CATALOGUE = {
    ActionType.REQUEST_ACCOUNT_CHANNEL_RECORD: ActionDefinition(
        action_type=ActionType.REQUEST_ACCOUNT_CHANNEL_RECORD,
        question_id="revenue-channel-coverage",
        unresolved_question=(
            "Are the bank-visible inflows drawn from all relevant business accounts "
            "and payment channels for the stated period?"
        ),
        purpose="Narrow unknown bank-account and revenue-channel coverage.",
        permitted_data_scope=(
            "Account/channel identifiers and period-specific coverage status only; "
            "no credentials or unrestricted transaction bodies."
        ),
        requested_source=(
            "A supported regulated-financial-institution coverage attestation."
        ),
        prerequisites=(
            "Active case authority and usable evidence consent.",
            "The source is already supported by the canonical evidence profile.",
        ),
        resolution_criteria=(
            (
                "A proposition-specific canonical coverage record identifies subject "
                "and exact period."
            ),
            "Canonical authority, not the analyst response, determines verification.",
        ),
        relevant_finding_types=(
            "BANK_ACCOUNT_COVERAGE",
            "REVENUE_CHANNEL_COVERAGE",
            "REVENUE_RECONCILIATION_GAP",
        ),
    ),
    ActionType.CLARIFY_MERCHANT_ASSERTION_SCOPE: ActionDefinition(
        action_type=ActionType.CLARIFY_MERCHANT_ASSERTION_SCOPE,
        question_id="merchant-revenue-claim-scope",
        unresolved_question=(
            "What exact period, business scope, and channels does the merchant's "
            "revenue assertion describe?"
        ),
        purpose="Clarify the meaning of an attributed merchant assertion.",
        permitted_data_scope=(
            "Merchant clarification of period, scope, and included channels; no "
            "verified-evidence designation."
        ),
        requested_source="The attributed merchant or authorized case representative.",
        prerequisites=(
            "The merchant assertion is present in the current assessment.",
            "Permission exists to request clarification.",
        ),
        resolution_criteria=(
            "A new attributed claim records an exact period and scope.",
            "The clarification remains a claim unless separately verified by canonical authority.",
        ),
        relevant_finding_types=(
            "MERCHANT_CLAIM",
            "REVENUE_RECONCILIATION_GAP",
        ),
    ),
}

ACTION_CATALOGUE: Mapping[ActionType, ActionDefinition] = MappingProxyType(_CATALOGUE)


_TRANSITIONS: Mapping[ActionStatus, frozenset[ActionStatus]] = MappingProxyType(
    {
        ActionStatus.SELECTED: frozenset(
            {ActionStatus.REQUESTED, ActionStatus.STOPPED, ActionStatus.ESCALATED}
        ),
        ActionStatus.REQUESTED: frozenset(
            {
                ActionStatus.RESPONSE_RECEIVED,
                ActionStatus.STOPPED,
                ActionStatus.ESCALATED,
            }
        ),
        ActionStatus.RESPONSE_RECEIVED: frozenset(
            {
                ActionStatus.EVIDENCE_ACCEPTED,
                ActionStatus.COMPLETED_UNRESOLVED,
                ActionStatus.STOPPED,
                ActionStatus.ESCALATED,
            }
        ),
        ActionStatus.EVIDENCE_ACCEPTED: frozenset(
            {
                ActionStatus.COMPLETED_UNRESOLVED,
                ActionStatus.ESCALATED,
            }
        ),
        ActionStatus.COMPLETED_RESOLVED: frozenset(),
        ActionStatus.COMPLETED_UNRESOLVED: frozenset(),
        ActionStatus.STOPPED: frozenset(),
        ActionStatus.ESCALATED: frozenset(),
    }
)


def action_definition(value: str | ActionType) -> ActionDefinition:
    try:
        action_type = value if isinstance(value, ActionType) else ActionType(value)
    except ValueError as exc:
        raise WorkflowValidationError("action type is not in the V1 catalogue") from exc
    return ACTION_CATALOGUE[action_type]


def require_transition(
    current: str | ActionStatus, requested: str | ActionStatus
) -> None:
    try:
        current_status = (
            current if isinstance(current, ActionStatus) else ActionStatus(current)
        )
        requested_status = (
            requested
            if isinstance(requested, ActionStatus)
            else ActionStatus(requested)
        )
    except ValueError as exc:
        raise WorkflowValidationError("action status is unsupported") from exc
    if requested_status not in _TRANSITIONS[current_status]:
        raise WorkflowValidationError(
            f"invalid action transition: {current_status.value} -> {requested_status.value}"
        )


def validate_rationale(value: str) -> str:
    canonical = value.strip()
    if not canonical or len(canonical.encode("utf-8")) > MAX_RATIONALE_LENGTH:
        raise WorkflowValidationError("bounded analyst rationale is required")
    return canonical


def validate_reason_detail(value: str | None) -> str | None:
    if value is None:
        return None
    canonical = value.strip()
    if not canonical or len(canonical.encode("utf-8")) > MAX_REASON_DETAIL_LENGTH:
        raise WorkflowValidationError("reason detail is empty or too long")
    return canonical


def validate_effort_cost(
    *,
    effort_minutes: int | None,
    cost_amount: str | Decimal | None,
    cost_currency: str | None,
) -> tuple[int | None, str | None, str | None]:
    if effort_minutes is not None and not 0 <= effort_minutes <= 100_000:
        raise WorkflowValidationError("effort minutes are outside the bounded domain")
    if cost_amount is None:
        if cost_currency is not None:
            raise WorkflowValidationError("cost currency requires an actual cost")
        return effort_minutes, None, None
    try:
        amount = Decimal(str(cost_amount))
    except InvalidOperation as exc:
        raise WorkflowValidationError("actual cost must be a decimal") from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal(1000000000):
        raise WorkflowValidationError("actual cost is outside the bounded domain")
    if cost_currency not in {"MXN", "USD"}:
        raise WorkflowValidationError("actual cost currency is unsupported")
    return effort_minutes, format(amount, "f"), cost_currency


def require_terminal_reason(
    status: str | ActionStatus, reason_code: str | None
) -> None:
    terminal = status if isinstance(status, ActionStatus) else ActionStatus(status)
    if terminal in {
        ActionStatus.STOPPED,
        ActionStatus.ESCALATED,
        ActionStatus.COMPLETED_UNRESOLVED,
    }:
        try:
            StopReason(str(reason_code))
        except ValueError as exc:
            raise WorkflowValidationError(
                "unresolved, stopped, and escalated actions require a closed reason"
            ) from exc
    elif reason_code is not None:
        raise WorkflowValidationError("this transition does not accept a stop reason")
