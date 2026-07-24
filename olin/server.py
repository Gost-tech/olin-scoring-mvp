#!/usr/bin/env python3
"""
Olin Credit Scoring — Analyst Review Interface

Run:
    cd /Users/pc/Downloads/olin_scoring_mvp_1
    python3 -m olin.server
    python3 -m olin.server --db path/to/olin_scoring.db --port 8080 --no-seed
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sqlite3
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from .config import (
    analyst_token, api_keys, default_db_path, is_production, runtime_mode, webhook_secret,
)

# Set by main() before server starts
DB_PATH: str = ""

# ---------------------------------------------------------------------------
# Embedded HTML page
# ---------------------------------------------------------------------------
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Olin · Analyst Review</title>
<style>
:root {
  --bg:       #0d1117;
  --surf:     #161b22;
  --surf2:    #21262d;
  --border:   #30363d;
  --text:     #e6edf3;
  --muted:    #8b949e;
  --green:    #238636;
  --green-hi: #3fb950;
  --amber:    #9a6700;
  --amber-hi: #e3b341;
  --red:      #a12424;
  --red-hi:   #f85149;
  --blue:     #1f6feb;
  --radius:   8px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;font-size:14px;line-height:1.6;min-height:100vh}

/* ── Top bar ──────────────────────────────────────────────────────── */
.topbar{
  position:sticky;top:0;z-index:100;
  background:rgba(13,17,23,.92);
  backdrop-filter:blur(12px);
  border-bottom:1px solid var(--border);
  padding:0 24px;
  display:flex;align-items:center;gap:16px;height:56px;
}
.logo{font-size:16px;font-weight:600;letter-spacing:-.3px;color:var(--text)}
.logo span{color:var(--muted);font-weight:400}
.stats-chips{display:flex;gap:8px;margin-left:auto}
.chip{padding:3px 10px;border-radius:12px;font-size:12px;font-weight:500;border:1px solid var(--border);background:var(--surf2);cursor:default}
.chip.active{border-color:var(--blue);color:#58a6ff;background:rgba(31,111,235,.12)}

/* ── Filter tabs ──────────────────────────────────────────────────── */
.filter-bar{
  display:flex;gap:4px;padding:16px 24px 0;
  border-bottom:1px solid var(--border);
  background:var(--bg);
}
.tab{
  padding:8px 14px;border:none;background:none;
  color:var(--muted);font-size:13px;font-weight:500;cursor:pointer;
  border-bottom:2px solid transparent;margin-bottom:-1px;
  transition:color .15s,border-color .15s;
}
.tab:hover{color:var(--text)}
.tab.active{color:var(--text);border-bottom-color:var(--blue)}
.tab .count{
  display:inline-flex;align-items:center;justify-content:center;
  min-width:18px;height:18px;padding:0 5px;
  border-radius:9px;font-size:11px;margin-left:5px;
  background:var(--surf2);
}

/* ── Main content ─────────────────────────────────────────────────── */
main{max-width:1100px;margin:0 auto;padding:24px}
.empty{color:var(--muted);text-align:center;padding:60px;font-size:15px}

/* ── Card ─────────────────────────────────────────────────────────── */
.card{
  background:var(--surf);border:1px solid var(--border);
  border-radius:var(--radius);margin-bottom:20px;
  transition:border-color .15s;
  overflow:hidden;
}
.card:hover{border-color:#484f58}
.card.decided-APPROVE{border-left:3px solid var(--green)}
.card.decided-DECLINE{border-left:3px solid var(--red)}
.card.decided-MANUAL_REVIEW{border-left:3px solid var(--amber-hi)}

/* card header */
.card-header{
  display:flex;align-items:flex-start;justify-content:space-between;
  gap:12px;padding:16px 20px 12px;
  border-bottom:1px solid var(--border);
}
.merchant-name{font-size:16px;font-weight:600;line-height:1.3}
.merchant-meta{display:flex;align-items:center;gap:8px;margin-top:4px;flex-wrap:wrap}
.badge{
  display:inline-block;padding:2px 8px;border-radius:4px;
  font-size:11px;font-weight:600;letter-spacing:.3px;text-transform:uppercase;
}
.badge-type{background:var(--surf2);color:var(--muted);border:1px solid var(--border)}
.badge-ae{background:rgba(35,134,54,.15);color:var(--green-hi);border:1px solid rgba(35,134,54,.4)}
.badge-mr{background:rgba(154,103,0,.15);color:var(--amber-hi);border:1px solid rgba(154,103,0,.4)}
.badge-dc{background:rgba(161,36,36,.15);color:var(--red-hi);border:1px solid rgba(161,36,36,.4)}
.badge-analyst-ap{background:rgba(35,134,54,.25);color:var(--green-hi);border:1px solid var(--green);font-size:12px;padding:3px 10px}
.badge-analyst-dc{background:rgba(161,36,36,.25);color:var(--red-hi);border:1px solid var(--red);font-size:12px;padding:3px 10px}
.badge-analyst-mr{background:rgba(154,103,0,.2);color:var(--amber-hi);border:1px solid var(--amber-hi);font-size:12px;padding:3px 10px}

.app-id{font-family:monospace;font-size:12px;color:var(--muted)}
.colonia{font-size:12px;color:var(--muted)}
.scored-at{font-size:12px;color:var(--muted);white-space:nowrap}

/* card body: score + signals side by side */
.card-body{display:grid;grid-template-columns:260px 1fr;gap:0}
@media(max-width:720px){.card-body{grid-template-columns:1fr}}

/* score panel */
.score-panel{
  padding:20px;border-right:1px solid var(--border);
  display:flex;flex-direction:column;gap:14px;
}
.score-big{font-size:56px;font-weight:700;line-height:1;letter-spacing:-2px;font-variant-numeric:tabular-nums}
.score-big.green{color:var(--green-hi)}
.score-big.amber{color:var(--amber-hi)}
.score-big.red{color:var(--red-hi)}

.ci-text{font-size:12px;color:var(--muted)}
.ci-text strong{color:var(--text);font-variant-numeric:tabular-nums}

/* score track */
.track-wrap{display:flex;flex-direction:column;gap:4px}
.track{
  position:relative;height:12px;border-radius:6px;overflow:visible;
  background:linear-gradient(to right,
    #5c1212 0%, #7f1d1d 49.9%,
    #78350f 50%, #a16207 74.9%,
    #14532d 75%, #15803d 100%
  );
}
.ci-band{
  position:absolute;top:0;bottom:0;
  background:rgba(255,255,255,.22);
  border-left:2px solid rgba(255,255,255,.55);
  border-right:2px solid rgba(255,255,255,.55);
  border-radius:4px;
}
.score-needle{
  position:absolute;top:-4px;bottom:-4px;width:3px;margin-left:-1.5px;
  background:#fff;border-radius:3px;
  box-shadow:0 0 6px rgba(255,255,255,.7);
}
.track-labels{display:flex;position:relative;font-size:10px;color:var(--muted);height:14px}
.track-labels span{position:absolute;transform:translateX(-50%)}

.coverage-row{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.coverage-bar{
  flex:1;height:4px;background:var(--surf2);border-radius:2px;overflow:hidden
}
.coverage-fill{height:100%;background:#388bfd;border-radius:2px}

.engine-rec{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:500}
.engine-rec .label{color:var(--muted)}

.loan-row{font-size:12px;color:var(--muted);line-height:1.8}
.loan-row strong{color:var(--text);font-variant-numeric:tabular-nums}

/* signals panel */
.signals-panel{padding:16px 20px}
.signals-panel h3{font-size:11px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;color:var(--muted);margin-bottom:12px}

.signals-table{width:100%;border-collapse:collapse}
.signals-table tr:not(:last-child) td{border-bottom:1px solid var(--border)}
.signals-table td{padding:7px 6px;vertical-align:top}
.sig-name{font-size:12px;font-weight:500;white-space:nowrap;width:140px}
.sig-name.missing{color:var(--muted)}
.sig-bar-cell{width:130px}
.sig-bar-wrap{display:flex;align-items:center;gap:6px}
.sig-bar{width:80px;height:6px;background:var(--surf2);border-radius:3px;overflow:hidden;flex-shrink:0}
.sig-bar-fill{height:100%;border-radius:3px}
.sig-bar-fill.hi{background:var(--green-hi)}
.sig-bar-fill.mid{background:var(--amber-hi)}
.sig-bar-fill.lo{background:var(--red-hi)}
.sig-score{font-size:12px;font-variant-numeric:tabular-nums;font-weight:600;min-width:30px}
.sig-wt{font-size:11px;color:var(--muted);white-space:nowrap;padding-right:8px}
.sig-expl{font-size:11px;color:var(--muted);line-height:1.4}
.sig-tag{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:600;margin-left:4px;background:rgba(31,111,235,.2);color:#58a6ff;border:1px solid rgba(31,111,235,.4)}
.sig-tag.fallback{background:rgba(154,103,0,.2);color:var(--amber-hi);border-color:var(--amber)}
.sig-missing{font-size:11px;color:var(--muted);font-style:italic}

/* reasons */
.reasons{
  padding:10px 20px;border-top:1px solid var(--border);
  display:flex;flex-wrap:wrap;gap:6px;align-items:center;
}
.reason-item{font-size:12px;color:var(--muted)}
.reason-item::before{content:'•  ';color:var(--border)}
.hard-fail{color:var(--red-hi)}
.hard-fail::before{content:'⚠ ';color:var(--red-hi)}

/* actions */
.card-footer{
  display:flex;align-items:center;gap:10px;
  padding:14px 20px;border-top:1px solid var(--border);
  background:rgba(255,255,255,.015);
}
.action-btn{
  display:flex;align-items:center;gap:6px;
  padding:7px 16px;border:1px solid;border-radius:6px;
  font-size:13px;font-weight:500;cursor:pointer;
  transition:background .12s,opacity .12s;
  background:transparent;
}
.action-btn:disabled{opacity:.35;cursor:not-allowed}
.btn-approve{color:var(--green-hi);border-color:var(--green)}
.btn-approve:hover:not(:disabled){background:rgba(35,134,54,.15)}
.btn-manual{color:var(--amber-hi);border-color:var(--amber-hi)}
.btn-manual:hover:not(:disabled){background:rgba(154,103,0,.15)}
.btn-decline{color:var(--red-hi);border-color:var(--red)}
.btn-decline:hover:not(:disabled){background:rgba(161,36,36,.15)}
.btn-disburse{color:#58a6ff;border-color:var(--blue);font-weight:600}
.btn-disburse:hover:not(:disabled){background:rgba(31,111,235,.15)}
.btn-disburse.disbursed-ok{color:var(--green-hi);border-color:var(--green);opacity:.6;cursor:default}
.decision-stamp{margin-left:auto;font-size:12px;color:var(--muted)}

/* ── Portfolio panel ─────────────────────────────────────────────── */
.portfolio-bar{
  background:var(--surf);border-bottom:1px solid var(--border);
  padding:10px 24px;display:flex;gap:24px;align-items:center;flex-wrap:wrap;
}
.pf-stat{display:flex;flex-direction:column;align-items:center;gap:1px}
.pf-label{font-size:10px;color:var(--muted);letter-spacing:.3px;text-transform:uppercase}
.pf-value{font-size:16px;font-weight:700;font-variant-numeric:tabular-nums;color:var(--text)}
.pf-value.warn{color:var(--amber-hi)}
.pf-value.bad{color:var(--red-hi)}
.pf-sep{width:1px;height:32px;background:var(--border)}
.grad-badge{
  font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600;
  background:rgba(31,111,235,.2);color:#58a6ff;border:1px solid rgba(31,111,235,.4);
  margin-left:6px;
}
.tier-badge{
  display:inline-flex;align-items:center;justify-content:center;
  min-width:54px;padding:3px 9px;border-radius:10px;font-size:12px;font-weight:700;
  letter-spacing:.2px;
}
.tier-badge.t1{background:rgba(35,134,54,.2);color:var(--green-hi);border:1px solid rgba(35,134,54,.5)}
.tier-badge.t2,.tier-badge.t3,.tier-badge.t4,
.tier-badge.t5,.tier-badge.t6,.tier-badge.t7,.tier-badge.t8,
.tier-badge.t9,.tier-badge.t10,.tier-badge.t11,.tier-badge.t12{
  background:rgba(154,103,0,.18);color:var(--amber-hi);border:1px solid rgba(154,103,0,.45)}
.tier-badge.t13,.tier-badge.t14{
  background:rgba(161,36,36,.18);color:var(--red-hi);border:1px solid rgba(161,36,36,.45)}

/* ── Toast ───────────────────────────────────────────────────────── */
#toast{
  position:fixed;bottom:24px;right:24px;
  display:flex;flex-direction:column;gap:8px;z-index:9999;
}
.toast-item{
  padding:10px 16px;border-radius:6px;font-size:13px;font-weight:500;
  border:1px solid;animation:slideIn .2s ease;
  box-shadow:0 4px 12px rgba(0,0,0,.4);
}
.toast-ok{background:rgba(35,134,54,.2);color:var(--green-hi);border-color:var(--green)}
.toast-err{background:rgba(161,36,36,.2);color:var(--red-hi);border-color:var(--red)}
@keyframes slideIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

/* ── Repayment section ───────────────────────────────────────────── */
.repayment-section{
  padding:12px 20px;border-top:1px solid var(--border);
  background:rgba(255,255,255,.012);
}
.repayment-section h3{
  font-size:11px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;
  color:var(--muted);margin-bottom:10px;
}
.rep-grid{display:flex;flex-wrap:wrap;gap:12px 28px}
.rep-item{display:flex;flex-direction:column;gap:2px}
.rep-label{font-size:10px;color:var(--muted);letter-spacing:.3px;text-transform:uppercase}
.rep-value{font-size:14px;font-weight:600;font-variant-numeric:tabular-nums}
.rep-value.green{color:var(--green-hi)}
.rep-value.amber{color:var(--amber-hi)}
.rep-value.red{color:var(--red-hi)}
.rep-note{font-size:11px;color:var(--amber-hi);margin-top:6px}
.rep-buro-ok{color:var(--green-hi)}
.rep-buro-warn{color:var(--amber-hi)}
.rep-buro-bad{color:var(--red-hi)}

/* ── Fraud section ───────────────────────────────────────────────── */
.fraud-section{
  padding:12px 20px;border-top:1px solid var(--border);
  background:rgba(255,255,255,.008);
}
.fraud-section h3{
  font-size:11px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;
  color:var(--muted);margin-bottom:10px;
}
.fraud-grid{display:flex;flex-wrap:wrap;gap:10px 24px;align-items:flex-start}
.fraud-score-wrap{display:flex;align-items:center;gap:8px}
.fraud-score{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums}
.fraud-score.clean{color:var(--green-hi)}
.fraud-score.warn{color:var(--amber-hi)}
.fraud-score.bad{color:var(--red-hi)}
.fraud-checks{display:flex;gap:5px;flex-wrap:wrap}
.fraud-check{
  font-size:10px;padding:2px 7px;border-radius:3px;font-weight:600;
  letter-spacing:.3px;text-transform:uppercase;
}
.fraud-check.ok{background:rgba(35,134,54,.15);color:var(--green-hi);border:1px solid rgba(35,134,54,.3)}
.fraud-check.fail{background:rgba(161,36,36,.15);color:var(--red-hi);border:1px solid rgba(161,36,36,.3)}
.fraud-flag{font-size:11px;color:var(--amber-hi);margin-top:4px}
.fraud-block{font-size:11px;color:var(--red-hi);font-weight:500;margin-top:4px}

/* ── Counter-offer banner ────────────────────────────────────────── */
.counter-offer-banner{
  display:flex;align-items:flex-start;gap:12px;
  padding:12px 20px;
  background:rgba(154,103,0,.12);
  border-left:3px solid var(--amber-hi);
  border-top:1px solid rgba(154,103,0,.3);
}
.co-icon{font-size:18px;margin-top:1px;flex-shrink:0}
.co-body{flex:1}
.co-title{font-size:12px;font-weight:700;color:var(--amber-hi);letter-spacing:.4px;text-transform:uppercase;margin-bottom:3px}
.co-text{font-size:13px;color:var(--text)}
.co-amounts{display:flex;gap:20px;margin-top:8px}
.co-amount{display:flex;flex-direction:column;gap:1px}
.co-amount-label{font-size:10px;color:var(--muted);letter-spacing:.3px;text-transform:uppercase}
.co-amount-value{font-size:15px;font-weight:700;font-variant-numeric:tabular-nums}
.co-amount-value.declined{color:var(--red-hi);text-decoration:line-through;opacity:.7}
.co-amount-value.offered{color:var(--amber-hi)}

/* ── Sensitivity hints ───────────────────────────────────────────── */
.sensitivity-hints{
  padding:8px 20px 10px;border-top:1px solid var(--border);
  background:rgba(255,255,255,.006);
}
.sensitivity-hints h3{
  font-size:10px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;
  color:var(--muted);margin-bottom:6px;
}
.sens-chip{
  display:inline-flex;align-items:center;gap:4px;
  padding:3px 9px;border-radius:10px;font-size:11px;font-weight:500;
  background:rgba(88,166,255,.1);color:#58a6ff;
  border:1px solid rgba(88,166,255,.25);margin:2px 4px 2px 0;
}

/* ── Mitigation menu ─────────────────────────────────────────────── */
.mitigation-section{
  padding:12px 20px 14px;border-top:1px solid var(--border);
  background:rgba(255,200,0,.028);
}
.mitigation-section h3{
  font-size:10px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;
  color:#e3b341;margin-bottom:6px;
}
.mit-intro{
  font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.4;
}
.mitigation-option{
  padding:7px 10px;border-radius:6px;margin-bottom:6px;
  background:rgba(255,255,255,.04);border:1px solid rgba(255,200,0,.15);
}
.mit-header{display:flex;align-items:center;gap:6px;margin-bottom:3px}
.mit-icon{font-size:13px;width:18px;text-align:center;color:#e3b341}
.mit-label{font-size:12px;font-weight:600;color:var(--text)}
.mit-rationale{font-size:11px;color:var(--muted);line-height:1.4;margin-left:24px}

/* ── Analyst note section ────────────────────────────────────────── */
.analyst-note-section{
  padding:12px 20px;border-top:1px solid var(--border);
  background:rgba(255,255,255,.008);
}
.analyst-note-section h3{
  font-size:10px;font-weight:600;letter-spacing:.6px;text-transform:uppercase;
  color:var(--muted);margin-bottom:8px;
}
.analyst-note-row{display:flex;gap:10px;align-items:flex-end}
.analyst-note-textarea{
  flex:1;min-height:56px;max-height:120px;
  background:var(--surf2);border:1px solid var(--border);
  border-radius:6px;color:var(--text);font-size:13px;font-family:inherit;
  padding:8px 10px;resize:vertical;
  transition:border-color .15s;
}
.analyst-note-textarea:focus{outline:none;border-color:#388bfd}
.btn-save-note{
  padding:7px 14px;border-radius:6px;font-size:12px;font-weight:600;
  cursor:pointer;white-space:nowrap;
  background:rgba(31,111,235,.15);color:#58a6ff;
  border:1px solid rgba(31,111,235,.4);
  transition:background .12s;flex-shrink:0;
}
.btn-save-note:hover{background:rgba(31,111,235,.25)}

/* ── Tier dist widget ────────────────────────────────────────────── */
.tier-dist-widget{
  display:flex;align-items:center;gap:8px;margin-left:auto;flex-wrap:wrap;
}
.tier-dist-label{font-size:10px;color:var(--muted);letter-spacing:.3px;text-transform:uppercase;white-space:nowrap}
.tier-bars{display:flex;gap:2px;align-items:flex-end;height:30px}
.tier-bar-col{
  display:flex;flex-direction:column;align-items:center;gap:2px;
  cursor:default;position:relative;
}
.tier-bar-fill{
  width:14px;border-radius:2px 2px 0 0;min-height:3px;
  transition:opacity .15s;
}
.tier-bar-col:hover .tier-bar-fill{opacity:.7}
.tier-bar-col:hover .tier-tooltip{display:block}
.tier-bar-lbl{font-size:9px;color:var(--muted);font-variant-numeric:tabular-nums}
.tier-tooltip{
  display:none;position:absolute;bottom:calc(100% + 4px);left:50%;
  transform:translateX(-50%);
  background:var(--surf2);border:1px solid var(--border);
  border-radius:4px;padding:4px 8px;font-size:10px;
  white-space:nowrap;z-index:50;color:var(--text);
}

/* ── CSV export button ───────────────────────────────────────────── */
.btn-export{
  padding:5px 12px;border-radius:5px;font-size:11px;font-weight:600;
  cursor:pointer;text-decoration:none;
  background:rgba(255,255,255,.06);color:var(--muted);
  border:1px solid var(--border);
  transition:background .12s,color .12s;white-space:nowrap;flex-shrink:0;
}
.btn-export:hover{background:rgba(255,255,255,.12);color:var(--text)}
.action-btn:focus-visible,.tab:focus-visible,.btn-export:focus-visible,.btn-save-note:focus-visible{
  outline:2px solid #58a6ff;outline-offset:2px;
}
.mode-banner{
  display:none;padding:8px 24px;border-bottom:1px solid var(--border);
  font-size:12px;font-weight:600;letter-spacing:.2px;
}
.mode-banner.demo{display:block;background:rgba(154,103,0,.15);color:var(--amber-hi)}
.mode-banner.production{display:block;background:rgba(35,134,54,.12);color:var(--green-hi)}
.provenance{
  padding:10px 20px;border-top:1px solid var(--border);display:flex;
  flex-wrap:wrap;gap:8px;align-items:center;background:rgba(255,255,255,.012);
}
.source-pill{font-size:11px;padding:3px 8px;border-radius:12px;border:1px solid var(--border);color:var(--muted)}
.source-pill.verified{color:var(--green-hi);border-color:rgba(35,134,54,.55);background:rgba(35,134,54,.1)}
.source-pill.synthetic{color:var(--amber-hi);border-color:rgba(154,103,0,.55);background:rgba(154,103,0,.1)}
.decision-rationale{font-size:11px;color:var(--muted);margin-left:auto;max-width:52ch;text-align:right}

/* ── Scrollbar ───────────────────────────────────────────────────── */
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
</style>
</head>
<body>

<header class="topbar">
  <span class="logo">Olin <span>· Analyst Review</span></span>
  <div class="stats-chips" id="stats-chips"></div>
</header>
<div class="mode-banner" id="mode-banner" role="status"></div>

<div class="portfolio-bar" id="portfolio-bar"></div>

<nav class="filter-bar" id="filter-bar"></nav>

<main>
  <div id="app-grid"><p class="empty">Loading…</p></div>
</main>

<div id="toast"></div>

<script>
'use strict';

const SIG_LABELS = {
  fmcg_purchase_history: 'FMCG Purchases',
  bank_cash_flow:        'Bank Cash Flow',
  business_tenure:       'Business Tenure',
  pos_transaction_volume:'POS Volume',
  google_maps_rating:    'Google Maps',
  imss_payroll:          'IMSS Payroll',
};

const ENG_LABEL = {
  AUTO_APPROVE:  {text:'AUTO APPROVE',  cls:'ae'},
  COMMITTEE:     {text:'COMMITTEE',     cls:'mr'},
  MANUAL_REVIEW: {text:'MANUAL REVIEW', cls:'mr'},
  DECLINE:       {text:'DECLINE',       cls:'dc'},
};

const ANALYST_LABEL = {
  APPROVE:       {text:'✓ Approved',          cls:'analyst-ap'},
  MANUAL_REVIEW: {text:'↩ Routed to Review',  cls:'analyst-mr'},
  DECLINE:       {text:'✗ Declined',          cls:'analyst-dc'},
};

let allApps = [];
let activeFilter = 'all';

async function apiFetch(url, options={}) {
  const headers = new Headers(options.headers || {});
  const token = sessionStorage.getItem('olin_analyst_token') || '';
  if (token) headers.set('X-Olin-Analyst-Token', token);
  let response = await fetch(url, {...options, headers});
  if (response.status === 401) {
    const supplied = window.prompt('Analyst access token');
    if (supplied) {
      sessionStorage.setItem('olin_analyst_token', supplied.trim());
      headers.set('X-Olin-Analyst-Token', supplied.trim());
      response = await fetch(url, {...options, headers});
    }
  }
  return response;
}

// ── Data loading ──────────────────────────────────────────────────────
async function load() {
  try {
    const r = await apiFetch('/api/apps');
    if (!r.ok) throw new Error((await r.json()).error || r.statusText);
    allApps = await r.json();
    const mode = allApps[0]?.environment || 'demo';
    const banner = document.getElementById('mode-banner');
    banner.className = `mode-banner ${mode === 'production' ? 'production' : 'demo'}`;
    banner.textContent = mode === 'production'
      ? 'PRODUCTION · verified inputs required · engine declines are locked'
      : 'DEMO MODE · synthetic inputs may be present · never use for real disbursement';
    renderFilterBar();
    renderGrid();
    renderPortfolioBar();
  } catch(e) {
    document.getElementById('app-grid').innerHTML =
      `<p class="empty">Error loading data: ${e.message}</p>`;
  }
}

// ── Filter bar ────────────────────────────────────────────────────────
function renderFilterBar() {
  const counts = {
    all:            allApps.length,
    pending:        allApps.filter(a => !a.analyst_override).length,
    APPROVE:        allApps.filter(a => a.analyst_override === 'APPROVE').length,
    MANUAL_REVIEW:  allApps.filter(a => a.analyst_override === 'MANUAL_REVIEW').length,
    DECLINE:        allApps.filter(a => a.analyst_override === 'DECLINE').length,
  };

  // stats chips in topbar
  document.getElementById('stats-chips').innerHTML = `
    <span class="chip">${counts.all} total</span>
    <span class="chip">${counts.pending} pending</span>
  `;

  const tabs = [
    ['all',           'All'],
    ['pending',       'Pending'],
    ['APPROVE',       'Approved'],
    ['MANUAL_REVIEW', 'Routed'],
    ['DECLINE',       'Declined'],
  ];
  document.getElementById('filter-bar').innerHTML = tabs.map(([key, label]) =>
    `<button class="tab${activeFilter===key?' active':''}" onclick="setFilter('${key}')">
      ${label}<span class="count">${counts[key]}</span>
    </button>`
  ).join('');
}

function setFilter(f) {
  activeFilter = f;
  renderFilterBar();
  renderGrid();
}

// ── Grid ──────────────────────────────────────────────────────────────
function renderGrid() {
  let apps = allApps;
  if (activeFilter === 'pending')       apps = apps.filter(a => !a.analyst_override);
  else if (activeFilter !== 'all')      apps = apps.filter(a => a.analyst_override === activeFilter);
  const grid = document.getElementById('app-grid');
  grid.innerHTML = apps.length
    ? apps.map(cardHtml).join('')
    : '<p class="empty">No applications in this view.</p>';
}

// ── Card rendering ────────────────────────────────────────────────────
function cardHtml(app) {
  const decided = app.analyst_override;
  const scoreColor = app.score >= 75 ? 'green' : app.score >= 50 ? 'amber' : 'red';
  const eng = ENG_LABEL[app.decision] || {text: app.decision, cls:'mr'};
  const dt = new Date(app.scored_at + (app.scored_at.includes('Z')?'':'Z'));
  const dateStr = isNaN(dt) ? app.scored_at : dt.toLocaleDateString('es-MX',{day:'numeric',month:'short',year:'numeric'});
  const analystApproved = app.analyst_override === 'APPROVE';
  const declined = app.decision === 'DECLINE' || app.analyst_override === 'DECLINE';
  const inCommittee = !analystApproved && !declined && app.decision === 'COMMITTEE';
  const amountLabel = analystApproved ? 'Aprobado'
    : declined ? 'No aprobado'
    : inCommittee ? 'Monto en comité'
    : 'Monto evaluado';
  const amountValue = declined ? 0 : app.approved_mxn;
  const costLabel = analystApproved ? 'Costo fijo' : 'Costo estimado';
  const costValue = declined ? 0 : app.pricing_fixed_cost_mxn;

  return `
<article class="card${decided?' decided-'+decided:''}" data-app-id="${app.application_id}">

  <div class="card-header">
    <div>
      <div class="merchant-name">${esc(app.merchant_name)}</div>
      <div class="merchant-meta">
        <span class="badge badge-type">${esc(app.business_type)}</span>
        ${app.colonia ? `<span class="colonia">${esc(app.colonia)}</span>` : ''}
        <span class="app-id">app ${app.application_id}</span>
        ${app.tier > 0 ? `<span class="tier-badge t${app.tier}" title="Credit tier from Círculo×DSCR×Score matrix">Tier ${app.tier}</span>` : ''}
        ${app.buro_score != null ? `<span class="badge badge-type" title="Círculo de Crédito score">Círculo ${app.buro_score}</span>` : ''}
        ${app.graduation_tier > 0 ? `<span class="grad-badge">Grad ${app.graduation_tier}</span>` : ''}
        ${app.is_demo ? `<span class="source-pill synthetic">DEMO DATA</span>` : `<span class="source-pill verified">PRODUCTION</span>`}
      </div>
    </div>
    <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
      <span class="scored-at">${dateStr}</span>
      ${decided ? `<span class="badge badge-${ANALYST_LABEL[decided].cls}">${ANALYST_LABEL[decided].text}</span>` : ''}
    </div>
  </div>

  <div class="card-body">

    <!-- LEFT: Score panel -->
    <div class="score-panel">
      <div>
        <div class="score-big ${scoreColor}">${app.score.toFixed(1)}</div>
        <div class="ci-text" style="margin-top:4px">
          CI <strong>[${app.ci_low.toFixed(1)} – ${app.ci_high.toFixed(1)}]</strong>
        </div>
      </div>

      <div class="track-wrap">
        <div class="track">
          <div class="ci-band" style="left:${app.ci_low}%;width:${Math.max(app.ci_high-app.ci_low,1)}%"></div>
          <div class="score-needle" style="left:${app.score}%"></div>
        </div>
        <div class="track-labels">
          <span style="left:0%">0</span>
          <span style="left:50%">50</span>
          <span style="left:75%">75</span>
          <span style="left:100%">100</span>
        </div>
      </div>

      <div class="coverage-row">
        <span>Coverage</span>
        <div class="coverage-bar"><div class="coverage-fill" style="width:${(app.data_coverage*100).toFixed(0)}%"></div></div>
        <span>${(app.data_coverage*100).toFixed(0)}%</span>
      </div>

      <div class="engine-rec">
        <span class="label">Engine:</span>
        <span class="badge badge-${eng.cls}">${eng.text}</span>
      </div>

      <div class="loan-row">
        Solicitado <strong>MXN ${fmt(app.requested_mxn)}</strong><br>
        ${amountLabel}&nbsp;&nbsp; <strong>MXN ${fmt(amountValue)}</strong><br>
        ${costLabel}&nbsp; <strong>MXN ${fmt(costValue)}</strong>
        <span style="color:var(--muted)"> (60 días)</span>
      </div>
    </div>

    <!-- RIGHT: Signals panel -->
    <div class="signals-panel">
      <h3>Señales</h3>
      <table class="signals-table">
        <tbody>
          ${app.signals.map(sigRow).join('')}
        </tbody>
      </table>
    </div>
  </div>

  ${counterOfferHtml(app)}

  ${(app.decision_reasons.length || app.hard_filter_failures.length) ? `
  <div class="reasons">
    ${app.hard_filter_failures.map(r =>
      `<span class="reason-item hard-fail">${esc(r)}</span>`).join('')}
    ${app.decision_reasons.map(r =>
      `<span class="reason-item">${esc(r)}</span>`).join('')}
  </div>` : ''}

  ${provenanceHtml(app)}

  ${sensitivityHintsHtml(app)}

  ${fraudHtml(app.fraud_assessment)}

  ${repaymentHtml(app.repayment)}

  ${collectionCalendarHtml(app)}

  ${mitigationHtml(app)}

  ${analystNoteHtml(app)}

  <div class="card-footer">
    <button class="action-btn btn-approve" onclick="decide('${app.application_id}','APPROVE')"
      ${(decided || app.decision === 'DECLINE')?'disabled':''}
      title="${app.decision === 'DECLINE' ? 'Pilot policy: engine declines cannot be overridden' : 'Approve application'}">✓ Approve</button>
    <button class="action-btn btn-manual"  onclick="decide('${app.application_id}','MANUAL_REVIEW')"
      ${decided?'disabled':''}>↩ Route to Review</button>
    <button class="action-btn btn-decline" onclick="decide('${app.application_id}','DECLINE')"
      ${decided?'disabled':''}>✗ Decline</button>
    ${app.analyst_override === 'APPROVE'
      ? app.disbursed
        ? `<button class="action-btn btn-disburse disbursed-ok" disabled>✓ Disbursed</button>`
        : `<button class="action-btn btn-disburse" onclick="disburse('${app.application_id}',${app.approved_mxn})">💸 Send MXN</button>`
      : ''}
    ${decided
      ? `<span class="decision-stamp">Analyst decision recorded</span>`
      : `<span class="decision-stamp" style="color:var(--muted)">Awaiting analyst decision</span>`}
  </div>

</article>`;
}

function sigRow(s) {
  const label = SIG_LABELS[s.name] || s.name;
  if (!s.available) {
    return `<tr>
      <td class="sig-name missing">${esc(label)}</td>
      <td colspan="3"><span class="sig-missing">${esc(s.explanation)}</span></td>
    </tr>`;
  }
  const score = s.raw_score;
  const barCls = score >= 70 ? 'hi' : score >= 40 ? 'mid' : 'lo';
  const tag = s.fallback_used
    ? `<span class="sig-tag fallback">${esc(s.fallback_used)}</span>`
    : s.name === 'bank_cash_flow'
      ? '<span class="sig-tag">Syncfy</span>'
      : s.name === 'google_maps_rating'
        ? '<span class="sig-tag">Places</span>'
        : '';
  return `<tr>
    <td class="sig-name">${esc(label)}${tag}</td>
    <td class="sig-bar-cell">
      <div class="sig-bar-wrap">
        <div class="sig-bar"><div class="sig-bar-fill ${barCls}" style="width:${score}%"></div></div>
        <span class="sig-score">${score.toFixed(1)}</span>
      </div>
    </td>
    <td class="sig-wt">w=${s.effective_weight.toFixed(2)}</td>
    <td class="sig-expl">${esc(s.explanation)}</td>
  </tr>`;
}

function provenanceHtml(app) {
  const src = app.data_sources || {};
  const pill = (label, source, verified) => {
    const synthetic = String(source || '').startsWith('mock');
    const cls = verified ? 'verified' : (synthetic ? 'synthetic' : '');
    const state = verified ? 'verified' : (synthetic ? 'synthetic' : 'unverified');
    return `<span class="source-pill ${cls}">${esc(label)}: ${esc(source || 'missing')} · ${state}</span>`;
  };
  const rationale = app.analyst_reason
    ? `<span class="decision-rationale">Analyst rationale: ${esc(app.analyst_reason)}</span>` : '';
  return `<div class="provenance">
    ${pill('Bank', src.bank, src.bank_verified)}
    ${pill('FMCG', src.fmcg, src.fmcg_verified)}
    <span class="source-pill">Outcome: ${esc(app.outcome_status || 'not_disbursed')}</span>
    ${rationale}
  </div>`;
}

// ── Counter-offer banner ──────────────────────────────────────────────
function counterOfferHtml(app) {
  const reasons = app.decision_reasons || [];
  const coNote = reasons.find(r => r.startsWith('Requested MXN'));
  if (!coNote) return '';
  return `
  <div class="counter-offer-banner">
    <div class="co-icon">⚡</div>
    <div class="co-body">
      <div class="co-title">Counter-offer — Loan amount adjusted</div>
      <div class="co-text">${esc(coNote)}</div>
      <div class="co-amounts">
        <div class="co-amount">
          <span class="co-amount-label">Solicitado</span>
          <span class="co-amount-value declined">MXN ${fmt(app.requested_mxn)}</span>
        </div>
        <div class="co-amount">
          <span class="co-amount-label">Contraoferta</span>
          <span class="co-amount-value offered">MXN ${fmt(app.approved_mxn)}</span>
        </div>
      </div>
    </div>
  </div>`;
}

// ── Sensitivity hints ─────────────────────────────────────────────────
function sensitivityHintsHtml(app) {
  const sens = app.tier_sensitivity || {};
  const path = sens.path || '';
  if (!path || path === 'Optimal — no upgrade path needed') return '';
  const chips = path.split(' · ').map(p =>
    `<span class="sens-chip">↑ ${esc(p)}</span>`
  ).join('');
  return `
  <div class="sensitivity-hints">
    <h3>Upgrade path</h3>
    <div>${chips}</div>
  </div>`;
}

// ── Analyst note ──────────────────────────────────────────────────────
function analystNoteHtml(app) {
  const existing = app.analyst_note || '';
  return `
  <div class="analyst-note-section">
    <h3>Analyst note</h3>
    <div class="analyst-note-row">
      <textarea class="analyst-note-textarea" id="note-${app.application_id}"
        placeholder="Add analysis, rationale, or follow-up...">${esc(existing)}</textarea>
      <button class="btn-save-note" onclick="saveNote('${app.application_id}')">Save</button>
    </div>
  </div>`;
}

// ── Fraud section ─────────────────────────────────────────────────────
function fraudHtml(fa) {
  if (!fa) return '';
  const score = fa.risk_score ?? 0;
  const scoreCls = score < 20 ? 'clean' : score < 50 ? 'warn' : 'bad';
  const checks = fa.checks || {};
  const CHECK_LABELS = {
    phone: 'Phone', rfc: 'RFC', curp: 'CURP',
    address: 'Address', clabe: 'CLABE', ine: 'INE'
  };
  const checkBadges = Object.entries(CHECK_LABELS).map(([k, label]) => {
    const ok = checks[k];
    return `<span class="fraud-check ${ok?'ok':'fail'}">${label}</span>`;
  }).join('');
  const blocks = (fa.hard_blocks||[]).map(b =>
    `<div class="fraud-block">🔴 ${esc(b)}</div>`).join('');
  const flags = (fa.flags||[]).map(f =>
    `<div class="fraud-flag">⚠ ${esc(f)}</div>`).join('');

  return `
  <div class="fraud-section">
    <h3>Fraud screening</h3>
    <div class="fraud-grid">
      <div class="fraud-score-wrap">
        <span class="fraud-score ${scoreCls}">${score.toFixed(0)}<span style="font-size:11px;font-weight:400;color:var(--muted)">/100</span></span>
      </div>
      <div class="fraud-checks">${checkBadges}</div>
    </div>
    ${blocks}${flags}
  </div>`;
}

// ── Repayment section ─────────────────────────────────────────────────
function repaymentHtml(rep) {
  if (!rep) return '';

  function dscrEl(v) {
    if (v == null) return '<span class="rep-value" style="color:var(--muted)">—</span>';
    const cls = v >= 2.5 ? 'green' : v >= 1.5 ? 'amber' : 'red';
    return `<span class="rep-value ${cls}">${v.toFixed(2)}</span>`;
  }
  function burdenEl(v) {
    if (v == null) return '<span class="rep-value" style="color:var(--muted)">—</span>';
    const cls = v <= 0.25 ? 'green' : v <= 0.40 ? 'amber' : 'red';
    return `<span class="rep-value ${cls}">${(v*100).toFixed(1)}%</span>`;
  }
  function bufferEl(v) {
    if (v == null) return '<span class="rep-value" style="color:var(--muted)">—</span>';
    const cls = v >= 1.0 ? 'green' : 'red';
    return `<span class="rep-value ${cls}">${v.toFixed(2)}x</span>`;
  }
  function buroEl(rep) {
    if ((rep.notes||[]).some(n => n.includes('Buro')))
      return '<span class="rep-value rep-buro-warn">NOT CHECKED</span>';
    if ((rep.hard_declines||[]).some(d => d.includes('Buro')))
      return '<span class="rep-value rep-buro-bad">DELINQUENT</span>';
    if ((rep.downgrades||[]).some(d => d.includes('Buro')))
      return '<span class="rep-value rep-buro-warn">MULTI-LENDING</span>';
    return '<span class="rep-value rep-buro-ok">OK</span>';
  }

  const notes = (rep.notes||[]).map(n =>
    `<div class="rep-note">⚠ ${esc(n)}</div>`).join('');

  return `
  <div class="repayment-section">
    <h3>Repayment</h3>
    <div class="rep-grid">
      <div class="rep-item">
        <span class="rep-label">DSCR</span>
        ${dscrEl(rep.dscr)}
      </div>
      <div class="rep-item">
        <span class="rep-label">Burden</span>
        ${burdenEl(rep.burden_ratio)}
      </div>
      <div class="rep-item">
        <span class="rep-label">Stress buffer</span>
        ${bufferEl(rep.stress_buffer_ratio)}
      </div>
      <div class="rep-item">
        <span class="rep-label">Buro</span>
        ${buroEl(rep)}
      </div>
      ${rep.estimated_monthly_net_mxn != null ? `
      <div class="rep-item">
        <span class="rep-label">Net / mo</span>
        <span class="rep-value">MXN ${fmt(rep.estimated_monthly_net_mxn)}</span>
      </div>` : ''}
    </div>
    ${notes}
  </div>`;
}

// ── Mitigation menu (COMMITTEE only) ─────────────────────────────────
function mitigationHtml(app) {
  const menu = app.mitigation_menu;
  if (!menu || !menu.length) return '';

  const ICONS = {
    reduced_amount:   '↘',
    guarantee:        '🛡',
    adjusted_pricing: '↑',
    origination_fee:  '%',
  };

  const rows = menu.map(opt => {
    const icon = ICONS[opt.type] || '·';
    return `
    <div class="mitigation-option">
      <div class="mit-header">
        <span class="mit-icon">${icon}</span>
        <span class="mit-label">${esc(opt.label)}</span>
      </div>
      <div class="mit-rationale">${esc(opt.rationale)}</div>
    </div>`;
  }).join('');

  return `
  <div class="mitigation-section">
    <h3>Opciones de mitigación · comité</h3>
    <div class="mit-intro">
      Opciones estructurales para el comité — no modifican la calificación.
      Documenta la estructura elegida en la nota de analista antes de decidir.
    </div>
    ${rows}
  </div>`;
}

// ── Collection calendar ───────────────────────────────────────────────
function collectionCalendarHtml(app) {
  const cal = app.recommended_collection_days;
  if (!cal) return '';
  const dow = (cal.best_days_of_week || []);
  const dom = (cal.best_days_of_month || []);
  const conf = cal.pattern_confidence ?? null;
  if (!dow.length && !dom.length) return '';
  const confCls = conf == null ? '' : conf >= 0.6 ? 'green' : conf >= 0.3 ? 'amber' : 'red';
  const confStr = conf != null ? `<span class="rep-value ${confCls}" title="Pattern confidence">${(conf*100).toFixed(0)}%</span>` : '';
  const dowPills = dow.map(d => `<span class="sens-chip">${esc(d)}</span>`).join('');
  const domPills = dom.map(d => `<span class="sens-chip">day&nbsp;${esc(String(d))}</span>`).join('');
  return `
  <div class="repayment-section">
    <h3>Calendario de cobranza recomendado</h3>
    <div class="rep-grid">
      ${dow.length ? `<div class="rep-item" style="flex-direction:column;align-items:flex-start;gap:4px">
        <span class="rep-label">Días de semana</span>
        <div>${dowPills}</div>
      </div>` : ''}
      ${dom.length ? `<div class="rep-item" style="flex-direction:column;align-items:flex-start;gap:4px">
        <span class="rep-label">Días del mes</span>
        <div>${domPills}</div>
      </div>` : ''}
      ${confStr ? `<div class="rep-item">
        <span class="rep-label">Confianza</span>
        ${confStr}
      </div>` : ''}
    </div>
    <div class="rep-note" style="color:var(--muted);font-size:11px">
      Basado en patrones de depósito Syncfy (${esc(cal.basis || 'open banking')}) · no modifica la calificación
    </div>
  </div>`;
}

// ── Portfolio bar ─────────────────────────────────────────────────────
async function renderPortfolioBar() {
  try {
    const r = await apiFetch('/api/portfolio');
    const pf = await r.json();
    const bar = document.getElementById('portfolio-bar');
    if (!bar) return;
    const dr = pf.default_rate ?? 0;
    const drCls = dr < 0.10 ? '' : dr < 0.15 ? 'warn' : 'bad';
    bar.innerHTML = `
      <div class="pf-stat"><span class="pf-label">Activos</span><span class="pf-value">${pf.active_loans ?? 0}</span></div>
      <div class="pf-sep"></div>
      <div class="pf-stat"><span class="pf-label">Expuesto</span><span class="pf-value">MXN ${fmt(pf.active_mxn ?? 0)}</span></div>
      <div class="pf-sep"></div>
      <div class="pf-stat"><span class="pf-label">Desembolsados</span><span class="pf-value">${pf.total_disbursed ?? 0}</span></div>
      <div class="pf-sep"></div>
      <div class="pf-stat"><span class="pf-label">Repagados</span><span class="pf-value">${pf.repaid ?? 0}</span></div>
      <div class="pf-sep"></div>
      <div class="pf-stat"><span class="pf-label">Default rate</span><span class="pf-value ${drCls}">${(dr*100).toFixed(1)}%</span></div>
      <div class="pf-sep"></div>
      ${tierDistWidget(pf.by_tier || [])}
      <button class="btn-export" onclick="exportCsv()" title="Export all applications as CSV">↓ CSV</button>
    `;
  } catch(e) { /* portfolio bar is non-critical */ }
}

async function exportCsv() {
  try {
    const response = await apiFetch('/api/export');
    if (!response.ok) throw new Error(response.statusText);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'olin_scoring.csv'; a.click();
    URL.revokeObjectURL(url);
  } catch (e) { toast('Export error: ' + e.message, 'err'); }
}

function tierDistWidget(byTier) {
  if (!byTier.length) return '';
  const totals = {};
  for (const r of byTier) {
    totals[r.tier] = (totals[r.tier] || 0) + r.count;
  }
  const tierNums = Object.keys(totals).map(Number).sort((a,b)=>a-b);
  if (!tierNums.length) return '';
  const maxVal = Math.max(...Object.values(totals));
  const MAX_H = 22;
  const tierColor = t => t === 1 ? '#3fb950' : t <= 12 ? '#e3b341' : '#f85149';
  const tierDecision = t => t === 1 ? 'AUTO' : t <= 12 ? 'COMM' : 'DECL';
  const bars = tierNums.map(t => {
    const n = totals[t];
    const h = Math.max(3, Math.round((n / maxVal) * MAX_H));
    return `<div class="tier-bar-col">
      <div class="tier-bar-fill" style="height:${h}px;background:${tierColor(t)}"></div>
      <div class="tier-bar-lbl">${t}</div>
      <div class="tier-tooltip">Tier ${t} · ${tierDecision(t)} · n=${n}</div>
    </div>`;
  }).join('');
  return `<div class="tier-dist-widget">
    <span class="tier-dist-label">Tier dist</span>
    <div class="tier-bars">${bars}</div>
  </div>`;
}

// ── Disburse ──────────────────────────────────────────────────────────
async function disburse(appId, amount) {
  const btn = document.querySelector(`[data-app-id="${appId}"] .btn-disburse`);
  if (btn) btn.disabled = true;
  try {
    const res = await apiFetch(`/api/apps/${appId}/disburse`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    const sched = data.payment_schedule || {};
    const p1 = sched.payment_1 || {};
    const p2 = sched.payment_2 || {};
    toast(
      `MXN ${fmt(amount)} enviado · Ref: ${data.collection_reference} · ` +
      `Pago 1: ${p1.due_date||'?'} (${fmt(p1.amount_mxn||0)}) · Pago 2: ${p2.due_date||'?'}`,
      'ok'
    );
    await load();
  } catch(e) {
    toast('Disbursement error: ' + e.message, 'err');
    if (btn) btn.disabled = false;
  }
}

// ── Decision action ───────────────────────────────────────────────────
async function decide(appId, decision) {
  const card = document.querySelector(`[data-app-id="${appId}"]`);
  const btns = card.querySelectorAll('.action-btn');
  btns.forEach(b => b.disabled = true);

  try {
    const promptLabel = decision === 'APPROVE' ? 'approval' :
      (decision === 'DECLINE' ? 'decline' : 'review routing');
    const reason = window.prompt(`Reason for ${promptLabel} (required)`);
    if (!reason || reason.trim().length < 5) {
      throw new Error('A decision reason of at least 5 characters is required');
    }
    const res = await apiFetch(`/api/apps/${appId}/decision`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({decision, reason: reason.trim()}),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || res.statusText);
    }
    const label = {APPROVE:'Approved ✓', MANUAL_REVIEW:'Routed to Review ↩', DECLINE:'Declined ✗'}[decision];
    toast(label, 'ok');
    await load();
  } catch(e) {
    toast('Error: ' + e.message, 'err');
    btns.forEach(b => b.disabled = false);
  }
}

// ── Save analyst note ─────────────────────────────────────────────────
async function saveNote(appId) {
  const ta = document.getElementById(`note-${appId}`);
  if (!ta) return;
  const note = ta.value.trim();
  try {
    const res = await apiFetch(`/api/apps/${appId}/note`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({note}),
    });
    if (!res.ok) { const e = await res.json(); throw new Error(e.error || res.statusText); }
    toast('Note saved', 'ok');
  } catch(e) {
    toast('Error saving note: ' + e.message, 'err');
  }
}

// ── Toast ─────────────────────────────────────────────────────────────
function toast(msg, type='ok') {
  const el = document.createElement('div');
  el.className = `toast-item toast-${type}`;
  el.textContent = msg;
  document.getElementById('toast').appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ── Helpers ───────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmt(n) {
  return Number(n || 0).toLocaleString('es-MX', {minimumFractionDigits:0, maximumFractionDigits:0});
}

load();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Merchant-facing application form  (/solicitar)
# ---------------------------------------------------------------------------

APPLY_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Solicita tu crédito — Olin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh}
header{background:#0f1117;border-bottom:1px solid #1e2433;padding:16px 20px;display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:10}
.logo{font-size:20px;font-weight:700;color:#fff;letter-spacing:-0.5px}
.logo span{color:#f59e0b}
.badge{background:#1e2433;color:#94a3b8;font-size:11px;padding:3px 8px;border-radius:20px}
.container{max-width:520px;margin:0 auto;padding:24px 16px 60px}
h1{font-size:24px;font-weight:700;color:#fff;margin-bottom:6px}
.subtitle{color:#64748b;font-size:14px;margin-bottom:28px}
.card{background:#161b27;border:1px solid #1e2433;border-radius:12px;padding:20px;margin-bottom:16px}
.card-title{font-size:13px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.card-title .num{background:#1e2433;color:#f59e0b;width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0}
.field{margin-bottom:14px}
label{display:block;font-size:12px;color:#64748b;margin-bottom:5px;font-weight:500}
input,select,textarea{width:100%;background:#0f1117;border:1px solid #2d3748;border-radius:8px;color:#e2e8f0;padding:11px 13px;font-size:15px;outline:none;transition:border-color .15s}
input:focus,select:focus{border-color:#f59e0b}
select option{background:#161b27}
input::placeholder{color:#4a5568}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.toggle-row{display:flex;gap:0;background:#0f1117;border:1px solid #2d3748;border-radius:8px;overflow:hidden}
.toggle-row label{flex:1;text-align:center;padding:10px;cursor:pointer;font-size:14px;color:#64748b;margin:0;transition:all .15s}
.toggle-row input[type=radio]{display:none}
.toggle-row input[type=radio]:checked+label{background:#1e2433;color:#f59e0b;font-weight:600}
.hint{font-size:12px;color:#4a5568;margin-top:5px}
.collapsible{display:none;padding-top:14px;border-top:1px solid #1e2433;margin-top:14px}
.collapsible.open{display:block}
.submit-btn{width:100%;background:#f59e0b;color:#0f1117;border:none;border-radius:10px;padding:15px;font-size:16px;font-weight:700;cursor:pointer;margin-top:8px;transition:opacity .15s}
.submit-btn:hover{opacity:0.9}
.submit-btn:disabled{opacity:0.5;cursor:not-allowed}
.required{color:#f59e0b}
.error-msg{background:#2d1515;border:1px solid #7f1d1d;color:#fca5a5;border-radius:8px;padding:12px;margin-bottom:16px;font-size:13px;display:none}
.spinner{display:inline-block;width:16px;height:16px;border:2px solid #0f111755;border-top-color:#0f1117;border-radius:50%;animation:spin .6s linear infinite;vertical-align:middle;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
.optional-tag{font-size:10px;color:#4a5568;font-weight:400;margin-left:4px}
</style>
</head>
<body>
<header>
  <div class="logo">Olin<span>·</span></div>
  <div class="badge">Solicitud de crédito</div>
</header>
<div class="container">
  <h1>Solicita tu crédito</h1>
  <p class="subtitle">Completa el formulario. Entre más datos, mejor será tu evaluación.</p>
  <div class="error-msg" id="errorMsg"></div>

  <form id="applyForm">
    <!-- 1. Tu negocio -->
    <div class="card">
      <div class="card-title"><span class="num">1</span>Tu negocio</div>
      <div class="field">
        <label>Nombre del negocio <span class="required">*</span></label>
        <input name="merchant_name" placeholder="Ej. Abarrotes La Esperanza" required autocomplete="off">
      </div>
      <div class="field">
        <label>Tipo de negocio <span class="required">*</span></label>
        <select name="business_type" required>
          <option value="">Selecciona...</option>
          <option value="abarrotes">Abarrotes / Tienda</option>
          <option value="taqueria">Taquería / Comida</option>
          <option value="jugueria">Juguería / Bebidas</option>
          <option value="other">Otro</option>
        </select>
      </div>
      <div class="row">
        <div class="field">
          <label>¿Cuánto necesitas? <span class="required">*</span></label>
          <input name="requested_mxn" type="number" min="5000" max="500000" placeholder="MXN" required>
        </div>
        <div class="field">
          <label>Años abierto <span class="optional-tag">(opcional)</span></label>
          <input name="years_open" type="number" min="0" max="50" step="0.5" placeholder="Ej. 3.5">
        </div>
      </div>
      <div class="field">
        <label>Colonia / Municipio <span class="optional-tag">(opcional)</span></label>
        <input name="colonia" placeholder="Ej. Doctores, CDMX">
      </div>
    </div>

    <!-- 2. Identificación -->
    <div class="card">
      <div class="card-title"><span class="num">2</span>Identificación</div>
      <div class="row">
        <div class="field">
          <label>Teléfono celular</label>
          <input name="phone" type="tel" placeholder="10 dígitos" maxlength="10" inputmode="numeric">
        </div>
        <div class="field">
          <label>RFC <span class="optional-tag">(opcional)</span></label>
          <input name="rfc" placeholder="Ej. GOMA850312HDF" maxlength="13" style="text-transform:uppercase">
        </div>
      </div>
      <div class="field">
        <label>CURP <span class="optional-tag">(opcional)</span></label>
        <input name="curp" placeholder="18 caracteres" maxlength="18" style="text-transform:uppercase">
      </div>
      <p class="hint">Más datos de identidad = menor riesgo percibido = mejor oferta.</p>
    </div>

    <!-- 3. Cuenta de banco -->
    <div class="card">
      <div class="card-title"><span class="num">3</span>Cuenta de banco</div>
      <div class="field">
        <label>¿Tienes cuenta de banco?</label>
        <div class="toggle-row">
          <input type="radio" name="has_bank" id="bank_yes" value="yes">
          <label for="bank_yes">Sí</label>
          <input type="radio" name="has_bank" id="bank_no" value="no" checked>
          <label for="bank_no">No</label>
        </div>
      </div>
      <div class="collapsible" id="bankFields">
        <div class="field">
          <label>Banco</label>
          <input name="bank_name" placeholder="Ej. BBVA, Bancomer, Santander">
        </div>
        <div class="row">
          <div class="field">
            <label>Depósitos al mes (MXN)</label>
            <input name="avg_deposits_mxn" type="number" placeholder="Promedio">
          </div>
          <div class="field">
            <label>Saldo promedio (MXN)</label>
            <input name="avg_balance_mxn" type="number" placeholder="Promedio">
          </div>
        </div>
        <div class="field">
          <label>¿Cuántos meses llevas con esa cuenta?</label>
          <input name="months_with_bank" type="number" min="1" placeholder="Ej. 24">
        </div>
      </div>
    </div>

    <!-- 4. Más sobre tu negocio -->
    <div class="card">
      <div class="card-title"><span class="num">4</span>Más sobre tu negocio</div>
      <div class="field">
        <label>¿Tienes empleados registrados en IMSS?</label>
        <div class="toggle-row">
          <input type="radio" name="has_imss" id="imss_yes" value="yes">
          <label for="imss_yes">Sí</label>
          <input type="radio" name="has_imss" id="imss_no" value="no" checked>
          <label for="imss_no">No</label>
        </div>
      </div>
      <div class="collapsible" id="imssFields">
        <div class="field">
          <label>¿Cuántos empleados tienes en IMSS?</label>
          <input name="imss_employees" type="number" min="1" placeholder="Número de empleados">
        </div>
      </div>
      <div class="field" style="margin-top:14px">
        <label>¿Tienes terminal punto de venta (tarjetas)?</label>
        <div class="toggle-row">
          <input type="radio" name="has_pos" id="pos_yes" value="yes">
          <label for="pos_yes">Sí</label>
          <input type="radio" name="has_pos" id="pos_no" value="no" checked>
          <label for="pos_no">No</label>
        </div>
      </div>
      <div class="collapsible" id="posFields">
        <div class="field">
          <label>Ventas con tarjeta al mes (MXN)</label>
          <input name="pos_monthly_mxn" type="number" placeholder="Promedio mensual">
        </div>
      </div>
    </div>

    <!-- 5. Círculo de Crédito -->
    <div class="card">
      <div class="card-title"><span class="num">5</span>Círculo de Crédito <span class="optional-tag" style="text-transform:none;font-size:11px">(agente: consultar antes de enviar)</span></div>
      <div class="field">
        <label>¿Se consultó el buró?</label>
        <div class="toggle-row">
          <input type="radio" name="buro_checked" id="buro_yes" value="yes">
          <label for="buro_yes">Sí</label>
          <input type="radio" name="buro_checked" id="buro_no" value="no" checked>
          <label for="buro_no">No</label>
        </div>
      </div>
      <div class="collapsible" id="buroFields">
        <div class="row">
          <div class="field">
            <label>Puntaje Círculo</label>
            <input name="buro_score" type="number" min="300" max="850" placeholder="Ej. 680">
          </div>
          <div class="field">
            <label>Adeudos activos</label>
            <input name="buro_delinquencies" type="number" min="0" placeholder="0 si ninguno">
          </div>
        </div>
      </div>
      <p class="hint">Un puntaje Círculo ≥670 habilita aprobación automática.</p>
    </div>

    <button type="submit" class="submit-btn" id="submitBtn">Solicitar crédito →</button>
  </form>
</div>

<script>
function toggle(radioName, containerId) {
  document.querySelectorAll('input[name="'+radioName+'"]').forEach(r => {
    r.addEventListener('change', () => {
      var c = document.getElementById(containerId);
      c.classList.toggle('open', r.value === 'yes' && r.checked);
    });
  });
}
toggle('has_bank', 'bankFields');
toggle('has_imss', 'imssFields');
toggle('has_pos', 'posFields');
toggle('buro_checked', 'buroFields');

document.getElementById('applyForm').addEventListener('submit', async function(e) {
  e.preventDefault();
  var btn = document.getElementById('submitBtn');
  var errEl = document.getElementById('errorMsg');
  errEl.style.display = 'none';
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Evaluando...';

  var fd = new FormData(this);
  var body = {};
  fd.forEach((v, k) => { body[k] = v.trim(); });

  try {
    var resp = await fetch('/solicitar', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    var data = await resp.json();
    if (!resp.ok) {
      errEl.textContent = data.error || 'Error al procesar la solicitud.';
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.innerHTML = 'Solicitar crédito →';
      return;
    }
    window.location.href = '/solicitar/resultado/' + data.application_id;
  } catch(ex) {
    errEl.textContent = 'Error de red. Verifica tu conexión e intenta de nuevo.';
    errEl.style.display = 'block';
    btn.disabled = false;
    btn.innerHTML = 'Solicitar crédito →';
  }
});
</script>
</body>
</html>"""


