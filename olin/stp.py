"""
Olin - STP/SPEI disbursement connector

STP (Sistema de Transferencias y Pagos) is the Mexican payment rail for SPEI.
Every peso we disburse to a merchant goes through this API.

Auth:
  STP uses mTLS (client certificate) + RSA signature on the payment payload.
  Required env vars:
    STP_EMPRESA          — your STP company code (e.g. "OLIN")
    STP_CUENTA_ORDENANTE — Olin's source CLABE (18 digits)
    STP_RFC_ORDENANTE    — Olin's RFC
    STP_PRIVATE_KEY_PATH — path to RSA private key PEM (provided by STP)
    STP_CERT_PATH        — path to client certificate PEM (provided by STP)
    STP_SANDBOX          — "1" for demo.stpmex.com, "0" for prod (default "1")

Endpoints:
  Sandbox: https://demo.stpmex.com:7002/speiws/rest/
  Prod:    https://prod.stpmex.com:7002/speiws/rest/

Sandbox note: STP sandbox does not require a real certificate for signature
validation. Set STP_SANDBOX=1 and the connector will POST to the demo URL
and return a synthetic folio without actual signing.

Usage:
    from olin.stp import disburse, DisbursementError
    result = disburse(application_id, amount_mxn, clabe_destino,
                      nombre_beneficiario, rfc_beneficiario,
                      concepto="Prestamo Olin")
"""
from __future__ import annotations

import base64
import hashlib
import math
import os
import time
from datetime import datetime, timezone
from typing import Optional

try:
    import requests
except ImportError as e:
    raise ImportError("pip install requests") from e

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .models import DisbursementResult
from .config import is_production

SANDBOX_URL = "https://demo.stpmex.com:7002/speiws/rest"
PROD_URL    = "https://prod.stpmex.com:7002/speiws/rest"

INSTITUCION_OLIN = 90646   # STP's own institution code (for inter-STP transfers)


class DisbursementError(Exception):
    pass


def validate_clabe(clabe: str) -> bool:
    """Validate the 18-digit CLABE checksum defined by Banco de México."""
    if len(clabe) != 18 or not clabe.isdigit():
        return False
    weights = (3, 7, 1)
    checksum = (10 - sum(
        (int(digit) * weights[index % 3]) % 10
        for index, digit in enumerate(clabe[:17])
    ) % 10) % 10
    return checksum == int(clabe[-1])


def _is_sandbox() -> bool:
    return os.getenv("STP_SANDBOX", "1").strip() != "0"


def is_sandbox() -> bool:
    """Public environment check used by the disbursement gate."""
    return _is_sandbox()


def validate_runtime_environment() -> None:
    """Prevent demo records reaching real SPEI, and production using fake SPEI."""
    if is_production() and _is_sandbox():
        raise DisbursementError(
            "Production mode requires STP_SANDBOX=0; disbursement blocked"
        )
    if not is_production() and not _is_sandbox():
        raise DisbursementError(
            "Real STP is disabled outside OLIN_MODE=production; disbursement blocked"
        )


def _base_url() -> str:
    return SANDBOX_URL if _is_sandbox() else PROD_URL


def _empresa() -> str:
    v = os.getenv("STP_EMPRESA", "").strip()
    if not v:
        raise DisbursementError(
            "STP_EMPRESA not set. Add to .env: STP_EMPRESA=YOURCODE"
        )
    return v


def _cuenta_ordenante() -> str:
    v = os.getenv("STP_CUENTA_ORDENANTE", "").strip()
    if not v:
        raise DisbursementError(
            "STP_CUENTA_ORDENANTE not set (Olin's source CLABE)."
        )
    return v


def _rfc_ordenante() -> str:
    return os.getenv("STP_RFC_ORDENANTE", "OLI200101AB1").strip()


def _folio_origen(application_id: str) -> str:
    """Unique folio per disbursement — application_id + unix timestamp."""
    ts = str(int(time.time()))[-6:]
    return f"OLIN{application_id[:8].upper()}{ts}"


