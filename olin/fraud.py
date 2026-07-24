"""
Olin V2 - Fraud Gate (GATE 0)

Runs BEFORE the quality scorecard. A merchant who passes fraud screening
gets scored; one who fails gets declined before any credit analysis begins.

Four automatic checks (run at onboarding with no external API):
  1. Phone: valid 10-digit MX mobile number
  2. RFC: valid Mexican tax ID format (12 = empresa, 13 = persona física)
  3. Address: stated colonia appears in the Maps-returned address
  4. CLABE: bank detected from CLABE prefix matches the bank the merchant
     said they use (catches CLABE belonging to someone else)

One manual check (blocks disbursement like Buro, not scoring):
  5. INE/IFE: government-issued photo ID verified by agent

Risk score interpretation:
  0–20  : clean, no action
  21–50 : review recommended
  51+   : strong flag, analyst must clear before approval
  hard_blocks present: disbursement blocked regardless of score

Design note: these are NOT score inputs — fraud risk is orthogonal to
credit quality. A clean fraudster can have a perfect abarrotes history.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from .models import Application, FraudData, FraudAssessment

# Penalty weights for risk_score (0..100)
_W_PHONE   = 15   # invalid phone
_W_RFC     = 30   # invalid RFC (highest: RFC is the identity anchor)
_W_ADDRESS = 25   # address mismatch
_W_CLABE   = 20   # CLABE-bank inconsistency
_W_CURP    = 10   # CURP missing (not required, but absence adds minor risk)

# MX mobile: 10 digits, first digit 2-9, valid area codes cover all states
_PHONE_RE = re.compile(r'^[2-9]\d{9}$')

# RFC: 3-4 uppercase letters (incl. Ñ, &), 6-digit date, 3-char homoclave
_RFC_RE = re.compile(
    r'^[A-ZÑ&]{3,4}'       # name initials (3=empresa, 4=persona física)
    r'\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])'  # YYMMDD
    r'[A-Z0-9]{3}$',        # homoclave
    re.IGNORECASE,
)

# CURP: strict 18-char structure
_CURP_RE = re.compile(
    r'^[A-Z]{4}\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])'
    r'[HM][A-Z]{5}[B-DF-HJ-NP-TV-Z\d]\d$',
    re.IGNORECASE,
)

# CLABE prefix → canonical bank name (same as onboard.py)
_CLABE_BANKS: dict[str, str] = {
    "002": "Banamex", "006": "BBVA", "012": "BBVA Bancomer",
    "021": "HSBC",    "072": "Banorte", "014": "Santander",
    "058": "Banregio", "044": "Scotiabank",
}


def _normalize(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r'\s+', ' ', s).strip()


def _check_phone(phone: str) -> tuple[bool, str]:
    clean = re.sub(r'[\s\-\(\)\+]', '', phone)
    if clean.startswith("52") and len(clean) == 12:
        clean = clean[2:]
    if not clean:
        return False, "Phone not provided"
    if not _PHONE_RE.match(clean):
        return False, f"Invalid MX mobile format: '{phone}'"
    return True, f"Phone {clean[:3]}****{clean[-3:]} valid"


def _check_rfc(rfc: str) -> tuple[bool, str]:
    clean = re.sub(r'\s', '', rfc).upper()
    if not clean:
        return False, "RFC not provided"
    if not _RFC_RE.match(clean):
        return False, f"RFC '{rfc}' does not match MX RFC format"
    entity = "persona física" if len(clean) == 13 else "empresa"
    return True, f"RFC {clean[:4]}****** valid ({entity})"


def _check_curp(curp: str) -> tuple[bool, str]:
    clean = re.sub(r'\s', '', curp).upper()
    if not clean:
        return False, "CURP not provided (optional but strengthens identity)"
    if not _CURP_RE.match(clean):
        return False, f"CURP '{curp}' does not match 18-char MX format"
    return True, f"CURP {clean[:4]}************** valid"


def _check_address(fraud: FraudData, maps_address: Optional[str]) -> tuple[bool, str]:
    """Stated colonia should appear somewhere in the Maps-returned address."""
    if not fraud.address_stated:
        return True, "Address cross-check skipped (no stated address)"
    if not maps_address:
        return True, "Address cross-check skipped (no Maps result)"
    stated = _normalize(fraud.address_stated)
    maps   = _normalize(maps_address)
    # Extract tokens of 4+ chars from stated address and check presence
    tokens = [t for t in re.split(r'[\s,]+', stated) if len(t) >= 4]
    if not tokens:
        return True, "Address cross-check skipped (address too short)"
    hits = sum(1 for t in tokens if t in maps)
    ratio = hits / len(tokens)
    if ratio >= 0.40:
        return True, f"Address cross-check passed ({hits}/{len(tokens)} tokens matched)"
    return False, (
        f"Address mismatch: stated '{fraud.address_stated}' shares only "
        f"{hits}/{len(tokens)} tokens with Maps result"
    )


def _check_clabe(clabe: str, bank_stated: Optional[str]) -> tuple[bool, str]:
    """CLABE prefix → bank name should match what merchant said."""
    if not clabe or len(clabe) < 3:
        return True, "CLABE cross-check skipped (no CLABE)"
    if not bank_stated:
        return True, "CLABE cross-check skipped (bank not recorded)"
    clabe_bank = _CLABE_BANKS.get(clabe[:3], "").lower()
    stated     = bank_stated.lower()
    if not clabe_bank:
        return True, f"CLABE prefix {clabe[:3]} not in known bank list"
    if clabe_bank in stated or stated in clabe_bank or clabe_bank[:4] in stated:
        return True, f"CLABE prefix {clabe[:3]} consistent with stated bank"
    return False, (
        f"CLABE prefix {clabe[:3]} points to {clabe_bank.title()}, "
        f"but merchant said '{bank_stated}'"
    )


def assess_fraud(
    app: Application,
    maps_address: Optional[str] = None,
    bank_stated: Optional[str] = None,
) -> FraudAssessment:
    """
    Run all automatic fraud checks. Returns FraudAssessment.

    Args:
        app: the loan application (fraud field must be populated)
        maps_address: full address string returned by Google Places (for cross-check)
        bank_stated: bank name the merchant said they use (from CLABE or Q6 in onboard)
    """
    fd = app.fraud or FraudData()

    phone_ok,   phone_msg   = _check_phone(fd.phone_mx)
    rfc_ok,     rfc_msg     = _check_rfc(fd.rfc)
    curp_ok,    curp_msg    = _check_curp(fd.curp)
    address_ok, address_msg = _check_address(fd, maps_address)
    clabe_ok,   clabe_msg   = _check_clabe(app.clabe or "", bank_stated)

    checks = {
        "phone":   phone_ok,
        "rfc":     rfc_ok,
        "curp":    curp_ok,
        "address": address_ok,
        "clabe":   clabe_ok,
        "ine":     fd.ine_checked,
    }

    flags:       list[str] = []
    hard_blocks: list[str] = []

    # RFC invalid = hard block (no verified identity = no loan)
    if not rfc_ok:
        hard_blocks.append(f"Identity unverifiable: {rfc_msg}")

    # INE not checked = disbursement block (like Buro)
    if not fd.ine_checked:
        hard_blocks.append(
            "INE/IFE not verified. Agent must check government-issued photo ID "
            "before disbursement."
        )

    # Warnings (not hard blocks)
    if not phone_ok:
        flags.append(phone_msg)
    if not address_ok:
        flags.append(address_msg)
    if not clabe_ok:
        flags.append(clabe_msg)
    if not curp_ok and fd.curp:          # only flag if they tried to provide one
        flags.append(curp_msg)
    if not curp_ok and not fd.curp:
        flags.append("CURP not provided — identity confidence lower")

    # Risk score: sum of penalties for failed checks
    risk = 0.0
    if not phone_ok:   risk += _W_PHONE
    if not rfc_ok:     risk += _W_RFC
    if not address_ok: risk += _W_ADDRESS
    if not clabe_ok:   risk += _W_CLABE
    if not curp_ok:    risk += _W_CURP
    risk = min(100.0, risk)

    return FraudAssessment(
        risk_score=round(risk, 1),
        checks=checks,
        hard_blocks=hard_blocks,
        flags=flags,
    )
