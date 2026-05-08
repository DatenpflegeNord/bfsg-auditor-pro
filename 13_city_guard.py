#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
13_city_guard.py
DatenpflegeNord BFSG Auditor - City Guard

Filtert nach der Lead-Sammlung falsche Stadt/PLZ, Behörden, Ketten und Domains mit anderer Stadt im Namen.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from urllib.parse import urlparse

PUBLIC_MARKERS = [
    "stadtverwaltung", "rathaus", "bürgerbüro", "buergerbuero", "bürgerservice", "buergerservice",
    "finanzamt", "jobcenter", "arbeitsagentur", "polizei", "gericht", "amtsgericht",
    "landeshauptstadt", "hansestadt", "kreisverwaltung", "gemeinde", "amt ",
    "universitätsklinikum", "uniklinikum", "klinikum", "uksh",
    "touristeninformation", "tourismusinformation", "stadtwerke",
    "local_government_office", "city_hall", "courthouse", "police",
]

PUBLIC_DOMAINS_EXACT = {"kiel.de", "luebeck.de", "lübeck.de", "hamburg.de", "berlin.de"}

CHAIN_DOMAINS = {
    "mediamarkt.de", "saturn.de", "rossmann.de", "dm.de", "mueller.de",
    "telekom.de", "shopseite.telekom.de", "o2online.de", "vodafone.de",
    "falke.com", "ihg.com", "h-hotels.com", "hrewards.com", "booking.com",
    "amazon.de", "ebay.de", "otto.de", "zalando.de", "citti-park.de",
    "thalia.de", "hugendubel.de", "apollo.de", "fielmann.de",
}

KNOWN_CITY_TERMS = {
    "kiel", "luebeck", "lubeck", "lübeck", "hamburg", "berlin", "flensburg", "neumuenster",
    "neumünster", "rostock", "schwerin", "bad-segeberg", "badsegeberg", "eutin",
    "preetz", "plön", "ploen", "schleswig", "eckernfoerde", "eckernförde", "rendsburg",
}


def norm(value: str) -> str:
    value = str(value or "").strip().lower()
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def slug(value: str) -> str:
    return norm(value).replace(" ", "-")


def compact(value: str) -> str:
    return norm(value).replace(" ", "")


def normalize_domain(value: str) -> str:
    value = str(value or "").strip().lower()
    if "://" in value:
        value = urlparse(value).netloc.lower()
    value = value.split("/")[0].strip()
    return value[4:] if value.startswith("www.") else value


def row_domain(row: dict[str, str]) -> str:
    for key in ["normalized_domain", "domain", "Domain"]:
        if row.get(key):
            return normalize_domain(row[key])
    for key in ["url", "URL", "Website", "website"]:
        if row.get(key):
            return normalize_domain(row[key])
    return ""


