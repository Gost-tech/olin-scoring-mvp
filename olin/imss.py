"""
Olin - IMSS / RFC connector

Two things this module does:

1. RFC validation (automatic, no API needed)
   The Mexican RFC has a deterministic structure. We validate format and
   extract the embedded birth/creation date and entity type.

2. IMSS employer registry (manual stub, Phase 0)
   IMSS does not expose a public REST API for Phase 0 use. The practical
   flow is:
     a. Collect RFC at onboarding.
     b. Agent queries IDSE (imss.gob.mx) or uses SIPARE credentials.
     c. Agent fills in the IMSSPayrollData fields and marks imss_verified=True.

   When a Syncfy/CFDI/SAT data partner is added in Phase 1, swap
   _fetch_imss_live() for the real implementation — the public interface
   (get_imss_data) stays the same.

Usage:
    from olin.imss import get_imss_data, validate_rfc

    info = validate_rfc("GASA8501011A2")
    # → {"valid": True, "type": "persona", "entity_date": "1985-01-01", ...}

    data = get_imss_data("GASA8501011A2", verified_employees=2)
    # → IMSSPayrollData(registered_employees=2)
"""
from __future__ import annotations

import re
from typing import Optional

from .models import IMSSPayrollData

# RFC patterns
_RFC_PERSONA  = re.compile(
    r'^([A-ZÑ&]{4})'
    r'(\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])'
    r'([A-Z0-9]{3})$',
    re.IGNORECASE,
)
_RFC_EMPRESA  = re.compile(
    r'^([A-ZÑ&]{3})'
    r'(\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])'
    r'([A-Z0-9]{3})$',
    re.IGNORECASE,
)

# Generic RFC (either type) for quick format check
_RFC_ANY = re.compile(
    r'^[A-ZÑ&]{3,4}'
    r'\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])'
    r'[A-Z0-9]{3}$',
    re.IGNORECASE,
)


def validate_rfc(rfc: str) -> dict:
    """
    Validate and parse a Mexican RFC.

    Returns a dict with:
      valid       : bool
      type        : "persona_fisica" | "empresa" | None
      entity_date : "YYYY-MM-DD" string embedded in the RFC
      initials    : the name-derived prefix
      homoclave   : the 3-char suffix
      error       : human-readable error if invalid
    """
    clean = re.sub(r'[\s\-]', '', rfc).upper()
    result: dict = {
        "valid": False, "type": None, "entity_date": None,
        "initials": None, "homoclave": None, "error": None,
        "rfc_clean": clean,
    }

    if not clean:
        result["error"] = "RFC is empty"
        return result

    m = _RFC_PERSONA.match(clean)
    if m:
        yy, mm, dd = m.group(2), m.group(3), m.group(4)
        year = int(yy) + (1900 if int(yy) >= 25 else 2000)
        result.update({
            "valid": True, "type": "persona_fisica",
            "entity_date": f"{year}-{mm}-{dd}",
            "initials": m.group(1), "homoclave": m.group(5),
        })
        return result

    m = _RFC_EMPRESA.match(clean)
    if m:
        yy, mm, dd = m.group(2), m.group(3), m.group(4)
        year = int(yy) + (1900 if int(yy) >= 90 else 2000)
        result.update({
            "valid": True, "type": "empresa",
            "entity_date": f"{year}-{mm}-{dd}",
            "initials": m.group(1), "homoclave": m.group(5),
        })
        return result

    result["error"] = (
        f"'{rfc}' does not match MX RFC format "
        "(3-4 letters + YYMMDD + 3-char homoclave)"
    )
    return result


def get_imss_data(
    rfc: str,
    verified_employees: Optional[int] = None,
    imss_verified: bool = False,
) -> IMSSPayrollData:
    """
    Return IMSSPayrollData for a given RFC.

    Phase 0: manual verification. Agent queries IDSE/IMSS and fills in
    verified_employees. If imss_verified is False, returns None employees
    (signal stays missing, weight redistributed).

    Phase 1 upgrade: replace with a live CFDI/SAT-based connector that
    reads nómina CFDI complements for the RFC. Same return type.
    """
    rfc_info = validate_rfc(rfc)
    if not rfc_info["valid"]:
        return IMSSPayrollData(registered_employees=None)

    if not imss_verified:
        # Not yet verified — signal stays missing rather than guessing
        return IMSSPayrollData(registered_employees=None)

    return IMSSPayrollData(registered_employees=verified_employees)


# ---------------------------------------------------------------------------
# Phase 1 stub — replace body when CFDI partner is available
# ---------------------------------------------------------------------------

def _fetch_imss_live(rfc: str) -> Optional[int]:
    """
    Query a CFDI/SAT data provider for nómina complement counts.
    Returns number of active payroll employees or None.

    NOT IMPLEMENTED — waiting for Phase 1 data partnership.
    Options:
      - Defontana / Nominasio (CFDI SaaS with API)
      - SAT CFDI download (requires FIEL certificate of the merchant)
      - IMSS SIPARE web portal (requires IMSS employer credentials)
    """
    raise NotImplementedError(
        "Live IMSS connector not yet implemented. "
        "Use get_imss_data(rfc, verified_employees=N, imss_verified=True) "
        "for manual verification flow."
    )
