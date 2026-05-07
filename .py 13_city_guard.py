[1mdiff --git a/01_collect_leads.py b/01_collect_leads.py[m
[1mindex 44a0a1e..5c1d9fb 100644[m
[1m--- a/01_collect_leads.py[m
[1m+++ b/01_collect_leads.py[m
[36m@@ -360,6 +360,27 @@[m [mclass PlacesClient:[m
         return res.get("result", {}).get("website", "") or ""[m
 [m
 [m
[32m+[m[32mdef remaining_request_budget(max_requests: int, used_requests: int) -> int:[m
[32m+[m[32m    if max_requests <= 0:[m
[32m+[m[32m        return 10**9[m
[32m+[m[32m    return max(0, max_requests - used_requests)[m
[32m+[m
[32m+[m
[32m+[m[32mdef should_continue_deep_scan([m
[32m+[m[32m    *,[m
[32m+[m[32m    max_requests: int,[m
[32m+[m[32m    used_requests: int,[m
[32m+[m[32m    remaining_plz_count: int,[m
[32m+[m[32m    seed_limit: int,[m
[32m+[m[32m    min_deep_requests_per_plz: int,[m
[32m+[m[32m) -> bool:[m
[32m+[m[32m    if max_requests <= 0:[m
[32m+[m[32m        return True[m
[32m+[m[32m    budget_left = remaining_request_budget(max_requests, used_requests)[m
[32m+[m[32m    reserve_for_remaining = remaining_plz_count * max(1, seed_limit + min_deep_requests_per_plz)[m
[32m+[m[32m    return budget_left > reserve_for_remaining[m
[32m+[m
[32m+[m
 def seed_plz(client: PlacesClient, plz: str, city: str, seeds: list[str], args: argparse.Namespace) -> tuple[bool, list[str]]:[m
     reasons: list[str] = [][m
     hits = 0[m
[36m@@ -462,6 +483,8 @@[m [mdef main() -> None:[m
     parser.add_argument("--max-requests", type=int, default=500, help="0 = keine Budgetbremse")[m
     parser.add_argument("--max-pages", type=int, default=1)[m
     parser.add_argument("--per-query-limit", type=int, default=15)[m
[32m+[m[32m    parser.add_argument("--min-deep-requests-per-plz", type=int, default=4, help="Reserviert Mindest-Deep-Budget pro verbleibender PLZ")[m
[32m+[m[32m    parser.add_argument("--min_deep_requests_per_plz", dest="min_deep_requests_per_plz", type=int, help=argparse.SUPPRESS)[m
     parser.add_argument("--check-dns", action="store_true", help="DNS-Erreichbarkeit der Domain prüfen")[m
     parser.add_argument("--exclude-chains", action="store_true", default=True)[m
     parser.add_argument("--include-chains", dest="exclude_chains", action="store_false")[m
[36m@@ -548,6 +571,16 @@[m [mdef main() -> None:[m
 [m
             print("   ✅ Seed-Treffer. Starte Deep-Scan.")[m
             for kw in deep_keywords:[m
[32m+[m[32m                remaining_plz = len(locations) - idx[m
[32m+[m[32m                if not should_continue_deep_scan([m
[32m+[m[32m                    max_requests=args.max_requests,[m
[32m+[m[32m                    used_requests=client.request_count,[m
[32m+[m[32m                    remaining_plz_count=remaining_plz,[m
[32m+[m[32m                    seed_limit=args.seed_limit,[m
[32m+[m[32m                    min_deep_requests_per_plz=args.min_deep_requests_per_plz,[m
[32m+[m[32m                ):[m
[32m+[m[32m                    print("   ⚠️ Deep-Scan gestoppt: Budget für verbleibende PLZ reserviert.")[m
[32m+[m[32m                    break[m
                 job_id = f"{plz}|{kw}"[m
                 if job_id in set(state.get("completed_jobs", [])):[m
                     continue[m