def _render_apply_result(app_id: str, result) -> str:
    from .models import Decision
    decision = result.decision
    approved = result.approved_amount_mxn
    score = result.score
    cost = result.pricing_fixed_cost_mxn
    reasons = result.decision_reasons or []
    coverage = int(result.data_coverage * 100)
    tier = result.tier

    if decision == Decision.AUTO_APPROVE:
        icon = "✓"
        title = "¡Pre-aprobado!"
        color = "#10b981"
        bg = "#052e1a"
        border = "#065f46"
        subtitle = f"Crédito pre-aprobado por <strong>MXN {approved:,.0f}</strong>"
        next_steps = [
            f"<strong>Monto aprobado:</strong> MXN {approved:,.0f}",
            f"<strong>Costo total (60 días):</strong> MXN {cost:,.0f}",
            "Un ejecutivo te llamará en menos de 2 horas hábiles.",
            "Ten lista tu INE y cuenta CLABE para el desembolso.",
        ]
    elif decision == Decision.DECLINE:
        icon = "✗"
        title = "No aprobado esta vez"
        color = "#ef4444"
        bg = "#2d0f0f"
        border = "#7f1d1d"
        subtitle = "No pudimos aprobar tu solicitud con los datos actuales."
        # Build specific missing data hints from reasons
        missing = []
        r_text = " ".join(reasons).lower()
        if "rfc" in r_text or "identidad" in r_text:
            missing.append("RFC y CURP para verificar tu identidad")
        if "banco" in r_text or "bank" in r_text:
            missing.append("Estado de cuenta bancario de los últimos 3 meses")
        if "círculo" in r_text or "buro" in r_text or "circulo" in r_text:
            missing.append("Consulta de Círculo de Crédito")
        if not missing:
            missing = ["Más información bancaria o de distribuidores"]
        next_steps = (
            ["<strong>Para mejorar tu solicitud, agrega:</strong>"] +
            [f"• {m}" for m in missing] +
            ["Puedes volver a solicitar en 30 días con datos adicionales.",
             "Escríbenos: <a href='mailto:hola@olin.mx' style='color:#94a3b8'>hola@olin.mx</a>"]
        )
    else:  # COMMITTEE
        icon = "⏳"
        title = "En revisión"
        color = "#f59e0b"
        bg = "#1f1208"
        border = "#78350f"
        subtitle = "Tu caso pasa a revisión manual con nuestro equipo."
        next_steps = [
            "Un analista revisará tu caso en las próximas <strong>24–48 horas hábiles</strong>.",
            "Te contactaremos al número registrado con la decisión final.",
            "Ten lista tu INE, CURP y estado de cuenta.",
            "Folio de seguimiento: <strong>" + app_id + "</strong>",
        ]

    reasons_html = "".join(
        f'<li style="color:#94a3b8;font-size:13px;margin-bottom:6px">{r}</li>'
        for r in reasons[:4]
    )
    steps_html = "".join(
        f'<li style="margin-bottom:10px;color:#e2e8f0;font-size:14px">{s}</li>'
        for s in next_steps
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Resultado — Olin</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh}}
header{{background:#0f1117;border-bottom:1px solid #1e2433;padding:16px 20px;display:flex;align-items:center;gap:10px}}
.logo{{font-size:20px;font-weight:700;color:#fff}}.logo span{{color:#f59e0b}}
.container{{max-width:480px;margin:0 auto;padding:32px 16px 60px}}
.result-card{{background:{bg};border:1px solid {border};border-radius:16px;padding:28px 24px;text-align:center;margin-bottom:20px}}
.icon{{font-size:48px;color:{color};margin-bottom:12px}}
.result-title{{font-size:24px;font-weight:700;color:{color};margin-bottom:8px}}
.result-sub{{font-size:16px;color:#e2e8f0;margin-bottom:4px}}
.folio{{font-size:12px;color:#4a5568;margin-top:12px}}
.folio strong{{color:#64748b}}
.card{{background:#161b27;border:1px solid #1e2433;border-radius:12px;padding:20px;margin-bottom:16px}}
.card h3{{font-size:12px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:14px}}
.stat-row{{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #1e2433}}
.stat-row:last-child{{border-bottom:none}}
.stat-label{{font-size:13px;color:#64748b}}
.stat-val{{font-size:14px;color:#e2e8f0;font-weight:600}}
ul{{list-style:none;padding:0}}
.btn{{display:block;width:100%;background:#1e2433;color:#e2e8f0;border:1px solid #2d3748;border-radius:10px;padding:13px;text-align:center;text-decoration:none;font-size:14px;font-weight:600;margin-top:8px}}
</style>
</head>
<body>
<header><div class="logo">Olin<span>·</span></div></header>
<div class="container">
  <div class="result-card">
    <div class="icon">{icon}</div>
    <div class="result-title">{title}</div>
    <div class="result-sub">{subtitle}</div>
    <div class="folio">Folio: <strong>{app_id}</strong></div>
  </div>

  <div class="card">
    <h3>Detalles de tu evaluación</h3>
    <div class="stat-row"><span class="stat-label">Puntaje</span><span class="stat-val">{score:.1f} / 100</span></div>
    <div class="stat-row"><span class="stat-label">Nivel</span><span class="stat-val">Tier {tier}</span></div>
    <div class="stat-row"><span class="stat-label">Cobertura de datos</span><span class="stat-val">{coverage}%</span></div>
    {"<div class='stat-row'><span class='stat-label'>Monto aprobado</span><span class='stat-val' style='color:#10b981'>MXN {:,.0f}</span></div>".format(approved) if approved > 0 else ""}
  </div>

  {"<div class='card'><h3>Notas del análisis</h3><ul>" + reasons_html + "</ul></div>" if reasons_html else ""}

  <div class="card">
    <h3>Próximos pasos</h3>
    <ul>{steps_html}</ul>
  </div>

  <a href="/solicitar" class="btn">← Nueva solicitud</a>
</div>
</body>
</html>"""


def _parse_apply_form(body: dict) -> dict:
    """Map merchant form fields to _build_application payload."""
    app_body: dict = {
        "merchant_name": body.get("merchant_name", "").strip(),
        "business_type": body.get("business_type", "other").strip(),
        "requested_mxn": float(body.get("requested_mxn") or 0),
        "colonia": body.get("colonia", "").strip(),
    }

    # Identity / fraud
    fraud: dict = {}
    phone = body.get("phone", "").strip().replace(" ", "").replace("-", "")
    if phone:
        if not phone.startswith("+"):
            phone = "+52" + phone.lstrip("0")
        fraud["phone_mx"] = phone
    rfc = body.get("rfc", "").strip().upper()
    if rfc:
        fraud["rfc"] = rfc
    curp = body.get("curp", "").strip().upper()
    if curp:
        fraud["curp"] = curp
    if fraud:
        app_body["fraud"] = fraud

    # Bank
    if body.get("has_bank") == "yes":
        monthly_dep = float(body.get("avg_deposits_mxn") or 0)
        avg_bal = float(body.get("avg_balance_mxn") or 0)
        months = float(body.get("months_with_bank") or 0)
        if monthly_dep or avg_bal:
            app_body["bank"] = {
                "months_connected": months or 6,
                "avg_daily_balance_mxn": avg_bal,
                "monthly_deposit_count": max(1, monthly_dep / 4000),
                "monthly_deposit_volume_mxn": monthly_dep,
                "monthly_outflow_volume_mxn": monthly_dep * 0.85,
                "deposit_regularity": 0.70,
                "overdrafts_90d": 0,
                "balance_trend_90d": 0.0,
                "min_daily_balance_mxn": avg_bal * 0.25,
                "source": "agent_form",
                "verified": False,
                "evidence_reference": "",
                "observed_at": "",
            }

    # Tenure
    years = body.get("years_open", "").strip()
    if years:
        app_body["tenure"] = {
            "years_on_google_maps": float(years),
            "years_in_imss": float(years),
            "address_consistent": True,
        }

    # IMSS
    if body.get("has_imss") == "yes":
        emp = body.get("imss_employees", "").strip()
        if emp and emp != "0":
            app_body["imss"] = {"registered_employees": int(emp)}

    # POS
    if body.get("has_pos") == "yes":
        pos_vol = float(body.get("pos_monthly_mxn") or 0)
        if pos_vol:
            app_body["pos"] = {
                "months_of_history": 6,
                "avg_monthly_volume_mxn": pos_vol,
                "volume_consistency": 0.70,
                "trend_3m": 0.0,
            }

    # Círculo de Crédito (buro)
    if body.get("buro_checked") == "yes":
        buro_score_raw = body.get("buro_score", "").strip()
        delinq = int(body.get("buro_delinquencies") or 0)
        app_body["buro"] = {
            "checked": True,
            "active_delinquencies": delinq,
            "active_loans_count": 0,
            "worst_mob_status": "",
            "score": int(buro_score_raw) if buro_score_raw else None,
        }

    return app_body


# ---------------------------------------------------------------------------
# POST /api/applications helpers
# ---------------------------------------------------------------------------

def _build_application(body: dict):
    """Build an Application from the JSON body sent by a bank partner.

    All signal blocks are optional. Unrecognised keys are ignored.
    Required: merchant_name, business_type, requested_mxn.
    """
    from .models import (
        Application, BusinessType,
        BankData, FMCGData, TenureData, POSData,
        MapsRatingData, IMSSPayrollData, BuroData, FraudData,
    )

    merchant_name = str(body["merchant_name"]).strip()
    if not merchant_name:
        raise ValueError("merchant_name is required")

    try:
        btype = BusinessType(str(body["business_type"]).lower())
    except ValueError:
        valid = [e.value for e in BusinessType]
        raise ValueError(f"business_type must be one of {valid}")

    requested = float(body["requested_mxn"])
    if requested <= 0:
        raise ValueError("requested_mxn must be > 0")

    def _sub(key):
        return body.get(key) or {}

    b = _sub("bank")
    bank = BankData(
        months_connected=float(b.get("months_connected", 0)),
        avg_daily_balance_mxn=float(b.get("avg_daily_balance_mxn", 0)),
        monthly_deposit_count=float(b.get("monthly_deposit_count", 0)),
        monthly_deposit_volume_mxn=float(b.get("monthly_deposit_volume_mxn", 0)),
        monthly_outflow_volume_mxn=float(b.get("monthly_outflow_volume_mxn", 0)),
        deposit_regularity=float(b.get("deposit_regularity", 0)),
        overdrafts_90d=int(b.get("overdrafts_90d", 0)),
        balance_trend_90d=float(b.get("balance_trend_90d", 0)),
        min_daily_balance_mxn=float(b.get("min_daily_balance_mxn", 0)),
        source=str(b.get("source", "api")),
        verified=bool(b.get("verified", False)),
        evidence_reference=str(b.get("evidence_reference", "")),
        observed_at=str(b.get("observed_at", "")),
    ) if b else None

    f = _sub("fmcg")
    fmcg = FMCGData(
        months_of_history=float(f.get("months_of_history", 0)),
        weekly_purchase_rate=float(f.get("weekly_purchase_rate", 0)),
        missed_weeks_last_12=int(f.get("missed_weeks_last_12", 0)),
        avg_weekly_purchase_mxn=float(f.get("avg_weekly_purchase_mxn", 0)),
        distributor_confirmed=bool(f.get("distributor_confirmed", False)),
        trend_3m=float(f.get("trend_3m", 0)),
        source=str(f.get("source", "api")),
        verified=bool(f.get("verified", False)),
        evidence_reference=str(f.get("evidence_reference", "")),
        observed_at=str(f.get("observed_at", "")),
    ) if f else None

    t = _sub("tenure")
    tenure = TenureData(
        years_on_google_maps=float(t.get("years_on_google_maps", 0)),
        years_in_imss=float(t.get("years_in_imss", 0)),
        address_consistent=bool(t.get("address_consistent", True)),
    ) if t else None

    p = _sub("pos")
    pos = POSData(
        months_of_history=float(p.get("months_of_history", 0)),
        avg_monthly_volume_mxn=float(p.get("avg_monthly_volume_mxn", 0)),
        volume_consistency=float(p.get("volume_consistency", 0)),
        trend_3m=float(p.get("trend_3m", 0)),
    ) if p else None

    m = _sub("maps")
    maps = MapsRatingData(
        rating=float(m.get("rating", 0)),
        review_count=int(m.get("review_count", 0)),
        review_velocity_6m=int(m.get("review_velocity_6m", 0)),
    ) if m else None

    i = _sub("imss")
    imss = IMSSPayrollData(
        registered_employees=i.get("registered_employees"),
    ) if i else None

    bu = _sub("buro")
    buro = BuroData(
        checked=bool(bu.get("checked", False)),
        active_delinquencies=int(bu.get("active_delinquencies", 0)),
        active_loans_count=int(bu.get("active_loans_count", 0)),
        worst_mob_status=str(bu.get("worst_mob_status", "")),
        score=bu.get("score"),
    ) if bu else None

    fr = _sub("fraud")
    fraud = FraudData(
        phone_mx=str(fr.get("phone_mx", "")),
        rfc=str(fr.get("rfc", "")),
        curp=str(fr.get("curp", "")),
        ine_checked=bool(fr.get("ine_checked", False)),
        address_stated=str(fr.get("address_stated", "")),
    ) if fr else None

    return Application(
        merchant_name=merchant_name,
        business_type=btype,
        requested_amount_mxn=requested,
        colonia=str(body.get("colonia", "")),
        clabe=str(body.get("clabe", "")),
        bank=bank,
        fmcg=fmcg,
        tenure=tenure,
        pos=pos,
        maps=maps,
        imss=imss,
        buro=buro,
        fraud=fraud,
    )


def _format_score_result(app, result) -> dict:
    """Compact, bank-friendly response for POST /api/applications."""
    from dataclasses import asdict
    rep = result.repayment
    return {
        "application_id": result.application_id,
        "merchant_name": result.merchant_name,
        "score": round(result.score, 2),
        "ci_low": round(result.ci_low, 2),
        "ci_high": round(result.ci_high, 2),
        "tier": result.tier,
        "decision": result.decision.value,
        "approved_amount_mxn": result.approved_amount_mxn,
        "pricing_fixed_cost_mxn": result.pricing_fixed_cost_mxn,
        "data_coverage": round(result.data_coverage, 3),
        "decision_reasons": result.decision_reasons,
        "hard_filter_failures": result.hard_filter_failures,
        "repayment": {
            "dscr": rep.dscr,
            "burden_ratio": rep.burden_ratio,
            "hard_declines": rep.hard_declines,
            "downgrades": rep.downgrades,
        } if rep else None,
        "signals": [
            {
                "name": s.name,
                "available": s.available,
                "raw_score": s.raw_score,
                "explanation": s.explanation,
            }
            for s in result.signals
        ],
        "scored_at": result.scored_at,
        "engine_version": result.engine_version,
        "analyst_ui": "http://localhost:8080",
    }


def _record_submission_metadata(sl, application_id: str, body: dict) -> None:
    """Persist consent and pilot metadata supplied with an application.

    Scoring remains possible without consent so an analyst can see what is
    missing; production approval is still fail-closed in the decision route.
    """
    consent = body.get("consent") or {}
    if consent.get("channel") or consent.get("text"):
        sl.record_consent(
            application_id,
            str(consent.get("channel", "")),
            str(consent.get("text", "")),
        )
    fields = {
        "cohort_id": body.get("cohort_id"),
        "case_mode": body.get("case_mode"),
        "partner_case_reference": body.get("partner_case_reference"),
    }
    fields = {k: (str(v).strip() if v is not None else None) for k, v in fields.items()}
    if any(v is not None for v in fields.values()):
        sl.conn.execute(
            "UPDATE scoring_log SET cohort_id=?, case_mode=?, partner_case_reference=? "
            "WHERE application_id=?",
            (fields["cohort_id"], fields["case_mode"], fields["partner_case_reference"], application_id),
        )
        sl.conn.commit()


def _validate_submission_metadata(body: dict) -> None:
    """Reject malformed consent/metadata before a score is written."""
    consent = body.get("consent") or {}
    if consent.get("channel") or consent.get("text"):
        channel = str(consent.get("channel", "")).strip().lower()
        text = str(consent.get("text", "")).strip()
        if channel not in ("whatsapp", "sms", "in_person"):
            raise ValueError("consent.channel must be whatsapp, sms, or in_person")
        if not text:
            raise ValueError("consent.text is required when consent is supplied")
    case_mode = body.get("case_mode")
    if case_mode is not None and str(case_mode).strip().lower() not in ("shadow", "live"):
        raise ValueError("case_mode must be shadow or live")


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence access log

    def _send(self, body: bytes, ctype: str = "text/html; charset=utf-8", status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self._send(body, "application/json; charset=utf-8", status)

    def _require_analyst_auth(self) -> bool:
        if not is_production():
            return True
        from .config import api_keys
        keys = api_keys()
        if not keys:
            self._json({"error": "OLIN_ANALYST_TOKEN is not configured"}, 503)
            return False
        supplied = self.headers.get("X-Olin-Analyst-Token", "").strip()
        if not supplied or not any(hmac.compare_digest(supplied, t) for t in keys.values()):
            self._json({"error": "Analyst authentication required"}, 401)
            return False
        return True

    def _read_json(self, max_bytes: int = 65_536) -> tuple[dict | None, bytes]:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._json({"error": "invalid Content-Length"}, 400)
            return None, b""
        if length <= 0 or length > max_bytes:
            self._json({"error": "request body must be between 1 byte and 64 KB"}, 413)
            return None, b""
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json({"error": "invalid JSON"}, 400)
            return None, raw
        if not isinstance(body, dict):
            self._json({"error": "JSON body must be an object"}, 400)
            return None, raw
        return body, raw

    def _verify_webhook(self, raw: bytes) -> bool:
        if not is_production():
            return True
        secret = webhook_secret()
        if not secret:
            self._json({"error": "OLIN_STP_WEBHOOK_SECRET is not configured"}, 503)
            return False
        supplied = self.headers.get("X-Olin-Signature", "").strip()
        if supplied.startswith("sha256="):
            supplied = supplied[7:]
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied, expected):
            self._json({"error": "invalid webhook signature"}, 401)
            return False
        return True

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/healthz":
            # Deliberately public and non-sensitive: useful for partner uptime
            # checks without exposing the analyst API or database contents.
            self._json({"ok": True, "service": "olin", "mode": runtime_mode()})
        elif path == "/":
            self._send(HTML_PAGE.encode())
        elif path == "/solicitar":
            self._send(APPLY_HTML.encode())
        elif path.startswith("/solicitar/resultado/"):
            app_id = path.split("/solicitar/resultado/")[1].strip("/")
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT raw_result FROM scoring_log WHERE application_id=?", (app_id,)
                ).fetchone()
            if not row:
                self._send(b"<h1>No encontrado</h1>", status=404)
                return
            import json as _j
            from .models import ScoreResult, Decision
            raw = _j.loads(row["raw_result"] or "{}")
            # Reconstruct a minimal result-like object for the renderer
            class _R:
                pass
            r = _R()
            r.application_id = app_id
            r.decision = Decision(raw.get("decision", "DECLINE"))
            r.approved_amount_mxn = raw.get("approved_amount_mxn", 0)
            r.score = raw.get("score", 0)
            r.pricing_fixed_cost_mxn = raw.get("pricing_fixed_cost_mxn", 0)
            r.decision_reasons = raw.get("decision_reasons", [])
            r.data_coverage = raw.get("data_coverage", 0)
            r.tier = raw.get("tier", 14)
            self._send(_render_apply_result(app_id, r).encode())
        elif not self._require_analyst_auth():
            return
        elif path == "/api/apps":
            self._json(self._load_apps())
        elif path.startswith("/api/applications/"):
            app_id = path.split("/api/applications/")[1].strip("/")
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT application_id, merchant_name, score, tier, decision, "
                    "approved_mxn, data_coverage, analyst_override, analyst_reason, "
                    "disbursed, outcome_status, scored_at, raw_result, "
                    "consent_timestamp, consent_channel, cohort_id, case_mode, "
                    "partner_case_reference, partner_decision, partner_reason, "
                    "partner_decision_at, recommendation_agreement "
                    "FROM scoring_log WHERE application_id=?", (app_id,)
                ).fetchone()
            if not row:
                self._json({"error": "not found"}, 404)
            else:
                import json as _json
                raw = _json.loads(row["raw_result"] or "{}")
                self._json({
                    "application_id": row["application_id"],
                    "merchant_name": row["merchant_name"],
                    "score": row["score"],
                    "tier": row["tier"],
                    "decision": row["decision"],
                    "approved_amount_mxn": row["approved_mxn"],
                    "data_coverage": row["data_coverage"],
                    "analyst_override": row["analyst_override"],
                    "analyst_reason": row["analyst_reason"],
                    "disbursed": bool(row["disbursed"]),
                    "outcome_status": row["outcome_status"],
                    "scored_at": row["scored_at"],
                    "decision_reasons": raw.get("decision_reasons", []),
                    "signals": raw.get("signals", []),
                    "consent": {
                        "timestamp": row["consent_timestamp"],
                        "channel": row["consent_channel"],
                    },
                    "pilot": {
                        "cohort_id": row["cohort_id"],
                        "case_mode": row["case_mode"],
                        "partner_case_reference": row["partner_case_reference"],
                        "partner_decision": row["partner_decision"],
                        "partner_reason": row["partner_reason"],
                        "partner_decision_at": row["partner_decision_at"],
                        "recommendation_agreement": row["recommendation_agreement"],
                    },
                })
        elif path == "/api/portfolio":
            from .store import ScoringLog
            with ScoringLog(DB_PATH) as _sl:
                snap = _sl.portfolio_snapshot()
            self._json(snap)
        elif path == "/api/export":
            self._csv_export()
        else:
            self._json({"error": "not found"}, 404)

    def _csv_export(self):
        import csv, io
        from .store import ScoringLog
        cols = ["application_id", "merchant_name", "business_type", "colonia",
                "requested_mxn", "approved_mxn", "score", "ci_low", "ci_high",
                "data_coverage", "decision", "tier", "buro_score", "scored_at",
                "analyst_override", "disbursed", "repaid_on_time", "defaulted",
                "outcome_status", "is_demo", "analyst_reason", "analyst_decision_at",
                "payment_1_amount_mxn", "payment_2_amount_mxn", "analyst_note"]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        with ScoringLog(DB_PATH) as sl:
            sl.conn.row_factory = sqlite3.Row
            rows = sl.conn.execute(
                f"SELECT {','.join(cols)} FROM scoring_log ORDER BY scored_at DESC"
            ).fetchall()
            sl.conn.row_factory = None
        for row in rows:
            w.writerow([row[c] for c in cols])
        body = buf.getvalue().encode("utf-8-sig")  # BOM for Excel
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="olin_scoring.csv"')
        self.send_header("Content-Length", len(body))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parts = urlparse(self.path).path.strip("/").split("/")

        is_webhook = (
            len(parts) == 3 and parts[0] == "api"
            and parts[1] == "webhook" and parts[2] == "stp"
        )
        is_apply = parts == ["solicitar"]
        if not is_webhook and not is_apply and not self._require_analyst_auth():
            return

        # POST /solicitar — public merchant application form submission
        if is_apply:
            body, _ = self._read_json()
            if body is None:
                return
            try:
                _validate_submission_metadata(body)
                app_body = _parse_apply_form(body)
                app = _build_application(app_body)
            except (KeyError, ValueError) as exc:
                self._json({"error": str(exc)}, 400)
                return
            from .scorecard import score_application
            from .portfolio import check_portfolio
            from .graduation import get_graduation_offer
            from .store import ScoringLog
            port = check_portfolio(app, DB_PATH)
            grad = get_graduation_offer(app.clabe or "", DB_PATH)
            result = score_application(app, portfolio_block=port, graduation=grad)
            with ScoringLog(DB_PATH) as sl:
                sl.log(app, result)
                _record_submission_metadata(sl, result.application_id, body)
            self._json({"application_id": result.application_id,
                        "redirect": f"/solicitar/resultado/{result.application_id}"}, 201)
            return

        # POST /api/applications  — submit a new merchant application for scoring
        if parts == ["api", "applications"]:
            body, _ = self._read_json()
            if body is None:
                return
            try:
                _validate_submission_metadata(body)
                app = _build_application(body)
            except (KeyError, ValueError) as exc:
                self._json({"error": f"invalid payload: {exc}"}, 400)
                return
            from .scorecard import score_application
            from .portfolio import check_portfolio
            from .graduation import get_graduation_offer
            from .store import ScoringLog
            port = check_portfolio(app, DB_PATH)
            grad = get_graduation_offer(app.clabe or "", DB_PATH)
            result = score_application(app, portfolio_block=port, graduation=grad)
            with ScoringLog(DB_PATH) as sl:
                sl.log(app, result)
                _record_submission_metadata(sl, result.application_id, body)
            self._json(_format_score_result(app, result), 201)
            return

        # POST /api/apps/{id}/outcome — partner decision for a shadow case.
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "apps" and parts[3] == "outcome":
            body, _ = self._read_json()
            if body is None:
                return
            try:
                from .store import ScoringLog
                with ScoringLog(DB_PATH) as sl:
                    outcome = sl.record_partner_outcome(
                        parts[2], body.get("partner_decision", ""),
                        body.get("partner_reason", ""), body.get("partner_decision_at"),
                    )
            except LookupError as exc:
                self._json({"error": str(exc)}, 404); return
            except ValueError as exc:
                self._json({"error": str(exc)}, 400); return
            self._json(outcome, 200); return

        # POST /api/apps/{id}/disburse
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "apps" and parts[3] == "disburse":
            app_id = parts[2]
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT application_id, merchant_name, clabe, approved_mxn, decision, "
                    "analyst_override, disbursed, is_demo, raw_result "
                    "FROM scoring_log WHERE application_id=?", (app_id,)
                ).fetchone()
            if not row:
                self._json({"error": "not found"}, 404); return
            row = dict(row)
            if row["analyst_override"] != "APPROVE":
                self._json({"error": "Analyst has not approved this application"}, 400); return
            if row["decision"] == "DECLINE":
                self._json({"error": "Engine declines cannot be disbursed during the pilot"}, 400); return
            if is_production() and row["is_demo"]:
                self._json({"error": "Demo applications cannot be disbursed in production"}, 400); return
            if not is_production() and not row["is_demo"]:
                self._json({"error": "Production applications cannot be disbursed in demo mode"}, 400); return
            result_json = json.loads(row.get("raw_result") or "{}")
            approved_mxn = row["approved_mxn"] or 0
            if approved_mxn <= 0:
                self._json({"error": "Approved amount must be greater than zero"}, 400); return
            pricing_cost = result_json.get("pricing_fixed_cost_mxn", 0)
            clabe = row["clabe"] or ""
            merchant_name = row["merchant_name"] or ""
            from .stp import disburse as stp_disburse, DisbursementError
            from .collection import make_collection_ref, payment_schedule as col_schedule
            from .store import ScoringLog
            with ScoringLog(DB_PATH) as sl:
                # Write-first: claim the disbursement slot atomically before calling STP.
                # If the process crashes after STP succeeds but before log_disbursement,
                # disbursed=1 + outcome_status='disburse_pending' prevents a double-send
                # on retry. rollback_disbursement() resets the row if STP itself fails.
                if not sl.claim_disbursement(app_id):
                    self._json({"error": "Already disbursed"}, 400); return
                try:
                    dis = stp_disburse(app_id, approved_mxn, clabe, merchant_name,
                                       concepto=f"Prestamo Olin {app_id[:8].upper()}")
                except DisbursementError as e:
                    sl.rollback_disbursement(app_id, str(e))
                    self._json({"error": str(e)}, 400); return
                if dis.status not in ("sandbox", "sent", "confirmed"):
                    err = dis.error or "STP transfer failed"
                    sl.rollback_disbursement(app_id, err)
                    self._json({"error": err, "status": dis.status}, 502); return
                col_ref = make_collection_ref(app_id)
                sl.log_disbursement(app_id, dis.folio_stp or dis.folio_origen, col_ref)
            sched = col_schedule(app_id, approved_mxn, pricing_cost, dis.timestamp)
            self._json({
                "ok": True, "status": dis.status,
                "folio_stp": dis.folio_stp, "folio_origen": dis.folio_origen,
                "collection_reference": col_ref, "payment_schedule": sched,
            }); return

        # POST /api/webhook/stp
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "webhook" and parts[2] == "stp":
            body, raw = self._read_json()
            if body is None or not self._verify_webhook(raw):
                return
            from .collection import process_incoming_payment
            self._json(process_incoming_payment(body, DB_PATH)); return

        # POST /api/apps/{id}/note
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "apps" and parts[3] == "note":
            body, _ = self._read_json()
            if body is None:
                return
            app_id = parts[2]
            note = str(body.get("note", ""))[:2000]  # cap length
            from .store import ScoringLog
            with ScoringLog(DB_PATH) as sl:
                sl.record_analyst_note(app_id, note)
            self._json({"ok": True}); return

        # POST /api/apps/{id}/decision
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "apps" and parts[3] == "decision":
            body, _ = self._read_json()
            if body is None:
                return
            decision = body.get("decision", "").upper()
            if decision not in ("APPROVE", "MANUAL_REVIEW", "DECLINE"):
                self._json({"error": "decision must be APPROVE | MANUAL_REVIEW | DECLINE"}, 400)
                return
            app_id = parts[2]
            try:
                from .store import ScoringLog
                consent_warning = None
                with ScoringLog(DB_PATH) as sl:
                    if decision == "APPROVE":
                        consent_row = sl.conn.execute(
                            "SELECT consent_timestamp FROM scoring_log WHERE application_id=?",
                            (app_id,),
                        ).fetchone()
                        if not consent_row:
                            raise LookupError("Application not found")
                        if not consent_row[0]:
                            consent_warning = "Círculo consent has not been recorded"
                            if is_production():
                                self._json({"error": consent_warning}, 400)
                                return
                    sl.record_analyst_decision(
                        app_id, decision, str(body.get("reason", ""))[:2000]
                    )
            except LookupError as e:
                self._json({"error": str(e)}, 404)
                return
            except ValueError as e:
                self._json({"error": str(e)}, 400)
                return
            response = {"ok": True}
            if consent_warning:
                response["warning"] = consent_warning
            self._json(response)
        else:
            self._json({"error": "not found"}, 404)

    def _load_apps(self) -> list:  # noqa: C901
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT application_id, merchant_name, business_type, colonia,
                       requested_mxn, approved_mxn, score, ci_low, ci_high,
                       data_coverage, decision, scored_at,
                       analyst_override, analyst_reason, analyst_decision_at,
                       disbursed, graduation_tier, tier, analyst_note, buro_score,
                       is_demo, outcome_status, payment_1_amount_mxn,
                       payment_2_amount_mxn, raw_application, raw_result
                FROM scoring_log
                ORDER BY scored_at DESC
            """).fetchall()
        apps = []
        for row in rows:
            app = dict(row)
            result = json.loads(app.pop("raw_result", "{}"))
            raw_app = json.loads(app.pop("raw_application", "{}"))
            app["signals"]              = result.get("signals", [])
            app["decision_reasons"]     = result.get("decision_reasons", [])
            app["hard_filter_failures"] = result.get("hard_filter_failures", [])
            app["pricing_fixed_cost_mxn"] = result.get("pricing_fixed_cost_mxn", 0)
            app["max_ticket_mxn"]       = result.get("max_ticket_mxn", 0)
            app["repayment"]            = result.get("repayment")
            app["fraud_assessment"]     = result.get("fraud_assessment")
            app["tier_sensitivity"]     = result.get("tier_sensitivity", {})
            app["environment"]          = result.get("environment", raw_app.get("environment", "unspecified"))
            app["production_blocks"]    = result.get("production_blocks", [])
            app["data_sources"] = {
                "bank": (raw_app.get("bank") or {}).get("source", "missing"),
                "bank_verified": bool((raw_app.get("bank") or {}).get("verified", False)),
                "fmcg": (raw_app.get("fmcg") or {}).get("source", "missing"),
                "fmcg_verified": bool((raw_app.get("fmcg") or {}).get("verified", False)),
            }
            app["recommended_collection_days"] = (
                (raw_app.get("bank") or {}).get("recommended_collection_days")
            )
            if not app.get("tier"):
                app["tier"] = result.get("tier", 0)
            # buro_score is already set from the SELECT column; keep as-is
            # Show mitigation menu for all COMMITTEE files not yet finally decided.
            # MANUAL_REVIEW means "sent to committee" — that's when options are needed.
            if (app["decision"] == "COMMITTEE"
                    and app.get("analyst_override") not in ("APPROVE", "DECLINE")):
                app["mitigation_menu"] = _build_mitigation_menu(result, raw_app, app)
            else:
                app["mitigation_menu"] = None
            apps.append(app)
        return apps


# ---------------------------------------------------------------------------
# Mitigation menu (COMMITTEE-band files only)
# ---------------------------------------------------------------------------

_MONTHLY_RATE_DEFAULT = 0.03   # Phase 0 baseline
_RATE_ADJUSTED        = 0.045  # risk-premium alternative
_ORIGINATION_FEE_PCT  = 0.02   # 2% one-time fee
_GUARANTEE_TIERS      = {9, 10, 11, 12}   # C3 thin-file tiers — always suggest
_GUARANTEE_MID_TIERS  = {5, 6, 7, 8}     # C2 mid-band tiers — suggest if DSCR also D2


def _build_mitigation_menu(result: dict, raw_app: dict, app: dict) -> list:
    """
    Generate a menu of structural mitigation options for a COMMITTEE-band file.

    This is an expediente output for the analyst — it does not auto-decide
    anything and does not feed back into the score. The analyst reads the options,
    documents their chosen structure in the analyst note, and records the final
    decision via the normal Approve / Route-to-Review / Decline buttons.

    Returns a list of option dicts, each with:
        type, label, rationale, amounts (if applicable)
    """
    tier = app.get("tier") or 0
    approved = app.get("approved_mxn") or 0.0
    rep = result.get("repayment") or {}
    bank = raw_app.get("bank") or {}
    monthly_inflows = bank.get("monthly_deposit_volume_mxn") or 0.0

    if tier < 1 or tier > 12 or approved <= 0:
        return []

    options: list[dict] = []

    # ── Option A: Reduced amount ──────────────────────────────────────────────
    # Always available for COMMITTEE files; reduces installment burden directly.
    if approved >= 6_000:
        reduced = max(3_000.0, round(approved * 0.70 / 1_000) * 1_000)
        reduced_cost = round(reduced * _MONTHLY_RATE_DEFAULT * 2, 2)
        reduced_installment = round((reduced + reduced_cost) / 2, 2)
        options.append({
            "type": "reduced_amount",
            "label": f"Monto reducido — MXN {reduced:,.0f} (70% del propuesto)",
            "rationale": (
                "Mejora DSCR y burden ratio. "
                f"Cuota mensual: MXN {reduced_installment:,.0f} "
                f"· Costo total: MXN {reduced_cost:,.0f}"
            ),
            "amounts": {
                "approved_mxn": reduced,
                "cost_mxn": reduced_cost,
                "installment_mxn": reduced_installment,
            },
        })

    # ── Option B: Aval / garantía ─────────────────────────────────────────────
    # Required for thin-file (C3, tiers 9-12). Strongly suggested for C2 (5-8)
    # when DSCR is also D2 (borderline repayment).
    dscr = rep.get("dscr")
    dscr_borderline = dscr is not None and dscr < 2.5
    if tier in _GUARANTEE_TIERS or (tier in _GUARANTEE_MID_TIERS and dscr_borderline):
        reason = (
            "Sin Círculo de Crédito en expediente" if tier in _GUARANTEE_TIERS
            else "Buró 600-669 con DSCR borderline"
        )
        cost_baseline = round(approved * _MONTHLY_RATE_DEFAULT * 2, 2)
        one_installment = round((approved + cost_baseline) / 2, 2)
        options.append({
            "type": "guarantee",
            "label": "Garantía / aval — aval personal solidario requerido",
            "rationale": (
                f"{reason}. "
                "El garante debe presentar comprobante de domicilio y estado de cuenta. "
                f"Depósito de garantía alternativo: MXN {one_installment:,.0f} "
                "(equivalente a una cuota)"
            ),
            "amounts": {
                "guarantee_deposit_mxn": one_installment,
            },
        })

    # ── Option C: Precio ajustado ─────────────────────────────────────────────
    # Suggest when risk warrants a rate premium (D2 DSCR band, or mid/thin-file
    # Buró). Does not change the loan amount.
    if dscr_borderline or tier >= 5:
        adj_cost = round(approved * _RATE_ADJUSTED * 2, 2)
        adj_installment = round((approved + adj_cost) / 2, 2)
        options.append({
            "type": "adjusted_pricing",
            "label": f"Precio ajustado — 4.5 % mensual (vs. 3 % estándar)",
            "rationale": (
                "Prima de riesgo por perfil comité. "
                f"Costo total ajustado: MXN {adj_cost:,.0f} "
                f"· Cuota: MXN {adj_installment:,.0f}"
            ),
            "amounts": {
                "rate_pct": _RATE_ADJUSTED * 100,
                "cost_mxn": adj_cost,
                "installment_mxn": adj_installment,
            },
        })

    # ── Option D: Comisión de apertura ────────────────────────────────────────
    # Always available. Reduces Olin's net exposure from Day 1 without changing
    # the credit decision or the pricing rate.
    fee = round(approved * _ORIGINATION_FEE_PCT, 2)
    options.append({
        "type": "origination_fee",
        "label": f"Comisión de apertura — 2 % sobre monto (MXN {fee:,.0f})",
        "rationale": (
            "Cobrada antes del desembolso. Reduce exposición neta inicial. "
            "No modifica el monto aprobado ni la tasa."
        ),
        "amounts": {
            "fee_mxn": fee,
            "net_disbursed_mxn": round(approved - fee, 2),
        },
    })

    return options


# ---------------------------------------------------------------------------
# Demo seed (3 canonical test profiles)
# ---------------------------------------------------------------------------
def seed_demo(db_path: str) -> int:
    """Populate db_path with the 3 demo profiles. Returns number of rows inserted."""
    from .models import (
        Application, BusinessType, BuroData, FraudData,
        FMCGData, BankData, TenureData, POSData, MapsRatingData, IMSSPayrollData,
    )
    from .scorecard import score_application
    from .store import ScoringLog

    cases = [
        Application(
            merchant_name="Maria — Abarrotes Don Chuy",
            business_type=BusinessType.ABARROTES,
            requested_amount_mxn=40_000,
            colonia="Iztapalapa Centro",
            fmcg=FMCGData(months_of_history=18, weekly_purchase_rate=0.96,
                          missed_weeks_last_12=0, avg_weekly_purchase_mxn=8_500,
                          distributor_confirmed=True, trend_3m=0.15),
            bank=BankData(months_connected=3, avg_daily_balance_mxn=22_000,
                          monthly_deposit_count=24,
                          monthly_deposit_volume_mxn=95_000,
                          monthly_outflow_volume_mxn=52_000,
                          deposit_regularity=0.88, overdrafts_90d=0,
                          balance_trend_90d=0.10, min_daily_balance_mxn=9_000),
            tenure=TenureData(years_on_google_maps=11, years_in_imss=8, address_consistent=True),
            pos=POSData(months_of_history=14, avg_monthly_volume_mxn=38_000,
                        volume_consistency=0.82, trend_3m=0.08),
            maps=MapsRatingData(rating=4.6, review_count=132, review_velocity_6m=9),
            imss=None,
            buro=BuroData(checked=True, active_delinquencies=0, active_loans_count=1, score=720),
            fraud=FraudData(phone_mx="5512345678", rfc="CHGU850101AB2",
                            ine_checked=True, address_stated="Iztapalapa Centro CDMX"),
        ),
        Application(
            merchant_name="Roberto — Taqueria El Güero",
            business_type=BusinessType.TAQUERIA,
            requested_amount_mxn=25_000,
            colonia="Doctores",
            fmcg=FMCGData(months_of_history=10, weekly_purchase_rate=0.85,
                          missed_weeks_last_12=2, avg_weekly_purchase_mxn=5_200,
                          distributor_confirmed=True, trend_3m=0.0),
            bank=BankData(months_connected=3, avg_daily_balance_mxn=9_000,
                          monthly_deposit_count=15,
                          monthly_deposit_volume_mxn=38_000,
                          monthly_outflow_volume_mxn=22_000,
                          deposit_regularity=0.70, overdrafts_90d=1,
                          balance_trend_90d=0.0, min_daily_balance_mxn=2_500,
                          source="manual_upload"),
            tenure=TenureData(years_on_google_maps=7, years_in_imss=0, address_consistent=True),
            pos=None,
            maps=MapsRatingData(rating=4.3, review_count=58, review_velocity_6m=4),
            imss=None,
            buro=None,   # no Buró on file → B2, ceiling = COMMITTEE
            fraud=FraudData(phone_mx="8112345678", rfc="GURE900215CD3",
                            ine_checked=True, address_stated="Doctores CDMX"),
        ),
        Application(
            merchant_name="Jugueria La Esquina — 14 meses",
            business_type=BusinessType.JUGUERIA,
            requested_amount_mxn=20_000,
            colonia="Narvarte",
            fmcg=FMCGData(months_of_history=4, weekly_purchase_rate=0.55,
                          missed_weeks_last_12=5, distributor_confirmed=False),
            bank=None,
            tenure=TenureData(years_on_google_maps=1.2, years_in_imss=0),
            pos=None,
            maps=MapsRatingData(rating=4.0, review_count=6, review_velocity_6m=3),
            imss=None,
            buro=None,
            fraud=FraudData(phone_mx="5587654321", rfc="LENA010115MH0",
                            ine_checked=True, address_stated="Narvarte CDMX"),
        ),
    ]

    with ScoringLog(db_path) as log:
        if log.conn.execute("SELECT COUNT(*) FROM scoring_log").fetchone()[0] > 0:
            return 0
        inserted = 0
        for app in cases:
            result = score_application(app)
            log.log(app, result)
            inserted += 1

        # Case 0 — Maria: AUTO_APPROVE, analyst confirms, mark as repaid (historical).
        # record_outcome runs first because it sets analyst_override=NULL (legacy coupling);
        # record_analyst_decision then stamps APPROVE on top without being blocked.
        log.record_outcome(cases[0].application_id, repaid_on_time=True, days_to_repay=58)
        log.record_analyst_decision(
            cases[0].application_id, "APPROVE",
            "Tier 1: Buró limpio 720, DSCR 3.2, score 79. Flujo Syncfy verificado. Sin observaciones.",
        )
        log.record_analyst_note(
            cases[0].application_id,
            "Préstamo 1 de la clienta. 18 meses de historial FEMSA. "
            "Balance mínimo MXN 9,000 — sólido para su volumen. Aprobado sin condiciones.",
        )

        # Case 1 — Roberto: COMMITTEE, sent to manual review with sub-threshold reasoning
        log.record_analyst_decision(
            cases[1].application_id, "MANUAL_REVIEW",
            "Sin Buró en expediente (C3) — techo COMMITTEE. DSCR 2.47 por debajo del umbral 2.50. "
            "Score borderline. Pendiente validar antigüedad real del local y estados de cuenta físicos.",
        )
        log.record_analyst_note(
            cases[1].application_id,
            "Comité requerido: (1) Sin Círculo de Crédito en expediente → no puede AUTO_APPROVE. "
            "(2) DSCR 2.47 está 0.03 por debajo del umbral D1 — un mes malo lo manda a D2. "
            "(3) Score 62 es mid-band (S2). "
            "Acción pendiente: solicitar estado de cuenta de los últimos 3 meses en papel "
            "y validar que el local es propio o lleva más de 5 años en la dirección declarada.",
        )

        # Case 2 — Jugueria: DECLINE, no analyst action required for engine declines
    return inserted


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    global DB_PATH

    parser = argparse.ArgumentParser(description="Olin Analyst Review Interface")
    project_root = Path(__file__).parent.parent
    parser.add_argument("--db",      default=str(default_db_path(project_root)),
                        help="Path to SQLite database")
    parser.add_argument("--port",    type=int, default=8080, help="HTTP port (default 8080)")
    parser.add_argument("--host",    default="127.0.0.1", help="Bind host (default localhost only)")
    parser.add_argument("--seed-demo", action="store_true", help="Seed demo applications into an empty demo DB")
    parser.add_argument("--no-seed", action="store_true", help="Don't auto-seed demo data")
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser window")
    args = parser.parse_args()

    DB_PATH = args.db

    if is_production() and (not api_keys() or not webhook_secret()):
        raise RuntimeError(
            "Production requires OLIN_ANALYST_TOKEN (or OLIN_API_KEYS) and OLIN_STP_WEBHOOK_SECRET"
        )

    from .store import ScoringLog
    with ScoringLog(DB_PATH) as log:  # create/migrate before the first query
        if is_production():
            demo_rows = log.conn.execute(
                "SELECT COUNT(*) FROM scoring_log WHERE is_demo=1"
            ).fetchone()[0]
            if demo_rows:
                raise RuntimeError(
                    f"Production database contains {demo_rows} demo row(s); use a clean production DB"
                )
        else:
            production_rows = log.conn.execute(
                "SELECT COUNT(*) FROM scoring_log WHERE is_demo=0"
            ).fetchone()[0]
            if production_rows:
                raise RuntimeError(
                    f"Demo mode cannot open a database containing {production_rows} "
                    "production row(s)"
                )

    if args.seed_demo and not args.no_seed:
        n = seed_demo(DB_PATH)
        if n:
            print(f"  Seeded {n} demo applications → {DB_PATH}")

    # Count apps
    with sqlite3.connect(DB_PATH) as conn:
        count = conn.execute("SELECT COUNT(*) FROM scoring_log").fetchone()[0]

    url = f"http://{args.host}:{args.port}"
    server = HTTPServer((args.host, args.port), Handler)

    print(f"\n  ┌─────────────────────────────────────────┐")
    print(f"  │  Olin · Analyst Review Interface        │")
    print(f"  │  Mode: {runtime_mode():<33} │")
    print(f"  │  {url:<39} │")
    loaded = f"{count} application{'s' if count != 1 else ''} loaded"
    print(f"  │  {loaded:<39} │")
    print(f"  │  Ctrl+C to stop                         │")
    print(f"  └─────────────────────────────────────────┘\n")

    if not args.no_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    main()
