#!/usr/bin/env python3
"""
Olin · Simulateur onboarding WhatsApp

Poses 11 questions in terminal, connects Places API + Syncfy sandbox,
runs the scoring engine (with portfolio + graduation checks), and saves
to olin_scoring.db.

Usage:
    cd /Users/pc/Downloads/olin_scoring_mvp_1
    python3 onboard.py
"""
from __future__ import annotations

import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from olin.models import (
    Application, BusinessType, BuroData,
    FMCGData, BankData, TenureData, IMSSPayrollData, FraudData,
)
from olin.scorecard import score_application
from olin.store import ScoringLog
from olin.places import get_maps_data
from olin.imss import validate_rfc
from olin.portfolio import check_portfolio
from olin.graduation import get_graduation_offer
from olin.config import default_db_path, mocks_allowed, runtime_mode
from olin.stp import validate_clabe

DB_PATH = default_db_path(ROOT)

CLABE_BANKS = {
    "002": "Banamex", "006": "BBVA", "012": "BBVA Bancomer",
    "021": "HSBC",    "072": "Banorte", "014": "Santander",
    "058": "Banregio", "044": "Scotiabank",
}
SYNCFY_BANKS = {"Banamex", "BBVA", "BBVA Bancomer", "HSBC", "Banorte"}

# ── ANSI colors ───────────────────────────────────────────────────────
R   = "\033[0m"
B   = "\033[1m"
MU  = "\033[90m"
GR  = "\033[92m"
AM  = "\033[93m"
RD  = "\033[91m"
CY  = "\033[96m"
BL  = "\033[94m"

def bold(s):  return f"{B}{s}{R}"
def green(s): return f"{GR}{s}{R}"
def amber(s): return f"{AM}{s}{R}"
def red(s):   return f"{RD}{s}{R}"
def muted(s): return f"{MU}{s}{R}"
def cyan(s):  return f"{CY}{s}{R}"
def blue(s):  return f"{BL}{s}{R}"

# ── UI primitives ─────────────────────────────────────────────────────
def bot(msg):   print(f"\n  {CY}🤖{R}  {msg}")
def ok(msg="Recibido."): print(f"  {GR}✓{R}  {muted(msg)}")
def warn(msg):  print(f"  {AM}⚠{R}  {amber(msg)}")
def step(msg):  print(f"\n  {MU}⟳{R}  {msg}", end="", flush=True)
def step_done(suffix=" ✓"): print(green(suffix))
def step_fail(suffix):      print(f" {amber(suffix)}")
def sep(char="─", width=58): print(f"\n  {muted(char * width)}")

def ask(prompt, hint=""):
    hint_str = f"  {muted(hint)}\n" if hint else ""
    print(hint_str, end="")
    try:
        return input(f"  {CY}›{R}  ").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n\n  {muted('Interrumpido.')}\n")
        sys.exit(0)

def ask_validated(prompt, hint, validate, error_msg):
    while True:
        val = ask(prompt, hint)
        if validate(val):
            return val
        warn(error_msg)

# ── Score / signal bars ───────────────────────────────────────────────
def score_bar(score, ci_low, ci_hi, width=36):
    bar = []
    for i in range(width):
        pos = i / width * 100
        if i < round(score / 100 * width):
            bar.append(f"{RD if pos<50 else (AM if pos<75 else GR)}█{R}")
        else:
            bar.append(f"{MU}░{R}")
    for bound in (ci_low, ci_hi):
        idx = round(bound / 100 * width)
        if 0 <= idx < width:
            bar[idx] = f"{MU}│{R}"
    return "".join(bar)

def sig_mini_bar(score, width=18):
    filled = round(score / 100 * width)
    color = GR if score >= 70 else (AM if score >= 40 else RD)
    return f"{color}{'█'*filled}{MU}{'░'*(width-filled)}{R}"

SIG_LABELS = {
    "fmcg_purchase_history":  "FMCG Compras   ",
    "bank_cash_flow":         "Banco / Syncfy ",
    "business_tenure":        "Antigüedad     ",
    "pos_transaction_volume": "POS Volume     ",
    "google_maps_rating":     "Google Maps    ",
    "imss_payroll":           "IMSS Nómina    ",
}

