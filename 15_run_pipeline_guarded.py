#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
15_run_pipeline_guarded.py

Schlanker Safety-Runner um den bestehenden 05_run_pipeline.py.

Ergänzt zwei Qualitäts-Gates, ohne 05_run_pipeline.py zu zerreißen:
1. City Guard vor dem Lead-Filter.
2. Evidence Gate nach Audit/Merge und vor finaler manual_review_queue.

Beispiel:
python 15_run_pipeline_guarded.py --city "Kiel" --contextual --max-pages 2 --transaction-pages 2 --transaction-limit 5 --contextual-pages 1 --contextual-tabs 15 --contextual-limit 5 --restart-every 3 --domain-retries 1
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    print("\n▶ " + " ".join(cmd))
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def ensure(path: str) -> None:
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        raise SystemExit(f"Fehlt oder leer: {path}")


def main() -> None:
    p = argparse.ArgumentParser(description="Guarded BFSG pipeline with City Guard and Evidence Gate")
    p.add_argument("--city", required=True)
    p.add_argument("--locations-file", default="orte_deutschland.csv")
    p.add_argument("--leads-input", default="leads_bfsg.csv")
    p.add_argument("--city-clean", default="leads_bfsg_city_clean.csv")
    p.add_argument("--city-rejected", default="leads_bfsg_city_rejected.csv")
    p.add_argument("--contextual", action="store_true")
    p.add_argument("--max-pages", type=int, default=3)
    p.add_argument("--restart-every", type=int, default=5)
    p.add_argument("--domain-retries", type=int, default=2)
    p.add_argument("--transaction-pages", type=int, default=5)
    p.add_argument("--transaction-timeout", type=int, default=15)
    p.add_argument("--transaction-limit", type=int, default=0)
    p.add_argument("--contextual-pages", type=int, default=3)
    p.add_argument("--contextual-tabs", type=int, default=40)
    p.add_argument("--contextual-timeout", type=int, default=20)
    p.add_argument("--contextual-limit", type=int, default=0)
    p.add_argument("--min-risk", choices=["niedrig", "mittel", "hoch"], default="mittel")
    p.add_argument("--audit-min-score", type=int, default=45)
    p.add_argument("--gate-min-transaction-score", type=int, default=60)
    p.add_argument("--gate-max-score-when-blocked", type=int, default=69)
    args = p.parse_args()

    ensure(args.leads_input)

    # 1. City Guard
    run([
        sys.executable, "13_city_guard.py",
        "--input", args.leads_input,
        "--output", args.city_clean,
        "--rejected-output", args.city_rejected,
        "--city", args.city,
        "--locations-file", args.locations_file,
    ])
    ensure(args.city_clean)

    # 2. Bestehende Pipeline auf gereinigten Leads laufen lassen.
    cmd = [
        sys.executable, "05_run_pipeline.py",
        "--all",
        "--leads-input", args.city_clean,
        "--max-pages", str(args.max_pages),
        "--restart-every", str(args.restart_every),
        "--domain-retries", str(args.domain_retries),
        "--transaction-pages", str(args.transaction_pages),
        "--transaction-timeout", str(args.transaction_timeout),
    ]
    if args.transaction_limit:
        cmd += ["--transaction-limit", str(args.transaction_limit)]
    if args.contextual:
        cmd += [
            "--contextual",
            "--contextual-pages", str(args.contextual_pages),
            "--contextual-tabs", str(args.contextual_tabs),
            "--contextual-timeout", str(args.contextual_timeout),
        ]
        if args.contextual_limit:
            cmd += ["--contextual-limit", str(args.contextual_limit)]

    run(cmd)

    # 3. Evidence Gate nach Audit/Merge.
    gate_input = "audit_results_enriched.csv" if Path("audit_results_enriched.csv").exists() else "audit_results.csv"
    ensure(gate_input)
    run([
        sys.executable, "14_evidence_gate.py",
        "--input", gate_input,
        "--output", "audit_results_gated.csv",
        "--min-transaction-score", str(args.gate_min_transaction_score),
        "--max-score-when-blocked", str(args.gate_max_score_when_blocked),
    ])

    # 4. Finale Review-Queue aus gated Results bauen.
    run([
        sys.executable, "04_filter_quality.py",
        "--input", "audit_results_gated.csv",
        "--output", "manual_review_queue.csv",
        "--rejected-output", "manual_review_rejected.csv",
        "--mode", "audit",
        "--min-risk", args.min_risk,
        "--min-score", str(args.audit_min_score),
        "--exclude-chains",
    ])

    print("\n✅ Guarded Pipeline fertig")
    print("Prüfen:")
    print("  head -n 10 manual_review_queue.csv")
    print("  head -n 10 leads_bfsg_city_rejected.csv")
    print("  head -n 10 audit_results_gated.csv")


if __name__ == "__main__":
    main()
