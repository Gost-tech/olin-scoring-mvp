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
from typing import Optional
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
    Fallback: manual statement upload via WhatsApp."""
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
    """Google Maps creation date + IMSS registry."""
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


@dataclass
class MapsRatingData:
    """Google Places API."""
    rating: float = 0.0                     # 0..5
    review_count: int = 0
    review_velocity_6m: int = 0             # new reviews last 6 months


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


@dataclass
class Application:
    """One loan application = one scoring event."""
    merchant_name: str
    business_type: BusinessType
    requested_amount_mxn: float
    colonia: str = ""
    clabe: str = ""

    fmcg: Optional[FMCGData] = None
    bank: Optional[BankData] = None
    tenure: Optional[TenureData] = None
    pos: Optional[POSData] = None
    maps: Optional[MapsRatingData] = None
    imss: Optional[IMSSPayrollData] = None
    buro: Optional[BuroData] = None
    fraud: Optional[FraudData] = None

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
