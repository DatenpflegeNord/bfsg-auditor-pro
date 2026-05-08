#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
14_evidence_gate.py
DatenpflegeNord BFSG Auditor - Evidence Gate

Größter Qualitätsgewinn:
Rot/hoch nur, wenn:
(a) starke Transaktionsindizien vorliegen und
(b) mindestens ein critical/serious Befund im relevanten Nutzerfluss existiert und
(c) harte Evidence vorhanden ist: URL + Evidence JSON oder Screenshot + Top-Issue/Selector-Hinweis.

Dieses Modul behauptet keine Verstöße. Es stuft nur Review-Priorität sauberer ein.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

HARD_ISSUE_MARKERS = [
    "button-name", "link-name", "label", "select-name", "image-alt", "html-has-lang",
    "aria-valid-attr", "aria-required-attr", "aria-allowed-role", "color-contrast",
    "context-focus-offscreen", "context-focus-loop-risk", "context-form-label-candidates",
    "context-icon-name-candidates", "context-image-alt-candidates",
]

FLOW_WORDS = [
    "checkout", "kasse", "warenkorb", "cart", "basket", "payment", "zahlung", "shop",
    "ticket", "booking", "buchen", "reservierung", "termin", "appointment", "konto", "login",
]


def int_value(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        raise SystemExit(f"Input nicht gefunden: {path}")
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        return [{k: str(v or "") for k, v in row.items()} for row in reader], reader.fieldnames or []


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    extra = [
        "Evidence_Gate_Status",
        "Evidence_Gate_Reasons",
        "Evidence_Gate_Original_Risk_Label",
        "Evidence_Gate_Original_Audit_Score",
    ]
    final = list(dict.fromkeys([*fields, *extra]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=final, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def yes(row: dict[str, str], key: str) -> bool:
    return str(row.get(key, "")).strip().lower() in {"yes", "ja", "true", "1"}


def transaction_strong(row: dict[str, str], min_transaction_score: int) -> tuple[bool, str]:
    score = int_value(row.get("Transaction_Score"), 0)
    flags = [
        "Checkout_Found", "Cart_Found", "Product_Price_Found", "Booking_Found",
        "Ticket_Found", "Appointment_Found", "Subscription_Found", "Contract_Form_Found",
    ]
    positives = [f for f in flags if yes(row, f)]
    if score >= min_transaction_score and positives:
        return True, f"transaction_strong(score={score}, flags={','.join(positives)})"
    return False, f"transaction_weak(score={score}, flags={','.join(positives) or '-'})"


def has_critical_or_serious(row: dict[str, str]) -> tuple[bool, str]:
    critical = int_value(row.get("Critical_Total"), 0)
    serious = int_value(row.get("Serious_Total"), 0)
    if critical > 0 or serious > 0:
        return True, f"critical={critical}, serious={serious}"
    return False, f"critical={critical}, serious={serious}"


def relevant_flow_evidence(row: dict[str, str]) -> tuple[bool, str]:
    top = (row.get("Top_Issues") or "").lower()
    urls = " ".join([
        row.get("URL", ""),
        row.get("Transaction_Evidence_URLs", ""),
        row.get("Contextual_Evidence_JSON", ""),
        row.get("Evidence_JSON", ""),
        row.get("Evidence_Screenshot_First", ""),
    ]).lower()

    hard_issue = any(marker in top for marker in HARD_ISSUE_MARKERS)
    flow_word = any(word in urls or word in top for word in FLOW_WORDS)
    evidence_json = bool(row.get("Evidence_JSON") or row.get("Contextual_Evidence_JSON") or row.get("Transaction_Evidence_JSON"))
    screenshot = bool(row.get("Evidence_Screenshot_First"))
    pages = int_value(row.get("Pages_Scanned"), 0)

    if hard_issue and evidence_json and (screenshot or pages >= 1):
        reason = "hard_issue+evidence"
        if flow_word:
            reason += "+flow_hint"
        else:
            reason += "+no_flow_word_but_evidence"
        return True, reason

    return False, f"hard_issue={hard_issue}, flow_word={flow_word}, evidence_json={evidence_json}, screenshot={screenshot}, pages={pages}"


def apply_gate(row: dict[str, str], args: argparse.Namespace) -> dict[str, str]:
    out = dict(row)
    original_label = out.get("BFSG_Risk_Label", "")
    original_score = out.get("Audit_Score", "")
    out["Evidence_Gate_Original_Risk_Label"] = original_label
    out["Evidence_Gate_Original_Audit_Score"] = original_score

    tx_ok, tx_reason = transaction_strong(out, args.min_transaction_score)
    sev_ok, sev_reason = has_critical_or_serious(out)
    ev_ok, ev_reason = relevant_flow_evidence(out)

    reasons = [tx_reason, sev_reason, ev_reason]

    if tx_ok and sev_ok and ev_ok:
        out["Evidence_Gate_Status"] = "red_allowed"
        reasons.append("gate=red_allowed")
        if "hoch" not in original_label.lower():
            out["BFSG_Risk_Label"] = "hoch - Evidence-Gate erfüllt, manuelle Prüfung priorisieren"
        out["Manual_Review_Needed"] = "ja"
        out["Audit_Score"] = str(max(int_value(original_score), args.high_score_floor))
    else:
        # Kein hartes Rot. Nicht verwerfen, aber runterstufen.
        out["Evidence_Gate_Status"] = "red_blocked"
        reasons.append("gate=red_blocked")
        if "hoch" in original_label.lower():
            out["BFSG_Risk_Label"] = "mittel - keine harte Rot-Evidence, manuell prüfen"
        out["Audit_Score"] = str(min(int_value(original_score), args.max_score_when_blocked))
        if not out.get("Manual_Review_Needed"):
            out["Manual_Review_Needed"] = "ja"

    legal = out.get("Legal_Safe_Status", "")
    if "Keine endgültige" not in legal:
        out["Legal_Safe_Status"] = "Automatisch erkannte Barrierefreiheitsrisiken. Keine endgültige BFSG-Verstoßbehauptung ohne manuelle Prüfung."

    out["Evidence_Gate_Reasons"] = " | ".join(reasons)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Apply red/high Evidence Gate to audit results")
    p.add_argument("--input", default="audit_results_enriched.csv")
    p.add_argument("--output", default="audit_results_gated.csv")
    p.add_argument("--min-transaction-score", type=int, default=60)
    p.add_argument("--high-score-floor", type=int, default=75)
    p.add_argument("--max-score-when-blocked", type=int, default=69)
    args = p.parse_args()

    rows, fields = read_csv(Path(args.input))
    out_rows = [apply_gate(row, args) for row in rows]
    write_csv(Path(args.output), out_rows, fields)

    allowed = sum(1 for r in out_rows if r.get("Evidence_Gate_Status") == "red_allowed")
    blocked = sum(1 for r in out_rows if r.get("Evidence_Gate_Status") == "red_blocked")
    print(f"Input: {len(rows)}")
    print(f"Rot erlaubt: {allowed}")
    print(f"Rot blockiert/runtergestuft: {blocked}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
