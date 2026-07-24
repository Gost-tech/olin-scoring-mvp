"""
Olin - Weight Calibration (outcome feedback loop)

Reads repayment outcomes from the SQLite log and computes whether the
current hardcoded signal weights actually predict default.

Two outputs:
  1. Per-signal predictive power (AUC proxy via rank correlation)
  2. Logistic regression weights — what the data says vs what we designed

Logistic regression is implemented from scratch (no scipy/sklearn needed).
Uses gradient descent with L2 regularization.

Usage:
    cd /Users/pc/Downloads/olin_scoring_mvp_1
    python3 -m olin.calibration
    python3 -m olin.calibration --db path/to/olin_scoring.db --min-samples 10
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
from pathlib import Path
from typing import Optional

SIGNAL_NAMES = [
    "fmcg_purchase_history",
    "bank_cash_flow",
    "business_tenure",
    "pos_transaction_volume",
    "google_maps_rating",
    "imss_payroll",
]

DESIGNED_WEIGHTS = {
    "fmcg_purchase_history": 0.25,
    "bank_cash_flow":        0.25,
    "business_tenure":       0.20,
    "pos_transaction_volume":0.15,
    "google_maps_rating":    0.10,
    "imss_payroll":          0.05,
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_training_rows(db_path: str) -> list[dict]:
    """
    Load loans with known repayment outcome.
    Extracts per-signal sub-scores from raw_result JSON.
    """
    from .store import ScoringLog
    ScoringLog(db_path).conn.close()  # ensure current schema migrations exist
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT raw_result, repaid_on_time, defaulted "
            "FROM scoring_log "
            "WHERE is_demo=0 AND defaulted IS NOT NULL "
            "AND outcome_status IN ('paid_on_time','paid_late','defaulted','defaulted_recovered')"
        ).fetchall()

    training = []
    for row in rows:
        try:
            result = json.loads(row["raw_result"])
        except (json.JSONDecodeError, TypeError):
            continue

        signals = {s["name"]: s["raw_score"]
                   for s in result.get("signals", [])
                   if s.get("raw_score") is not None}

        label = 0 if int(row["defaulted"] or 0) else 1  # model default, not lateness
        training.append({"signals": signals, "label": label})

    return training


# ---------------------------------------------------------------------------
# Rank correlation (AUC proxy per signal)
# ---------------------------------------------------------------------------

def _rank_auc(scores: list[float], labels: list[int]) -> float:
    """
    Wilcoxon-Mann-Whitney AUC: probability that a randomly chosen
    repaid loan has a higher signal score than a randomly chosen defaulted loan.
    0.5 = no predictive power, 1.0 = perfect.
    """
    pos = [s for s, l in zip(scores, labels) if l == 1]
    neg = [s for s, l in zip(scores, labels) if l == 0]
    if not pos or not neg:
        return float("nan")
    total = len(pos) * len(neg)
    wins  = sum(1 for p in pos for n in neg if p > n)
    ties  = sum(0.5 for p in pos for n in neg if p == n)
    return (wins + ties) / total


# ---------------------------------------------------------------------------
# Logistic regression (gradient descent, pure Python)
# ---------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    x = max(-500.0, min(500.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def _fit_logistic(
    X: list[list[float]],
    y: list[int],
    lr: float = 0.01,
    epochs: int = 2000,
    l2: float = 0.1,
) -> list[float]:
    """
    Fit logistic regression via gradient descent.
    X: list of feature vectors (already standardized)
    y: binary labels (0/1)
    Returns: weight vector (no bias term — we centre features instead)
    """
    n_features = len(X[0]) if X else 0
    n_samples  = len(X)
    w = [0.0] * n_features

    for _ in range(epochs):
        grad = [0.0] * n_features
        for xi, yi in zip(X, y):
            pred  = _sigmoid(sum(wi * xij for wi, xij in zip(w, xi)))
            error = pred - yi
            for j in range(n_features):
                grad[j] += error * xi[j]
        w = [
            wi - lr * (grad[j] / n_samples + l2 * wi)
            for j, wi in enumerate(w)
        ]

    return w


def _standardize(
    rows: list[list[Optional[float]]],
) -> tuple[list[list[float]], list[float], list[float]]:
    """
    Z-score standardize. Missing values (None) imputed with column mean.
    Returns (standardized_X, means, stds).
    """
    n = len(rows)
    n_feat = len(rows[0])

    means = []
    stds  = []
    for j in range(n_feat):
        col = [rows[i][j] for i in range(n) if rows[i][j] is not None]
        m = statistics.mean(col) if col else 50.0
        s = statistics.stdev(col) if len(col) >= 2 else 20.0
        means.append(m)
        stds.append(s if s > 0 else 1.0)

    X_std = []
    for row in rows:
        X_std.append([
            ((v if v is not None else means[j]) - means[j]) / stds[j]
            for j, v in enumerate(row)
        ])
    return X_std, means, stds


# ---------------------------------------------------------------------------
# Main calibration routine
# ---------------------------------------------------------------------------

def calibrate(db_path: str, min_samples: int = 20) -> dict:
    """
    Run full calibration. Returns a dict with:
      n_samples      : number of labelled loans used
      signal_auc     : {signal_name: auc_score}
      calibrated_weights : {signal_name: weight}  (normalised, from logistic reg)
      designed_weights   : {signal_name: weight}  (current hardcoded values)
      weight_drift       : {signal_name: calibrated - designed}  (+ = under-weighted)
    """
    rows = _load_training_rows(db_path)
    n = len(rows)

    result: dict = {
        "n_samples": n,
        "signal_auc": {},
        "calibrated_weights": None,
        "designed_weights": DESIGNED_WEIGHTS,
        "weight_drift": None,
        "warning": None,
    }

    if n < min_samples:
        result["warning"] = (
            f"Only {n} labelled loans (need ≥{min_samples} for reliable calibration). "
            "Designed weights unchanged. Keep originating."
        )
        return result

    # Per-signal AUC
    for sig in SIGNAL_NAMES:
        scores = [r["signals"].get(sig) for r in rows]
        labels = [r["label"] for r in rows]
        # Drop pairs where score is missing
        pairs = [(s, l) for s, l in zip(scores, labels) if s is not None]
        if pairs:
            s_list, l_list = zip(*pairs)
            result["signal_auc"][sig] = round(_rank_auc(list(s_list), list(l_list)), 3)

    # Logistic regression
    X_raw = [
        [r["signals"].get(sig) for sig in SIGNAL_NAMES]
        for r in rows
    ]
    y = [r["label"] for r in rows]
    X_std, _, _ = _standardize(X_raw)
    weights_raw = _fit_logistic(X_std, y)

    # Convert logistic weights to positive importances and normalise to sum=1
    importances = [abs(w) for w in weights_raw]
    total = sum(importances) or 1.0
    calibrated = {sig: round(imp / total, 4) for sig, imp in zip(SIGNAL_NAMES, importances)}
    result["calibrated_weights"] = calibrated

    # Drift: how far each signal is from its designed weight
    result["weight_drift"] = {
        sig: round(calibrated[sig] - DESIGNED_WEIGHTS[sig], 4)
        for sig in SIGNAL_NAMES
    }

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _bar(v: float, width: int = 20) -> str:
    filled = round(v * width)
    return "█" * filled + "░" * (width - filled)


def main():
    parser = argparse.ArgumentParser(description="Olin weight calibration")
    parser.add_argument("--db", default=str(
        Path(__file__).parent.parent / "olin_scoring.db"))
    parser.add_argument("--min-samples", type=int, default=20)
    args = parser.parse_args()

    print("\n  ┌─────────────────────────────────────────────────┐")
    print("  │  Olin · Weight Calibration                      │")
    print("  └─────────────────────────────────────────────────┘\n")

    cal = calibrate(args.db, args.min_samples)
    print(f"  Labelled loans in DB: {cal['n_samples']}\n")

    if cal["warning"]:
        print(f"  ⚠  {cal['warning']}\n")
        return

    print("  ── Per-signal AUC (0.5=random · 0.7=useful · 1.0=perfect) ──\n")
    for sig in SIGNAL_NAMES:
        auc = cal["signal_auc"].get(sig, float("nan"))
        flag = ""
        if not math.isnan(auc):
            if auc < 0.55:
                flag = "  ← WEAK"
            elif auc > 0.75:
                flag = "  ← STRONG"
        auc_str = f"{auc:.3f}" if not math.isnan(auc) else " N/A"
        print(f"  {sig:<28}  AUC {auc_str}  {_bar(auc if not math.isnan(auc) else 0.5)}{flag}")

    print("\n  ── Weight comparison (designed vs data-driven) ──\n")
    print(f"  {'Signal':<28}  {'Designed':>8}  {'Calibrated':>10}  {'Drift':>7}")
    print("  " + "─" * 62)
    for sig in SIGNAL_NAMES:
        d  = cal["designed_weights"][sig]
        c  = cal["calibrated_weights"][sig]
        dr = cal["weight_drift"][sig]
        arrow = "▲" if dr > 0.02 else ("▼" if dr < -0.02 else " ")
        print(f"  {sig:<28}  {d:>8.2%}  {c:>10.2%}  {arrow}{dr:>+6.2%}")

    print()
    large_drifts = [
        (sig, cal["weight_drift"][sig])
        for sig in SIGNAL_NAMES
        if abs(cal["weight_drift"][sig]) > 0.05
    ]
    if large_drifts:
        print("  Signals with drift > 5% (consider adjusting WEIGHTS_BY_TYPE):")
        for sig, dr in sorted(large_drifts, key=lambda x: -abs(x[1])):
            direction = "under-weighted" if dr > 0 else "over-weighted"
            print(f"    {sig}: {direction} by {abs(dr):.0%}")
    else:
        print("  No large drifts detected. Designed weights look reasonable.")

    print(f"\n  Re-run when n_samples ≥ {args.min_samples * 5} for production-grade recalibration.\n")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Tier calibration report (added v0.3)
# ---------------------------------------------------------------------------

TIER_LABELS = {
    1:  "AUTO_APPROVE  C1·D1·S1",
    2:  "COMMITTEE     C1·D1·S2",
    3:  "COMMITTEE     C1·D2·S1",
    4:  "COMMITTEE     C1·D2·S2",
    5:  "COMMITTEE     C2·D1·S1",
    6:  "COMMITTEE     C2·D1·S2",
    7:  "COMMITTEE     C2·D2·S1",
    8:  "COMMITTEE     C2·D2·S2",
    9:  "COMMITTEE     C3·D1·S1",
    10: "COMMITTEE     C3·D1·S2",
    11: "COMMITTEE     C3·D2·S1",
    12: "COMMITTEE     C3·D2·S2",
    13: "DECLINE       C4 or D3 or S3",
    14: "DECLINE       Pre-gate (fraud/portfolio)",
}

_GR = "\033[92m"; _AM = "\033[93m"; _RD = "\033[91m"
_MU = "\033[90m"; _BD = "\033[1m";  _RS = "\033[0m"


def _risk_bar(ratio: float, width: int = 14) -> str:
    filled = round(ratio * width)
    color = _GR if ratio < 0.05 else (_AM if ratio < 0.15 else _RD)
    return f"{color}{'█' * filled}{_MU}{'░' * (width - filled)}{_RS}"


def tier_report(db_path: str) -> None:
    """Print a tier-distribution + outcome cross-tab. Replaces ad-hoc SQL queries."""
    from .store import ScoringLog
    ScoringLog(db_path).conn.close()
    conn = sqlite3.connect(db_path)

    dist = conn.execute(
        "SELECT tier, decision, COUNT(*), AVG(score) FROM scoring_log WHERE is_demo=0 "
        "GROUP BY tier, decision ORDER BY tier"
    ).fetchall()

    outcomes = conn.execute(
        """SELECT tier, COUNT(*),
                  SUM(CASE WHEN repaid_on_time=1 THEN 1 ELSE 0 END),
                  SUM(CASE WHEN defaulted=1 THEN 1 ELSE 0 END),
                  AVG(score), AVG(days_to_repay)
           FROM scoring_log
           WHERE is_demo=0 AND (repaid_on_time IS NOT NULL OR defaulted IS NOT NULL)
           GROUP BY tier ORDER BY tier"""
    ).fetchall()

    dscr_by_tier: dict[int, list[float]] = {}
    for (_id, tier, raw) in conn.execute(
        "SELECT application_id, tier, raw_result FROM scoring_log WHERE raw_result IS NOT NULL"
    ).fetchall():
        try:
            rep = json.loads(raw).get("repayment") or {}
            dscr = rep.get("dscr")
            if dscr is not None:
                dscr_by_tier.setdefault(tier, []).append(float(dscr))
        except Exception:
            pass

    conn.close()
    total = sum(r[2] for r in dist)

    print(f"\n  {_BD}Olin · Tier Distribution{_RS}  {_MU}({total} applications){_RS}")
    print(f"  {'─' * 92}")
    print(f"  {_BD}{'Tier':<6}  {'Matrix label':<36}  {'Decision':<14}  "
          f"{'n':>4}  {'%':>6}  {'Score':>6}  {'Avg DSCR':>8}{_RS}")
    print(f"  {'─' * 90}")

    for tier, decision, count, avg_score in dist:
        label = TIER_LABELS.get(tier, f"Tier {tier}")
        pct   = count / total * 100 if total else 0
        col   = _GR if decision == "AUTO_APPROVE" else (_AM if "COMMITTEE" in decision or "MANUAL" in decision else _RD)
        sc    = f"{avg_score:.1f}" if avg_score else "—"
        dvals = dscr_by_tier.get(tier, [])
        dc    = f"{sum(dvals)/len(dvals):.2f}" if dvals else "—"
        print(f"  {col}{tier:<6}{_RS}  {label:<36}  {col}{decision:<14}{_RS}  "
              f"{count:>4}  {pct:>5.1f}%  {sc:>6}  {dc:>8}")

    labeled_n = sum(r[1] for r in outcomes)
    if labeled_n == 0:
        print(f"\n  {_MU}No labeled outcomes yet. Run record_outcome() after loan completion.{_RS}\n")
        return

    print(f"\n  {_BD}Outcome cross-tab  ({labeled_n} labeled){_RS}")
    print(f"  {'─' * 92}")
    print(f"  {_BD}{'Tier':<6}  {'n':>4}  {'Repaid':>6}  {'Default':>7}  "
          f"{'Rate':>6}  {'Risk bar':<16}  {'Avg score':>9}  {'Avg days':>8}{_RS}")
    print(f"  {'─' * 90}")

    for tier, n, repaid, defaulted, avg_score, avg_days in outcomes:
        dr    = (defaulted or 0) / n if n else 0
        sc    = f"{avg_score:.1f}" if avg_score else "—"
        days  = f"{avg_days:.0f}d" if avg_days else "—"
        print(f"  {tier:<6}  {n:>4}  {repaid or 0:>6}  {defaulted or 0:>7}  "
              f"{dr:>5.1%}  {_risk_bar(dr):<16}  {sc:>9}  {days:>8}")
    print()