def detect_delimiter(sample: str) -> str:
    return ";" if sample.count(";") >= sample.count(",") else ","


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        raise SystemExit(f"Input nicht gefunden: {path}")
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    delimiter = detect_delimiter(sample)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        return [{k: str(v or "") for k, v in row.items()} for row in reader], reader.fieldnames or []


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    final_fields = list(dict.fromkeys([*fields, "City_Guard_Status", "City_Guard_Reasons"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=final_fields, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_city_plzs(locations_file: Path, city: str) -> set[str]:
    wanted = norm(city)
    text = locations_file.read_text(encoding="utf-8-sig", errors="replace")
    delimiter = detect_delimiter(text[:4096])
    plzs: set[str] = set()
    with locations_file.open("r", encoding="utf-8-sig", newline="") as f:
        for raw in csv.reader(f, delimiter=delimiter):
            cells = [str(c or "").strip() for c in raw if str(c or "").strip()]
            if not cells or any(norm(c) in {"plz", "postleitzahl", "zip"} for c in cells):
                continue
            plz = next((c for c in cells if re.fullmatch(r"\d{5}", c)), "")
            if plz and any(norm(c) == wanted for c in cells):
                plzs.add(plz)
    return plzs


def row_city(row: dict[str, str]) -> str:
    for key in ["city", "Lead_City", "City", "Ort"]:
        if row.get(key):
            return row[key]
    return ""


def row_plz(row: dict[str, str]) -> str:
    for key in ["plz", "Lead_PLZ", "PLZ"]:
        if row.get(key):
            return re.sub(r"\D", "", row[key])[:5]
    blob = " ".join(str(row.get(k, "") or "") for k in ["formatted_address", "Adresse_Text", "address"])
    m = re.search(r"\b(\d{5})\b", blob)
    return m.group(1) if m else ""


def row_address(row: dict[str, str]) -> str:
    return " ".join(str(row.get(k, "") or "") for k in ["formatted_address", "Adresse_Text", "address"])


def is_chain(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in CHAIN_DOMAINS)


def looks_public(row: dict[str, str], domain: str) -> bool:
    blob = norm(" ".join(str(v or "") for v in row.values()))
    if domain in PUBLIC_DOMAINS_EXACT:
        return True
    if domain.endswith(".kiel.de") or domain.endswith(".luebeck.de") or domain.endswith(".hamburg.de") or domain.endswith(".berlin.de"):
        return True
    return any(norm(marker) in blob for marker in PUBLIC_MARKERS)


def domain_contains_other_city(domain: str, target_city: str) -> str:
    target_terms = {slug(target_city), compact(target_city)}
    d = domain.replace(".", "-").replace("_", "-")
    for term in sorted(KNOWN_CITY_TERMS, key=len, reverse=True):
        term_norms = {slug(term), compact(term)}
        if term_norms & target_terms:
            continue
        for candidate in term_norms:
            if len(candidate) >= 4 and candidate in d:
                return candidate
    return ""


def evaluate(row: dict[str, str], city: str, city_plzs: set[str], args: argparse.Namespace) -> tuple[bool, list[str]]:
    domain = row_domain(row)
    if not domain:
        return False, ["no_domain"]

    if looks_public(row, domain) and not args.include_public:
        return False, ["public_sector_or_public_domain"]

    if is_chain(domain) and args.exclude_chains:
        return False, ["known_chain_domain"]

    c = norm(row_city(row))
    target = norm(city)
    plz = row_plz(row)
    address = norm(row_address(row))
    city_ok = c == target or target in address
    plz_ok = bool(plz and plz in city_plzs)

    if not city_ok and not plz_ok:
        return False, [f"city_plz_mismatch(city={c or '-'}, plz={plz or '-'})"]

    other_city = domain_contains_other_city(domain, city)
    if other_city and args.reject_other_city_in_domain:
        return False, [f"domain_contains_other_city:{other_city}"]

    return True, ["city_guard_pass"]


def main() -> None:
    p = argparse.ArgumentParser(description="City Guard Filter for BFSG Leads")
    p.add_argument("--input", required=True)
    p.add_argument("--output", default="leads_bfsg_city_clean.csv")
    p.add_argument("--rejected-output", default="leads_bfsg_city_rejected.csv")
    p.add_argument("--city", required=True)
    p.add_argument("--locations-file", default="orte_deutschland.csv")
    p.add_argument("--include-public", action="store_true")
    p.add_argument("--exclude-chains", action="store_true", default=True)
    p.add_argument("--include-chains", dest="exclude_chains", action="store_false")
    p.add_argument("--reject-other-city-in-domain", action="store_true", default=True)
    args = p.parse_args()

    city_plzs = load_city_plzs(Path(args.locations_file), args.city)
    if not city_plzs:
        raise SystemExit(f"Keine PLZ für Stadt gefunden: {args.city}")

    rows, fields = read_csv(Path(args.input))
    kept: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []

    for row in rows:
        keep, reasons = evaluate(row, args.city, city_plzs, args)
        row["City_Guard_Status"] = "kept" if keep else "rejected"
        row["City_Guard_Reasons"] = " | ".join(reasons)
        if keep:
            kept.append(row)
        else:
            rejected.append(row)

    write_csv(Path(args.output), kept, fields)
    write_csv(Path(args.rejected_output), rejected, fields)

    print(f"Stadt: {args.city}")
    print(f"PLZ erlaubt: {', '.join(sorted(city_plzs))}")
    print(f"Input: {len(rows)}")
    print(f"Behalten: {len(kept)} -> {args.output}")
    print(f"Verworfen: {len(rejected)} -> {args.rejected_output}")
    if rejected[:10]:
        print("Top verworfen:")
        for row in rejected[:10]:
            name = row.get("business_name") or row.get("Company_Name") or ""
            print(f"  {row_domain(row):<35} | {name[:50]:<50} | {row.get('City_Guard_Reasons')}")


if __name__ == "__main__":
    main()