def _sign_payload(payload: dict) -> str:
    """
    Sign the STP payment payload with RSA SHA-256.

    The cadena (string to sign) is the pipe-delimited concatenation of
    specific fields, as per STP documentation:
    ||empresa||folio||fechaOperacion||claveRastreo||institucionContraparte||
    tipoPago||monto||nombreBeneficiario||cuentaBeneficiario||
    rfcCurpBeneficiario||nombreOrdenante||cuentaOrdenante||
    rfcCurpOrdenante||conceptoPago||

    Returns base64-encoded signature, or a mock hash in sandbox mode.
    """
    cadena = (
        f"||{payload['empresa']}||{payload['folio']}||{payload['fechaOperacion']}||"
        f"{payload['claveRastreo']}||{payload['institucionContraparte']}||"
        f"{payload['tipoPago']}||{payload['monto']}||{payload['nombreBeneficiario']}||"
        f"{payload['cuentaBeneficiario']}||{payload['rfcCurpBeneficiario']}||"
        f"{payload['nombreOrdenante']}||{payload['cuentaOrdenante']}||"
        f"{payload['rfcCurpOrdenante']}||{payload['conceptoPago']}||"
    )

    if _is_sandbox():
        # Sandbox: STP doesn't validate the real signature, use SHA-256 mock
        digest = hashlib.sha256(cadena.encode()).digest()
        return base64.b64encode(digest).decode()

    # Production: sign with RSA private key
    key_path = os.getenv("STP_PRIVATE_KEY_PATH", "").strip()
    if not key_path:
        raise DisbursementError(
            "STP_PRIVATE_KEY_PATH not set. "
            "Point it to the RSA private key PEM file provided by STP."
        )
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
        with open(key_path, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        signature = private_key.sign(
            cadena.encode(),
            asym_padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode()
    except ImportError:
        raise DisbursementError(
            "cryptography package required for production signing. "
            "Run: pip install cryptography"
        )


def disburse(
    application_id: str,
    amount_mxn: float,
    clabe_destino: str,
    nombre_beneficiario: str,
    rfc_beneficiario: str = "XAXX010101000",  # generic RFC for unregistered
    concepto: str = "Prestamo Olin",
) -> DisbursementResult:
    """
    Send a SPEI transfer to the merchant's CLABE.

    In sandbox mode, posts to demo.stpmex.com and returns the response folio.
    In production mode, signs with the RSA private key and posts to prod.

    Returns DisbursementResult. Raises DisbursementError on config issues.
    The caller should catch requests.RequestException for network failures.
    """
    validate_runtime_environment()
    if not math.isfinite(amount_mxn) or amount_mxn <= 0:
        raise DisbursementError("Disbursement amount must be greater than zero")
    if not validate_clabe(clabe_destino):
        raise DisbursementError("Destination CLABE is invalid or has a bad checksum")
    if not nombre_beneficiario.strip():
        raise DisbursementError("Beneficiary name is required")

    empresa         = _empresa()
    cuenta_ord      = _cuenta_ordenante()
    rfc_ord         = _rfc_ordenante()
    folio_origen    = _folio_origen(application_id)
    fecha_op        = int(datetime.now(timezone.utc).strftime("%Y%m%d"))
    folio_int       = int(time.time()) % 10_000_000   # 7-digit int folio

    # Detect destination bank institution code from CLABE prefix
    clabe_prefix    = clabe_destino[:3] if len(clabe_destino) >= 3 else "000"
    institucion     = _CLABE_TO_STP_CODE.get(clabe_prefix, 90646)

    payload = {
        "empresa":               empresa,
        "folio":                 folio_int,
        "fechaOperacion":        fecha_op,
        "claveRastreo":          folio_origen,
        "institucionContraparte": institucion,
        "tipoPago":              1,
        "monto":                 round(amount_mxn, 2),
        "nombreBeneficiario":    nombre_beneficiario[:40],
        "cuentaBeneficiario":    clabe_destino,
        "rfcCurpBeneficiario":   rfc_beneficiario or "XAXX010101000",
        "conceptoPago":          concepto[:40],
        "nombreOrdenante":       "OLIN CREDITO SA",
        "cuentaOrdenante":       cuenta_ord,
        "rfcCurpOrdenante":      rfc_ord,
    }

    payload["firma"] = _sign_payload(payload)

    cert_path = os.getenv("STP_CERT_PATH", "").strip()
    key_path  = os.getenv("STP_PRIVATE_KEY_PATH", "").strip()
    cert      = (cert_path, key_path) if (cert_path and key_path and not _is_sandbox()) else None

    try:
        resp = requests.post(
            f"{_base_url()}/ordenPago/registra",
            json=payload,
            cert=cert,
            timeout=30,
            verify=not _is_sandbox(),   # skip SSL verification on sandbox
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return DisbursementResult(
            application_id=application_id,
            folio_stp=None,
            folio_origen=folio_origen,
            status="failed",
            amount_mxn=amount_mxn,
            clabe_destino=clabe_destino,
            error=str(e),
        )

    # STP returns {"resultado": {"id": 12345, "descripcionError": null}} on success
    resultado = data.get("resultado") or data
    folio_stp = str(resultado.get("id", "")) or None
    error_desc = resultado.get("descripcionError") or resultado.get("error")

    if error_desc:
        return DisbursementResult(
            application_id=application_id,
            folio_stp=folio_stp,
            folio_origen=folio_origen,
            status="failed",
            amount_mxn=amount_mxn,
            clabe_destino=clabe_destino,
            error=error_desc,
        )

    status = "sandbox" if _is_sandbox() else "sent"
    return DisbursementResult(
        application_id=application_id,
        folio_stp=folio_stp or folio_origen,
        folio_origen=folio_origen,
        status=status,
        amount_mxn=amount_mxn,
        clabe_destino=clabe_destino,
    )


# CLABE prefix (first 3 digits) → STP institution code
# https://www.banxico.org.mx/sistemas-de-pago/codi/participantes.html
_CLABE_TO_STP_CODE: dict[str, int] = {
    "002": 2,      # Banamex / Citibanamex
    "006": 6,      # BBVA México
    "012": 12,     # BBVA Bancomer (legacy)
    "014": 14,     # Santander
    "021": 21,     # HSBC
    "030": 30,     # Bajío
    "036": 36,     # Inbursa
    "044": 44,     # Scotiabank
    "058": 58,     # Banregio
    "059": 59,     # Invex
    "072": 72,     # Banorte
    "106": 106,    # BAMSA
    "108": 108,    # Tokio
    "110": 110,    # JP Morgan
    "112": 112,    # Bansí
    "113": 113,    # Banco del Ejército
    "116": 116,    # ING
    "124": 124,    # Deutsche
    "126": 126,    # Credit Suisse
    "127": 127,    # Azteca
    "128": 128,    # Agro Crédito
    "129": 129,    # ABC Capital
    "130": 130,    # UBS Bank
    "132": 132,    # Multiva
    "133": 133,    # Actinver
    "135": 135,    # NAFIN
    "136": 136,    # HSBC (empresas)
    "138": 138,    # HSBC Afore
    "141": 141,    # Ve por Más
    "145": 145,    # BBASE
    "147": 147,    # Banxico
    "148": 148,    # BBVA Bancomer (empresas)
    "149": 149,    # SCOTIAB (empresas)
    "155": 155,    # ICBC
    "156": 156,    # Sabadell
    "168": 168,    # HIPOTECARIA FED
    "600": 600,    # Monexcb
    "601": 601,    # GBM
    "602": 602,    # Bamx
    "605": 605,    # Valué
    "606": 606,    # FONDIVISA
    "608": 608,    # FINCOMUN
    "611": 611,    # HDIVISA
    "613": 613,    # Multiva Cbolsa
    "616": 616,    # Finanzen
    "617": 617,    # VALMEX
    "618": 618,    # ÚNICA
    "621": 621,    # CIBANCO
    "622": 622,    # AFIRME
    "623": 623,    # BANORTE IXE
    "626": 626,    # CBDEUTSCHE
    "627": 627,    # ZURICHVI
    "628": 628,    # ZURICHVIDA
    "629": 629,    # SU CASITA
    "630": 630,    # EVERCORE
    "631": 631,    # HSBC (dls)
    "632": 632,    # HDFM
    "633": 633,    # CCIFIN
    "634": 634,    # VE POR MAS
    "636": 636,    # HDI SEGUROS
    "637": 637,    # ORDER
    "638": 638,    # AKALA
    "640": 640,    # CB JP MORGAN
    "642": 642,    # REFORMA
    "646": 646,    # STP (SPEI directo)
    "648": 648,    # EVERCORE (dls)
    "649": 649,    # INMOBILIARIA
    "651": 651,    # Seguro Ahorro Banorte
    "652": 652,    # ASEA
    "653": 653,    # KUSPIT
    "655": 655,    # SOFIEXPRESS
    "656": 656,    # UNAGRA
    "659": 659,    # ASP INTEGRA OPC
    "670": 670,    # FONDEA
    "674": 674,    # AXA
    "677": 677,    # CAJA POP MEXICANA
    "679": 679,    # FND
    "684": 684,    # TRANSFER
    "685": 685,    # FONDO (FIRA)
    "686": 686,    # INVERCAP
    "689": 689,    # FINCI
    "699": 699,    # CoDi Valida
    "706": 706,    # ARCUS
    "710": 710,    # TELECOMUNICACIONES
    "711": 711,    # ANCIENTUM
    "713": 713,    # MULTINET
    "716": 716,    # INBURSA
    "723": 723,    # CUENCA
    "728": 728,    # SPIN
    "730": 730,    # NVIO
    "732": 732,    # MERCADO PAGO
    "733": 733,    # CUENTACERO
    "734": 734,    # INDEVAL
    "736": 736,    # PAGOPRO
    "741": 741,    # BNET
    "742": 742,    # STP VIASAT
    "743": 743,    # TEMPORAL
    "744": 744,    # BANORTE AHORRO
    "745": 745,    # BBASE INVERSION
    "746": 746,    # ABC CAPITAL
    "747": 747,    # KUSPIT CTES
    "748": 748,    # LIBERTAD
    "749": 749,    # FICREA
    "901": 901,    # CoDi
}