# ── Syncfy sandbox connection ─────────────────────────────────────────
def try_syncfy(bank_name, merchant_name=""):
    try:
        from olin.syncfy import create_link_and_fetch, SYNCFY_TEST_SITE_ID
        bank, _ = create_link_and_fetch(SYNCFY_TEST_SITE_ID, "test", "test")
        return bank
    except EnvironmentError:
        step_fail("SYNCFY_API_KEY no configurada — usando mock sandbox")
    except Exception as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        if code == 402 or "402" in str(exc):
            step_fail("plan Syncfy no incluye credentials — usando mock sandbox")
        else:
            step_fail(f"conexión fallida ({type(exc).__name__}) — usando mock sandbox")
    if not mocks_allowed():
        step_fail("producción: no se permiten datos bancarios sintéticos")
        return None
    # Demo-only deterministic fallback
    from olin.bank_mock import mock_bank
    bank = mock_bank(merchant_name or bank_name)
    if bank:
        step_done(f" [mock]  balance {bank.avg_daily_balance_mxn:,.0f} MXN · "
                  f"depósitos {bank.monthly_deposit_volume_mxn:,.0f}/mo")
    else:
        step_done(" [mock]  cash_only — sin señal bancaria")
    return bank


# ── Main flow ─────────────────────────────────────────────────────────
def main():
    print()
    print(f"  Mode: {runtime_mode().upper()} · DB: {DB_PATH.name}")
    print(f"  {B}╔══════════════════════════════════════════════════════╗{R}")
    print(f"  {B}║   Olin · Simulador Onboarding WhatsApp               ║{R}")
    print(f"  {B}╚══════════════════════════════════════════════════════╝{R}")
    bot("Hola! Soy Olin. Voy a analizar tu solicitud de crédito.\n"
        f"  {MU}     Voy a hacerte 13 preguntas rápidas.{R}")

    # ── Q1: Nombre del comercio ────────────────────────────────────────
    sep()
    bot(f"{bold('1/12')}  ¿Cuál es el nombre de tu negocio?")
    merchant_name = ask_validated(
        "nombre", "", lambda v: len(v) >= 2,
        "El nombre debe tener al menos 2 caracteres.",
    )
    ok()

    # ── Q2: Tipo de negocio ────────────────────────────────────────────
    sep()
    bot(f"{bold('2/12')}  ¿Qué tipo de negocio es?")
    TYPE_MAP = {
        "abarrotes": BusinessType.ABARROTES,
        "taqueria":  BusinessType.TAQUERIA,
        "jugueria":  BusinessType.JUGUERIA,
        "other":     BusinessType.OTHER,
    }
    biz_type_str = ask_validated(
        "tipo", "abarrotes · taqueria · jugueria · other",
        lambda v: v.lower() in TYPE_MAP,
        "Elige: abarrotes / taqueria / jugueria / other",
    )
    biz_type = TYPE_MAP[biz_type_str.lower()]
    ok()

    # ── Q3: Colonia ────────────────────────────────────────────────────
    sep()
    bot(f"{bold('3/12')}  ¿En qué colonia está el negocio?")
    colonia = ask_validated(
        "colonia", "", lambda v: len(v) >= 2,
        "Ingresa una colonia válida.",
    )
    ok()

    # ── Q4: Monto solicitado ───────────────────────────────────────────
    sep()
    bot(f"{bold('4/12')}  ¿Cuánto crédito necesitas? (MXN)")
    def parse_amount(v):
        try:
            return float(v.replace(",","").replace("$","").replace(" ","")) > 0
        except ValueError:
            return False
    amount_str = ask_validated(
        "monto", "Ejemplo: 20000", parse_amount,
        "Ingresa un monto numérico positivo (sin comas ni $).",
    )
    requested_amount = float(amount_str.replace(",","").replace("$","").strip())
    ok()

    # ── Q5: Dirección Google Maps ──────────────────────────────────────
    sep()
    bot(f"{bold('5/12')}  ¿Cuál es la dirección completa del negocio?\n"
        f"  {MU}     (Se usará para buscar en Google Maps){R}")
    maps_address = ask_validated(
        "dirección", "Ejemplo: Abarrotes La Lupita, Iztapalapa, CDMX",
        lambda v: len(v) >= 5,
        "Ingresa una dirección con al menos 5 caracteres.",
    )
    ok()

    # ── Q6: Banco ──────────────────────────────────────────────────────
    sep()
    bot(f"{bold('6/12')}  ¿Tiene cuenta en BBVA, Banamex, Banorte o HSBC?")
    has_syncfy_bank = ask_validated(
        "banco", "si / no  (si = conectamos Syncfy, no = upload manual)",
        lambda v: v.lower() in ("oui","si","sí","s","yes","y","non","no","n"),
        "Responde: si / no",
    )
    syncfy_eligible = has_syncfy_bank.lower() in ("oui","si","sí","s","yes","y")
    ok()

    # ── Q7: CLABE ─────────────────────────────────────────────────────
    sep()
    bot(f"{bold('7/12')}  ¿Cuál es la CLABE del comerciante?")
    clabe = ask_validated(
        "CLABE", "18 dígitos — se almacenará de forma segura",
        lambda v: validate_clabe(v.replace(" ", "")),
        "La CLABE debe tener 18 dígitos y un dígito verificador válido.",
    )
    clabe = clabe.replace(" ","")
    detected_bank = CLABE_BANKS.get(clabe[:3], "banco desconocido")
    ok(f"Recibido. Banco detectado: {bold(detected_bank)}")

    # ── Q8: FEMSA / Bimbo ─────────────────────────────────────────────
    sep()
    bot(f"{bold('8/12')}  ¿Está confirmada la entrega de FEMSA o Bimbo?")
    fmcg_confirm = ask_validated(
        "distribuidor", "si / no",
        lambda v: v.lower() in ("oui","si","sí","s","yes","y","non","no","n"),
        "Responde: si / no",
    )
    distributor_confirmed = fmcg_confirm.lower() in ("oui","si","sí","s","yes","y")
    ok(f"FEMSA/Bimbo: {'confirmado ✓' if distributor_confirmed else 'no confirmado'}")

    # ── Q9: RFC ───────────────────────────────────────────────────────
    sep()
    bot(f"{bold('9/13')}  ¿Cuál es el RFC del comerciante?")
    def _valid_rfc(v):
        return not v.strip() or validate_rfc(v)["valid"]
    rfc_raw = ask_validated(
        "RFC", "Ejemplo: GASA850101AB2  (deja vacío si no lo tienes)",
        _valid_rfc,
        "RFC inválido. Revisa el formato (ej: GAPC850101AB2) o deja vacío.",
    )
    rfc_info = validate_rfc(rfc_raw) if rfc_raw.strip() else {"valid": False, "type": None}
    if rfc_raw.strip() and rfc_info["valid"]:
        ok(f"RFC válido ({rfc_info['type']}, fecha {rfc_info.get('entity_date', '?')})")
    elif not rfc_raw.strip():
        warn("RFC no proporcionado — verificar antes del desembolso")

    # ── Q10: CURP ─────────────────────────────────────────────────────
    sep()
    bot(f"{bold('10/13')}  ¿Cuál es el CURP del comerciante?")
    import re as _re
    _CURP_RE = _re.compile(
        r'^[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d$', _re.IGNORECASE
    )
    def _valid_curp(v):
        return not v.strip() or bool(_CURP_RE.match(v.strip().upper()))
    curp_raw = ask_validated(
        "CURP", "18 caracteres  (deja vacío si no lo tienes)",
        _valid_curp,
        "CURP inválido. Debe tener 18 caracteres (ej: GASA850101HDFRRN09). Deja vacío si no tienes.",
    )
    curp_raw = curp_raw.strip().upper()
    if curp_raw:
        ok(f"CURP {curp_raw[:4]}************** registrado ✓")
    else:
        warn("CURP no proporcionado — identity score reducido en fraud gate")

    # ── Q11: Teléfono ─────────────────────────────────────────────────
    sep()
    bot(f"{bold('11/13')}  ¿Cuál es el teléfono celular del comerciante?")
    phone_raw = ask("teléfono", "10 dígitos MX (sin +52)")
    if phone_raw.strip():
        ok("Teléfono registrado")
    else:
        warn("Teléfono no proporcionado")

    # ── Q12: INE verificado ────────────────────────────────────────────
    sep()
    bot(f"{bold('12/13')}  ¿Se ha verificado el INE/IFE del comerciante?")
    ine_str = ask_validated(
        "INE", "si = verificado físicamente · no = pendiente",
        lambda v: v.lower() in ("oui","si","sí","s","yes","y","non","no","n"),
        "Responde: si / no",
    )
    ine_checked = ine_str.lower() in ("oui","si","sí","s","yes","y")
    if ine_checked:
        ok("INE verificado ✓")
    else:
        warn("INE pendiente — requerido antes del desembolso (hard block en Gate 0)")

    # ── Q13: Círculo de Crédito ────────────────────────────────────────
    sep()
    bot(f"{bold('13/13')}  ¿Se realizó consulta a {bold('Círculo de Crédito')}?")
    buro_str = ask_validated(
        "Círculo", "si = consultado · no = sin expediente",
        lambda v: v.lower() in ("oui","si","sí","s","yes","y","non","no","n"),
        "Responde: si / no",
    )
    buro_checked = buro_str.lower() in ("oui","si","sí","s","yes","y")
    buro_delinquencies = 0
    buro_loans = 0
    buro_score_val = None

    if buro_checked:
        ok("Círculo de Crédito consultado ✓")
        from olin.scorecard import CIRCULO_HIGH_BAND, CIRCULO_MID_BAND
        def _parse_int(v): return v.isdigit()

        # Numeric score (300-850)
        def _valid_score(v):
            return v.isdigit() and 300 <= int(v) <= 850
        score_str = ask_validated(
            "score", "Puntaje Círculo 300-850",
            _valid_score, "Ingresa un número entre 300 y 850.",
        )
        if score_str.strip():
            buro_score_val = int(score_str.strip())
            if buro_score_val >= CIRCULO_HIGH_BAND:
                ok(f"Círculo {bold(str(buro_score_val))} → {green('C1')} banda alta — elegible AUTO_APPROVE")
            elif buro_score_val >= CIRCULO_MID_BAND:
                ok(f"Círculo {bold(str(buro_score_val))} → {amber('C2')} banda media — máximo COMMITTEE")
            else:
                warn(f"Círculo {buro_score_val} → C4 banda baja (<{CIRCULO_MID_BAND}) · DECLINE automático")

        delq_str = ask_validated(
            "delinquencias", "Créditos con atraso activo (0 si ninguno)",
            _parse_int, "Ingresa un número entero ≥ 0",
        )
        buro_delinquencies = int(delq_str)
        loans_str = ask_validated(
            "créditos activos", "Total de créditos activos en Círculo",
            _parse_int, "Ingresa un número entero ≥ 0",
        )
        buro_loans = int(loans_str)

        if buro_delinquencies > 0:
            warn(f"Círculo: {buro_delinquencies} delinquencia(s) activa(s) → C4 · DECLINE automático")
        elif buro_loans >= 3:
            warn(f"Círculo: {buro_loans} créditos activos → multi-lending soft-flag (downgrade DSCR)")
        elif buro_score_val and buro_score_val >= CIRCULO_HIGH_BAND:
            ok(f"Círculo limpio: score {buro_score_val} · {buro_loans} crédito(s) → C1")
        elif buro_score_val:
            ok(f"Círculo: score {buro_score_val} · {buro_loans} crédito(s) → C2")
    else:
        warn("Sin expediente en Círculo de Crédito → C3 · máximo COMMITTEE, nunca AUTO_APPROVE")

    buro_data = BuroData(
        checked=buro_checked,
        active_delinquencies=buro_delinquencies,
        active_loans_count=buro_loans,
        score=buro_score_val,
    ) if buro_checked else BuroData(checked=False)

    # ── Processing ─────────────────────────────────────────────────────
    print()
    sep("═")
    print(f"\n  {bold('Analizando solicitud...')}\n")

    # Google Maps / Places
    step("Google Maps · Places API...")
    maps_data, tenure_data = None, None
    try:
        maps_data, tenure_data = get_maps_data(maps_address)
        if maps_data:
            step_done(f" ✓  {maps_data.rating}★ · {maps_data.review_count} reseñas · "
                      f"antigüedad ~{tenure_data.years_on_google_maps:.1f} años")
        else:
            step_fail("negocio no encontrado en Google Maps")
    except Exception as exc:
        step_fail(f"Places API error: {exc}")

    # Syncfy
    bank_data = None
    if syncfy_eligible:
        step(f"Syncfy sandbox · {detected_bank}...")
        if detected_bank in SYNCFY_BANKS:
            bank_data = try_syncfy(detected_bank, merchant_name)
        else:
            step_fail(f"{detected_bank} no está en la lista Syncfy (BBVA/Banamex/Banorte/HSBC)")
    else:
        step("Banco · upload manual")
        step_fail("señal bancaria ausente (upload manual no implementado aún)")

    # FMCG — inject mock purchase history when distributor is confirmed
    _fmcg_data = None
    if distributor_confirmed and mocks_allowed():
        from olin.fmcg_mock import mock_fmcg
        from olin.signals import score_fmcg
        _fmcg_data = mock_fmcg(merchant_name)
        _fsc, _fexpl = score_fmcg(_fmcg_data)
        step(f"FEMSA/Bimbo · historial compras...")
        step_done(f" [mock]  {_fmcg_data.months_of_history:.0f} meses · "
                  f"{_fmcg_data.weekly_purchase_rate*100:.0f}% cadencia · "
                  f"score {_fsc:.0f}")
    elif distributor_confirmed:
        step("FEMSA/Bimbo · historial compras...")
        step_fail("producción: falta evidencia verificada; no se inyectó mock")

    # Build Application
    maps_full_address = maps_address if maps_data else None
    app = Application(
        merchant_name=merchant_name,
        business_type=biz_type,
        requested_amount_mxn=requested_amount,
        colonia=colonia,
        clabe=clabe,
        # Provide FMCGData with realistic purchase history when confirmed.
        # mock_fmcg is deterministic on merchant_name so reruns are consistent.
        fmcg=_fmcg_data,
        bank=bank_data,
        tenure=tenure_data,
        pos=None,
        maps=maps_data,
        imss=None,
        buro=buro_data,
        fraud=FraudData(
            phone_mx=phone_raw.strip(),
            rfc=rfc_raw.strip().upper(),
            curp=curp_raw,
            ine_checked=ine_checked,
            address_stated=maps_address,
        ),
    )

    # Portfolio check
    step("Portafolio · límites de concentración...")
    pf_block = check_portfolio(app, str(DB_PATH))
    if pf_block.blocked:
        step_fail(" bloqueado")
        for r in pf_block.reasons:
            warn(r)
    else:
        step_done()
        for w in pf_block.warnings:
            warn(f"Portafolio: {w}")

    # Graduation check
    step("Historial de crédito · tier...")
    graduation = get_graduation_offer(clabe, str(DB_PATH))
    if graduation.tier > 0:
        step_done(
            f" ✓  Tier {graduation.tier} · cap MXN {graduation.max_ticket_mxn:,.0f}"
            f" · {graduation.pricing_rate:.1%}/mes"
        )
        for n in graduation.notes:
            ok(n)
    else:
        step_done(" ✓  Nuevo cliente · Tier 0")

    # Scoring
    step("Scoring engine...")
    result = score_application(
        app,
        maps_address=maps_full_address,
        bank_stated=detected_bank if syncfy_eligible else None,
        portfolio_block=pf_block,
        graduation=graduation,
    )
    step_done()

    # Save
    step(f"Guardando en {DB_PATH.name}...")
    log = ScoringLog(str(DB_PATH))
    log.log(app, result)
    if graduation.tier > 0:
        log.conn.execute(
            "UPDATE scoring_log SET graduation_tier=? WHERE application_id=?",
            (graduation.tier, app.application_id),
        )
        log.conn.commit()
    step_done()

    # ── Result display ─────────────────────────────────────────────────
    d = result.decision.value
    if d == "AUTO_APPROVE":
        decision_str = green(bold("✅  AUTO_APPROVE"))
        score_color  = GR
    elif d in ("COMMITTEE", "MANUAL_REVIEW"):
        decision_str = amber(bold("🟡  COMMITTEE"))
        score_color  = AM
    else:
        decision_str = red(bold("❌  DECLINE"))
        score_color  = RD

    sep("═")
    tier_label = ""
    if result.tier > 0:
        tier_color = GR if result.tier == 1 else (AM if result.tier <= 12 else RD)
        tier_label = f"  {tier_color}{bold(f'Tier {result.tier}')}{R}"

    print(f"\n  {bold('RESULTADO FINAL')} — {bold(merchant_name)}{tier_label}")
    sep("═")

    print(f"\n  Score    {score_color}{bold(f'{result.score:.1f}')}{R}"
          f"   {muted(f'CI [{result.ci_low:.1f} – {result.ci_high:.1f}]')}")
    print(f"  {score_bar(result.score, result.ci_low, result.ci_high)}")
    ruler = "0" + " " * 14 + "50" + " " * 10 + "75" + " " * 8 + "100"
    print(f"  {muted(ruler)}")
    print(f"  Coverage {bold(f'{result.data_coverage:.0%}')}\n")

    print(f"  {decision_str}\n")

    for reason in result.decision_reasons:
        print(f"  {muted('•')} {reason}")
    for fail in result.hard_filter_failures:
        print(f"  {RD}⚠{R} {red(fail)}")

    # Sensitivity / upgrade path
    sens = result.tier_sensitivity or {}
    path = sens.get("path", "")
    if path and path != "Optimal — no upgrade path needed":
        print(f"\n  {bold('UPGRADE PATH')}")
        for p in path.split(" · "):
            print(f"  {BL}↑{R}  {p}")

    # Loan terms
    print()
    print(f"  {muted('─' * 42)}")
    if result.approved_amount_mxn > 0:
        if result.approved_amount_mxn < app.requested_amount_mxn:
            print(f"  Monto solicitado  {muted('MXN')} {bold(f'{app.requested_amount_mxn:>10,.0f}')}")
            print(f"  {amber('Counter-offer')}     {muted('MXN')} {amber(bold(f'{result.approved_amount_mxn:>10,.0f}'))}")
        else:
            print(f"  Monto solicitado  {muted('MXN')} {bold(f'{app.requested_amount_mxn:>10,.0f}')}")
            print(f"  Monto aprobado    {muted('MXN')} {bold(f'{result.approved_amount_mxn:>10,.0f}')}")
        print(f"  Costo fijo        {muted('MXN')} {bold(f'{result.pricing_fixed_cost_mxn:>10,.0f}')}  "
              f"{muted('(60 días · 2 pagos)')}")
    else:
        print(f"  {red('Monto aprobado: MXN 0')}")
    print(f"  {muted('─' * 42)}")

    # Graduation offer (if repeat borrower)
    if graduation.tier > 0:
        print(f"\n  {bold('GRADUACIÓN')}")
        print(f"  {muted('─' * 42)}")
        print(f"  Tier {bold(str(graduation.tier))}  ·  "
              f"cap {muted('MXN')} {bold(f'{graduation.max_ticket_mxn:,.0f}')}  ·  "
              f"tasa {bold(f'{graduation.pricing_rate:.1%}')}/mes"
              + (f"  {GR}(early repayment bonus ✓){R}" if graduation.early_repayment_bonus else ""))
        for note in graduation.notes:
            print(f"  {GR}✓{R}  {muted(note)}")
        print(f"  {muted('─' * 42)}")

    # Portfolio warnings
    if pf_block.warnings:
        print(f"\n  {bold('PORTAFOLIO')}")
        print(f"  {muted('─' * 42)}")
        for w in pf_block.warnings:
            print(f"  {AM}⚠{R}  {amber(w)}")
        print(f"  {muted('─' * 42)}")

    # Repayment summary
    r = result.repayment
    if r and (r.dscr is not None or r.burden_ratio is not None):
        print(f"\n  {bold('REPAYMENT')}")
        print(f"  {muted('─' * 42)}")
        if r.dscr is not None:
            dc = GR if r.dscr >= 2.5 else (AM if r.dscr >= 1.5 else RD)
            print(f"  DSCR              {dc}{bold(f'{r.dscr:.2f}')}{R}"
                  f"  {muted('(≥2.5 auto · ≥1.5 review · <1.5 decline)')}")
        if r.burden_ratio is not None:
            brd_pct = r.burden_ratio * 100
            bc = GR if r.burden_ratio <= 0.25 else (AM if r.burden_ratio <= 0.40 else RD)
            print(f"  Burden ratio      {bc}{bold(f'{brd_pct:.1f}%')}{R}"
                  f"  {muted('of monthly inflows  (≤25% auto · ≤40% review)')}")
        if r.estimated_monthly_net_mxn is not None:
            print(f"  Net income/mo     {muted('MXN')} {bold(f'{r.estimated_monthly_net_mxn:>10,.0f}')}")
        if r.stress_buffer_ratio is not None:
            bc = GR if r.stress_buffer_ratio >= 1.0 else RD
            print(f"  Stress buffer     {bc}{bold(f'{r.stress_buffer_ratio:.2f}x')}{R}"
                  f"  {muted('worst-day balance / 2-day shock')}")
        for note in r.notes:
            print(f"  {AM}⚠{R}  {amber(note)}")
        print(f"  {muted('─' * 42)}")

    # Signals table
    print(f"\n  {bold('SEÑALES')}")
    print(f"  {muted('─' * 58)}")
    for s in result.signals:
        label = SIG_LABELS.get(s.name, s.name)
        if s.name == "imss_payroll":
            print(f"  {muted(label)}  {muted('SKIPPED')}  {muted('Phase 0 — no configurado')}")
            continue
        if not s.available:
            print(f"  {muted(label)}  {muted('MISSING')}  {muted(s.explanation)}")
        else:
            sc = GR if s.raw_score >= 70 else (AM if s.raw_score >= 40 else RD)
            tag = ""
            if s.name == "bank_cash_flow":
                tag = blue(" [Syncfy]") if not s.fallback_used else amber(f" [{s.fallback_used}]")
            elif s.name in ("google_maps_rating", "business_tenure"):
                tag = blue(" [Places]")
            print(f"  {label}  {sig_mini_bar(s.raw_score)}"
                  f"  {sc}{s.raw_score:5.1f}{R}"
                  f"  {muted(f'w={s.effective_weight:.2f}')}{tag}")
            print(f"  {' '*17}  {muted(s.explanation[:52])}")
    print(f"  {muted('─' * 58)}")

    # Fraud summary
    fa = result.fraud_assessment
    if fa:
        print(f"\n  {bold('FRAUD SCREENING')}")
        print(f"  {muted('─' * 42)}")
        rc = GR if fa.risk_score < 20 else (AM if fa.risk_score < 50 else RD)
        print(f"  Risk score  {rc}{bold(f'{fa.risk_score:.0f}/100')}{R}")
        checks_done = sum(1 for v in fa.checks.values() if v)
        print(f"  Checks OK   {bold(str(checks_done))}/{len(fa.checks)}")
        for block in fa.hard_blocks:
            print(f"  {RD}🔴{R} {red(block)}")
        for flag in fa.flags:
            print(f"  {AM}⚠{R}  {amber(flag)}")
        if not fa.hard_blocks and not fa.flags:
            print(f"  {GR}✓{R}  {muted('All fraud checks passed')}")
        print(f"  {muted('─' * 42)}")

    # Footer
    print(f"\n  {muted('Guardado →')} {bold(DB_PATH.name)}"
          f"  {muted('app')} {cyan(app.application_id)}")
    print(f"  {muted('CLABE')} {clabe[:6]}{'*'*10}{clabe[-2:]}"
          f"  {muted('·')}  {muted(detected_bank)}")
    sep("═")
    print()


if __name__ == "__main__":
    main()
