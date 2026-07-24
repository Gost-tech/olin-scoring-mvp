"""
Olin · Batch Scoring CLI

Score a CSV of merchant profiles and write results to a CSV.
Useful for pre-screening a colonia pipeline before a field visit.

Input CSV columns (all optional except merchant_name + business_type):
  merchant_name, business_type, requested_mxn, colonia,
  bank_deposit_mxn, bank_outflow_mxn, bank_regularity, bank_trend_90d,
  bank_min_balance_mxn, bank_months_connected, bank_avg_balance_mxn, bank_deposit_count,
  fmcg_months, fmcg_weekly_rate, fmcg_missed_weeks, fmcg_confirmed,
  fmcg_avg_weekly_mxn, fmcg_trend_3m,
  tenure_years_maps, tenure_years_imss,
  maps_rating, maps_review_count, maps_velocity_6m,
  buro_checked, buro_delinquencies, buro_active_loans,
  imss_employees

Usage:
    python3 -m olin.batch merchants.csv
    python3 -m olin.batch merchants.csv --out scored.csv
    python3 -m olin.batch merchants.csv --save-db  # also write to olin_scoring.db
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from olin.models import (
    Application, BusinessType, BuroData, FraudData,
    FMCGData, BankData, TenureData, POSData, MapsRatingData, IMSSPayrollData,
)
from olin.scorecard import score_application, _buro_dim, _dscr_dim, _score_dim

_BTYPE = {
    "abarrotes": BusinessType.ABARROTES,
    "taqueria":  BusinessType.TAQUERIA,
    "jugueria":  BusinessType.JUGUERIA,
}


def _f(row: dict, col: str, default: Optional[float] = None) -> Optional[float]:
    v = row.get(col, "").strip()
    if v == "" or v.lower() in ("none", "null", "na", "-"):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _b(row: dict, col: str, default: bool = False) -> bool:
    v = row.get(col, "").strip().lower()
    return v in ("1", "true", "yes", "si", "sí", "y") if v else default


def _build_app(row: dict) -> Application:
    btype = _BTYPE.get(row.get("business_type", "").strip().lower(), BusinessType.OTHER)

    bank: Optional[BankData] = None
    if _f(row, "bank_months_connected", 0) or _f(row, "bank_deposit_mxn", 0):
        bank = BankData(
            months_connected        = _f(row, "bank_months_connected", 0) or 0,
            avg_daily_balance_mxn   = _f(row, "bank_avg_balance_mxn", 0) or 0,
            monthly_deposit_count   = _f(row, "bank_deposit_count", 0) or 0,
            monthly_deposit_volume_mxn = _f(row, "bank_deposit_mxn", 0) or 0,
            monthly_outflow_volume_mxn = _f(row, "bank_outflow_mxn", 0) or 0,
            deposit_regularity      = _f(row, "bank_regularity", 0.5) or 0.5,
            overdrafts_90d          = int(_f(row, "bank_overdrafts_90d", 0) or 0),
            balance_trend_90d       = _f(row, "bank_trend_90d", 0.0) or 0.0,
            min_daily_balance_mxn   = _f(row, "bank_min_balance_mxn", 0) or 0,
        )

    fmcg: Optional[FMCGData] = None
    if _f(row, "fmcg_months", 0):
        fmcg = FMCGData(
            months_of_history       = _f(row, "fmcg_months", 0) or 0,
            weekly_purchase_rate    = _f(row, "fmcg_weekly_rate", 0.5) or 0.5,
            missed_weeks_last_12    = int(_f(row, "fmcg_missed_weeks", 0) or 0),
            avg_weekly_purchase_mxn = _f(row, "fmcg_avg_weekly_mxn", 0) or 0,
            distributor_confirmed   = _b(row, "fmcg_confirmed"),
            trend_3m                = _f(row, "fmcg_trend_3m", 0.0) or 0.0,
        )

    tenure: Optional[TenureData] = None
    if _f(row, "tenure_years_maps") is not None or _f(row, "tenure_years_imss") is not None:
        tenure = TenureData(
            years_on_google_maps = _f(row, "tenure_years_maps", 0) or 0,
            years_in_imss        = _f(row, "tenure_years_imss", 0) or 0,
        )

    maps: Optional[MapsRatingData] = None
    if _f(row, "maps_rating") is not None:
        maps = MapsRatingData(
            rating           = _f(row, "maps_rating", 0) or 0,
            review_count     = int(_f(row, "maps_review_count", 0) or 0),
            review_velocity_6m = int(_f(row, "maps_velocity_6m", 0) or 0),
        )

    buro: Optional[BuroData] = None
    if _b(row, "buro_checked"):
        buro = BuroData(
            checked               = True,
            active_delinquencies  = int(_f(row, "buro_delinquencies", 0) or 0),
            active_loans_count    = int(_f(row, "buro_active_loans", 0) or 0),
        )

    imss: Optional[IMSSPayrollData] = None
    if _f(row, "imss_employees") is not None:
        imss = IMSSPayrollData(registered_employees=int(_f(row, "imss_employees", 0) or 0))

    return Application(
        merchant_name        = row.get("merchant_name", "Unknown").strip(),
        business_type        = btype,
        requested_amount_mxn = _f(row, "requested_mxn", 20_000) or 20_000,
        colonia              = row.get("colonia", "").strip(),
        fmcg=fmcg, bank=bank, tenure=tenure, maps=maps,
        imss=imss, buro=buro,
        fraud=FraudData(ine_checked=True),  # batch mode: assume KYC done
    )


OUTPUT_COLS = [
    "row", "merchant_name", "business_type", "colonia", "requested_mxn",
    "tier", "decision", "score", "ci_low", "ci_high",
    "approved_mxn", "dscr", "buro_dim", "dscr_dim", "score_dim",
    "upgrade_path",
]


def run_batch(input_path: str, output_path: Optional[str], save_db: bool) -> None:
    out_path = output_path or input_path.replace(".csv", "_scored.csv")

    _G = "\033[92m"; _A = "\033[93m"; _R = "\033[91m"; _M = "\033[90m"
    _B = "\033[1m";  _X = "\033[0m"

    from olin.store import ScoringLog
    db_ctx = ScoringLog(str(ROOT / "olin_scoring.db")) if save_db else None

    with open(input_path, newline="", encoding="utf-8-sig") as fin, \
         open(out_path,   "w", newline="", encoding="utf-8") as fout:

        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=OUTPUT_COLS)
        writer.writeheader()

        print(f"\n  {_B}Olin · Batch Scoring{_X}  {_M}← {input_path}{_X}")
        print(f"  {_M}{'─' * 78}{_X}")
        print(f"  {_B}{'#':<4}  {'Merchant':<32}  {'Tier':>4}  {'Decision':<13}  "
              f"{'Score':>5}  {'DSCR':>5}{_X}")
        print(f"  {'─' * 76}")

        n_auto = n_committee = n_decline = 0

        for i, row in enumerate(reader, 1):
            try:
                app = _build_app(row)
                result = score_application(app)
            except Exception as exc:
                print(f"  {_R}ERR row {i}: {exc}{_X}")
                continue

            if db_ctx:
                db_ctx.log(app, result)

            dscr = result.repayment.dscr if result.repayment else None
            dscr_s = f"{dscr:.2f}" if dscr is not None else "—"
            sens = result.tier_sensitivity or {}

            bd = _buro_dim(app.buro)
            dd = _dscr_dim(result.repayment) if result.repayment else "D3"
            sd = _score_dim(result.score)

            dec = result.decision.value
            col = _G if dec == "AUTO_APPROVE" else (_A if dec == "COMMITTEE" else _R)
            if dec == "AUTO_APPROVE": n_auto += 1
            elif dec == "COMMITTEE":  n_committee += 1
            else:                     n_decline += 1

            print(f"  {i:<4}  {app.merchant_name[:32]:<32}  {col}{result.tier:>4}{_X}  "
                  f"{col}{dec:<13}{_X}  {result.score:>5.1f}  {dscr_s:>5}")

            writer.writerow({
                "row": i,
                "merchant_name": app.merchant_name,
                "business_type": app.business_type.value,
                "colonia": app.colonia,
                "requested_mxn": app.requested_amount_mxn,
                "tier": result.tier,
                "decision": dec,
                "score": round(result.score, 1),
                "ci_low": result.ci_low,
                "ci_high": result.ci_high,
                "approved_mxn": result.approved_amount_mxn,
                "dscr": dscr_s,
                "buro_dim": bd,
                "dscr_dim": dd,
                "score_dim": sd,
                "upgrade_path": sens.get("path", ""),
            })

        total = n_auto + n_committee + n_decline
        print(f"  {'─' * 76}")
        print(f"  {_B}Total {total}{_X}  {_G}AUTO {n_auto}{_X}  "
              f"{_A}COMMITTEE {n_committee}{_X}  {_R}DECLINE {n_decline}{_X}")
        print(f"  Output → {_B}{out_path}{_X}\n")

    if db_ctx:
        db_ctx.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Olin batch scoring")
    parser.add_argument("input", help="Input CSV path")
    parser.add_argument("--out", help="Output CSV path (default: input_scored.csv)")
    parser.add_argument("--save-db", action="store_true",
                        help="Also log results to olin_scoring.db")
    args = parser.parse_args()
    run_batch(args.input, args.out, args.save_db)


if __name__ == "__main__":
    main()
