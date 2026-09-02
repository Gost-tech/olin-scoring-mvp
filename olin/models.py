"""
Olin Credit Scoring V2 - Data models
Phase 0 scorecard + repayment prediction layer.
Two questions, two engines:
  1. Is this a good business?        -> quality score (6 signals)
  2. Can this business repay?        -> repayment filters (DSCR, stress,
                                        volatility, trend, burden)
A loan is approved only when BOTH answers are yes.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid


class Decision(str, Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    COMMITTEE = "COMMITTEE"        # tier-matrix output: replaces MANUAL_REVIEW
    MANUAL_REVIEW = "MANUAL_REVIEW"  # legacy label, kept for backward compat
    DECLINE = "DECLINE"


class BusinessType(str, Enum):
    ABARROTES = "abarrotes"
    JUGUERIA = "jugueria"
    TAQUERIA = "taqueria"
    RESTAURANT = "restaurant"
    RETAIL = "retail"
    SERVICES = "services"
    HEALTH_BEAUTY = "health_beauty"
    PROFESSIONAL = "professional"
    TRANSPORT = "transport"
    LIGHT_MANUFACTURING = "light_manufacturing"
    WHOLESALE = "wholesale"
    ECOMMERCE = "ecommerce"
    CONSTRUCTION = "construction"
    AGRICULTURE = "agriculture"
    HOSPITALITY = "hospitality"
    EDUCATION = "education"
    HEALTHCARE = "healthcare"
    PHARMACY = "pharmacy"
    LOGISTICS = "logistics"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Raw signal inputs. None = signal not available (triggers fallback logic).
# ---------------------------------------------------------------------------

@dataclass
class FMCGData:
    """Distributor purchase history (FEMSA / Bimbo / Lala).
    Phase 0 reality: no public API, data comes from photos of delivery
    receipts via WhatsApp + distributor confirmation calls."""
    months_of_history: float = 0.0          # how far back we can see
    weekly_purchase_rate: float = 0.0       # 1.0 = buys every week
    missed_weeks_last_12: int = 0           # restock gaps = stress signal
    avg_weekly_purchase_mxn: float = 0.0
    distributor_confirmed: bool = False     # FEMSA or Bimbo delivery confirmed
    trend_3m: float = 0.0                   # -1..+1, purchase volume trend
    source: str = "unknown"                 # distributor | receipts | mock_sandbox
    verified: bool = False                  # evidence checked by Olin/distributor
    evidence_reference: str = ""            # receipt batch or partner record id
    observed_at: str = ""                   # source retrieval/verification time


@dataclass
class BankData:
    """Syncfy open banking (ex-Belvo, discontinued MX June 2026).
    A manual statement may support review but is not provider-verified."""
    months_connected: float = 0.0
    avg_daily_balance_mxn: float = 0.0
    monthly_deposit_count: float = 0.0
    monthly_deposit_volume_mxn: float = 0.0   # NEW V2: total inflows/month
    monthly_outflow_volume_mxn: float = 0.0   # NEW V2: total outflows/month
    deposit_regularity: float = 0.0           # 0..1
    overdrafts_90d: int = 0
    balance_trend_90d: float = 0.0            # -1..+1
    min_daily_balance_mxn: float = 0.0        # NEW V2: worst day in 90d
    source: str = "unknown"                   # syncfy | manual_upload | mock_sandbox
    verified: bool = False
    evidence_reference: str = ""
    observed_at: str = ""
    # Derived collection hint — not used by scorer, surfaced in expediente only
    recommended_collection_days: Optional[dict] = None


@dataclass
class TenureData:
    """Documented continuity evidence; Google does not expose opening date."""
    years_on_google_maps: float = 0.0
    years_in_imss: float = 0.0
    address_consistent: bool = True         # same location across sources


@dataclass
class POSData:
    """Clip / STP transaction API. 28% of CDMX micro-merchants are cash-only:
    missing POS is a weighted signal, NOT a hard filter (Jose Molina)."""
    months_of_history: float = 0.0
    avg_monthly_volume_mxn: float = 0.0
    volume_consistency: float = 0.0         # 0..1
    trend_3m: float = 0.0                   # -1..+1
    source: str = "unknown"
    verified: bool = False
    evidence_reference: str = ""
    observed_at: str = ""


@dataclass
class MapsRatingData:
    """Observed Google Places evidence.

    Only ``rating``, ``review_count`` and ``review_velocity_6m`` feed the
    current scorecard.  The remaining fields preserve provenance for the
    analyst and must not be interpreted as validated credit predictors.
    """
    rating: float = 0.0                     # 0..5
    review_count: int = 0
    review_velocity_6m: int = 0             # recent reviews in returned sample
    source: str = "unknown"                 # google_places | manual
    verified: bool = False                  # fetched server-side from provider
    evidence_reference: str = ""            # Google place id
    observed_at: str = ""
    display_name: str = ""
    formatted_address: str = ""
    business_status: str = ""
    primary_type: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    google_maps_uri: str = ""
    website_uri: str = ""
    oldest_visible_review_at: str = ""
    review_sample_size: int = 0
    # Public persistent geo evidence from INEGI DENUE.
    denue_id: str = ""
    denue_clee: str = ""
    denue_name: str = ""
    denue_address: str = ""
    denue_activity: str = ""
    denue_size_band: str = ""
    denue_latitude: Optional[float] = None
    denue_longitude: Optional[float] = None
    denue_verified: bool = False
    denue_observed_at: str = ""


@dataclass
class IMSSPayrollData:
    """IMSS public registry. Zero employees is neutral, not negative."""
    registered_employees: Optional[int] = None  # None = unknown


@dataclass
class FraudData:
    """Collected at onboarding. Automatic checks run immediately;
    INE is manual (like BuroData) and blocks disbursement if unchecked."""
    phone_mx: str = ""          # 10-digit MX mobile
    rfc: str = ""               # 12 (empresa) or 13 (persona) chars
    curp: str = ""              # 18-char CURP (optional, strengthens identity)
    ine_checked: bool = False   # manual INE/IFE check done by agent
    address_stated: str = ""    # merchant's stated address for cross-check


@dataclass
class FraudAssessment:
    """Output of the fraud gate (GATE 0, runs before quality score)."""
    risk_score: float                   # 0..100, 0=clean
    checks: dict                        # {check_name: passed (bool)}
    hard_blocks: list[str] = field(default_factory=list)   # stop disbursement
    flags: list[str] = field(default_factory=list)         # analyst warnings


@dataclass
class BuroData:
    """Círculo de Crédito query (MXN 50/query, circulodecredito.com.mx).
    Mandatory pre-disbursement; None = not yet checked → blocks disbursement.
    Bureau provider: see BUREAU_PROVIDER constant in scorecard.py."""
    checked: bool = False
    active_delinquencies: int = 0
    active_loans_count: int = 0
    worst_mob_status: str = ""              # e.g. "01" current, "97" fraud
    score: Optional[int] = None             # Círculo de Crédito score 300-850
    source: str = "unknown"
    verified: bool = False
    evidence_reference: str = ""
    observed_at: str = ""


@dataclass
class ExternalSignalEvidence:
    """Normalized evidence supplied by a provider or the partner bank.

    The 28-signal architecture keeps these observations separate from the
    legacy six-signal scorecard.  ``metrics`` contains only the documented
    inputs for one signal; a provider cannot submit a final Olin decision.
    """
    metrics: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"
    verified: bool = False
    evidence_reference: str = ""
    observed_at: str = ""


@dataclass
class PharmacyData:
    """Pharmacy-specific facts; trust is resolved server-side, not by payload."""
    subtype: str = "community_pharmacy"
    scian_code: str = "464111"
    sells_controlled_medicines: bool = False
    license_status: str = "not_supplied"
    license_reference: str = ""
    supplier_count: int = 0
    top_supplier_share: Optional[float] = None
    inventory_days: Optional[float] = None
    expiry_writeoff_ratio: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    stockout_rate: Optional[float] = None
    source: str = "partner_supplied"
    evidence_reference: str = ""
    observed_at: str = ""


@dataclass
class FacilityTerms:
    """Terms evaluated by the capacity engine; not a lending offer."""
    term_months: int = 12
    monthly_rate: float = 0.03
    existing_monthly_debt_service_mxn: float = 0.0
    policy_max_amount_mxn: float = 80_000.0
    target_dscr: float = 1.25
    revenue_stress_pct: float = 0.15
    cost_stress_pct: float = 0.10


@dataclass
class BankFeatureContractV2:
    """Versioned, classified cash-flow features supplied by a trusted bank source."""
    contract_version: str = "bank-feature-contract-2.0"
    calculation_version: str = "bank-cashflow-2.0"
    normalization_basis: str = "monthly_average"
    currency: str = "MXN"
    period_start: str = ""
    period_end: str = ""
    account_count: int = 0
    account_coverage_ratio: float = 0.0
    account_holder_match: bool = False
    classification_coverage_ratio: float = 0.0
    operating_inflows_mxn: float = 0.0
    operating_outflows_mxn: float = 0.0
    internal_transfer_inflows_mxn: float = 0.0
    debt_proceeds_mxn: float = 0.0
    refunds_mxn: float = 0.0
    existing_monthly_debt_service_mxn: float = 0.0
    end_of_day_avg_balance_mxn: float = 0.0
    end_of_day_min_balance_mxn: float = 0.0
    inflow_volatility: float = 0.0
    top_payer_share: float = 0.0
    source: str = "unknown"
    evidence_reference: str = ""
    observed_at: str = ""


@dataclass
class OperatingProfile:
    """Archetype-specific operating metrics under a bounded bank contract."""
    metrics: dict[str, float] = field(default_factory=dict)
    source: str = "unknown"
    evidence_reference: str = ""
    observed_at: str = ""


@dataclass
class Application:
    """One loan application = one scoring event."""
    merchant_name: str
    business_type: BusinessType
    requested_amount_mxn: float
    colonia: str = ""
    clabe: str = ""
    business_description: str = ""
    funding_purpose: str = ""
    project_description: str = ""
    evidence_route: str = ""

    fmcg: Optional[FMCGData] = None
    bank: Optional[BankData] = None
    tenure: Optional[TenureData] = None
    pos: Optional[POSData] = None
    maps: Optional[MapsRatingData] = None
    imss: Optional[IMSSPayrollData] = None
    buro: Optional[BuroData] = None
    fraud: Optional[FraudData] = None
    signal_evidence: dict[str, ExternalSignalEvidence] = field(default_factory=dict)
    pharmacy: Optional[PharmacyData] = None
    facility: FacilityTerms = field(default_factory=FacilityTerms)
    bank_features_v2: Optional[BankFeatureContractV2] = None
    operating_profile: Optional[OperatingProfile] = None

    application_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    environment: str = "unspecified"         # demo | production | test

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RepaymentAssessment:
    """Output of the repayment prediction layer (V2)."""
    dscr: Optional[float]                  # net income / monthly payment
    stress_buffer_ratio: Optional[float]   # min balance / 2-day shock
    deposit_volatility_ok: Optional[bool]
    trend_ok: Optional[bool]
    burden_ratio: Optional[float]          # payment / monthly inflows
    estimated_monthly_net_mxn: Optional[float]
    hard_declines: list[str] = field(default_factory=list)
    downgrades: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class SignalScore:
    name: str
    weight: float
    raw_score: Optional[float]
    effective_weight: float
    available: bool
    fallback_used: Optional[str]
    explanation: str


@dataclass
class ScoreResult:
    application_id: str
    merchant_name: str
    score: float
    ci_low: float
    ci_high: float
    data_coverage: float
    decision: Decision
    decision_reasons: list[str]
    hard_filter_failures: list[str]
    fraud_assessment: Optional[FraudAssessment]
    repayment: Optional[RepaymentAssessment]
    max_ticket_mxn: float
    approved_amount_mxn: float
    pricing_fixed_cost_mxn: float
    signals: list[SignalScore]
    tier: int = 0   # 1-14 from the 3-dimension Buró×DSCR×Score matrix; 0 = pre-v2
    tier_sensitivity: dict = field(default_factory=dict)  # upgrade-path diagnostics
    scored_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    engine_version: str = "scorecard-0.4.0-circulo-tier-matrix"
    environment: str = "unspecified"
    production_blocks: list[str] = field(default_factory=list)
    alternative_signal_report: dict[str, Any] = field(default_factory=dict)
    capacity_v2: dict[str, Any] = field(default_factory=dict)
    enrichment_report: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Disbursement, collection, graduation, portfolio
# ---------------------------------------------------------------------------

@dataclass
class DisbursementResult:
    application_id: str
    folio_stp: Optional[str]        # STP tracking number
    folio_origen: str               # our internal reference
    status: str                     # "sent" | "confirmed" | "failed" | "sandbox"
    amount_mxn: float
    clabe_destino: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: Optional[str] = None


@dataclass
class GraduationOffer:
    tier: int                        # 0=new, 1=1 repaid, 2=2+, 3=4+ no default
    max_ticket_mxn: float
    pricing_rate: float              # monthly rate (default Phase 0 = 0.03)
    early_repayment_bonus: bool      # rate reduced for paying early last loan
    notes: list[str] = field(default_factory=list)


@dataclass
class PortfolioBlock:
    """Pre-GATE-0 portfolio health check. Blocks override credit decision."""
    blocked: bool
    reasons: list[str] = field(default_factory=list)    # hard blocks
    warnings: list[str] = field(default_factory=list)   # analyst flags
    stats: dict = field(default_factory=dict)           # live portfolio snapshot
