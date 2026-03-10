#!/usr/bin/env python3
"""
DeviceAtlas — EUDAMED EU Device Import (with import tracking)

Strategy:
1. Page through EUDAMED public API (425K devices, parallel 20-thread download)
2. Load already-tracked basicUdis from deviceatlas_import_tracking to skip
3. Match by exact/fuzzy normalised name to existing devices
4. For each EUDAMED record, write a row to deviceatlas_import_tracking:
   - source       = 'eudamed'
   - source_ref   = basicUdi
   - source_url   = https://ec.europa.eu/tools/eudamed/#/screen/search-device?basicUdi=...
   - fetch_status = 'matched' | 'inserted' | 'skipped_class_i' | 'skipped_no_name'
                   | 'already_imported'
   - device_id    = uuid of matched/inserted device (null if skipped)
   - notes        = human-readable reason + match score if fuzzy

This table lets future imports instantly skip processed records, and lets us
audit exactly which EUDAMED entries were checked, matched, or skipped.
"""

import json, os, re, sys, time, threading, urllib.request, urllib.error, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

SUPABASE_URL        = os.environ["SUPABASE_URL"]
SERVICE_KEY         = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
PROJECT_REF         = os.environ["SUPABASE_PROJECT_REF"]
MGMT_TOKEN_FILE     = "/tmp/mgmt_token.txt"

EUDAMED_BASE    = "https://ec.europa.eu/tools/eudamed/api/devices/basicUdiData"
EUDAMED_LINK    = "https://ec.europa.eu/tools/eudamed/#/screen/search-device?basicUdi={}"
MATCH_THRESHOLD = 0.88
TRACKING_TABLE  = "deviceatlas_import_tracking"
SOURCE          = "eudamed"

# Risk classes we import as new EU-only devices (Class IIa and above)
HIGH_RISK_CLASSES = {
    "refdata.risk-class.class-iia",
    "refdata.risk-class.class-iib",
    "refdata.risk-class.class-iii",
    "refdata.risk-class.class-c",
    "refdata.risk-class.class-d",
}

RISK_CLASS_MAP = {
    "refdata.risk-class.class-i":   "Class I",
    "refdata.risk-class.class-iia": "Class IIa",
    "refdata.risk-class.class-iib": "Class IIb",
    "refdata.risk-class.class-iii": "Class III",
    "refdata.risk-class.class-a":   "Class A",
    "refdata.risk-class.class-b":   "Class B",
    "refdata.risk-class.class-c":   "Class C",
    "refdata.risk-class.class-d":   "Class D",
}

# ── HTTP helpers ──────────────────────────────────────────────────────────────
REST_HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
    "User-Agent": "curl/7.81.0",
}

def mgmt_token() -> str:
    if os.path.exists(MGMT_TOKEN_FILE):
        tok = open(MGMT_TOKEN_FILE).read().strip()
        if tok:
            return tok
    return os.environ.get("SUPABASE_MGMT_TOKEN", "")

def mgmt_query(sql: str) -> list:
    tok = mgmt_token()
    payload = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=payload, method="POST",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                 "User-Agent": "curl/7.81.0"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                result = json.loads(r.read())
                if isinstance(result, dict) and "message" in result:
                    if attempt < 2:
                        time.sleep(5)
                        continue
                    raise RuntimeError(f"MGMT: {result['message']}")
                return result if isinstance(result, list) else []
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if "canceling" in body or e.code == 408:
                time.sleep(10)
                continue
            raise
    return []

def rest_post(path: str, data: list, upsert: bool = False) -> None:
    if not data:
        return
    headers = dict(REST_HEADERS)
    if upsert:
        headers["Prefer"] = "resolution=ignore-duplicates,return=minimal"
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=payload, method="POST", headers=headers,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        pass

# ── Tracking helpers ──────────────────────────────────────────────────────────
def load_tracked_refs() -> set:
    """Load all basicUdis already in the tracking table for EUDAMED."""
    print("Loading already-tracked EUDAMED records...")
    rows = mgmt_query(
        f"SELECT source_ref FROM deviceatlas_import_tracking "
        f"WHERE source='{SOURCE}';"
    )
    refs = {r["source_ref"] for r in rows if r.get("source_ref")}
    print(f"  {len(refs)} records already tracked (will be skipped)")
    return refs

# Collect tracking rows in memory, flush in batches for performance
_tracking_buffer: list = []
_tracking_lock = threading.Lock()

def track(basic_udi: str, status: str, device_id: str | None, notes: str) -> None:
    row = {
        "source": SOURCE,
        "source_ref": basic_udi,
        "source_url": EUDAMED_LINK.format(basic_udi),
        "fetch_status": status,
        "device_id": device_id,
        "notes": notes,
    }
    with _tracking_lock:
        _tracking_buffer.append(row)

def flush_tracking(force: bool = False) -> None:
    with _tracking_lock:
        if not _tracking_buffer or (not force and len(_tracking_buffer) < 500):
            return
        batch = list(_tracking_buffer)
        _tracking_buffer.clear()
    try:
        rest_post(TRACKING_TABLE, batch, upsert=True)
    except Exception as e:
        print(f"  Tracking flush error: {e}")

# ── EUDAMED download ──────────────────────────────────────────────────────────
def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    noise = {"the", "a", "an", "and", "or", "for", "of", "with", "by", "to", "in", "on"}
    return " ".join(t for t in s.split() if t not in noise)

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def fetch_eudamed_page(page: int) -> dict:
    url = f"{EUDAMED_BASE}?page={page}&pageSize=500&lang=en&latestVersion=true"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            if attempt < 4:
                time.sleep(3 * (attempt + 1))
    return {}

def download_all_eudamed() -> list:
    cache_file = "/tmp/eudamed_devices.json"
    if os.path.exists(cache_file):
        print("Loading EUDAMED from disk cache...")
        with open(cache_file) as f:
            devices = json.load(f)
        print(f"  {len(devices)} devices loaded from cache")
        return devices

    print("Downloading EUDAMED devices (~425K records, 20 parallel threads)...")
    first = fetch_eudamed_page(0)
    total_pages = first.get("totalPages", 0)
    total_el    = first.get("totalElements", 0)
    print(f"  API reports: {total_el} devices, {total_pages} pages")

    results: dict[int, list] = {0: first.get("content", [])}
    done_count = [len(results[0])]
    lock = threading.Lock()

    def fetch_page(page: int) -> tuple:
        for attempt in range(4):
            try:
                data = fetch_eudamed_page(page)
                return page, data.get("content", [])
            except Exception:
                if attempt < 3:
                    time.sleep(2 * (attempt + 1))
        return page, []

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(fetch_page, p): p for p in range(1, total_pages)}
        for fut in as_completed(futures):
            pg, content = fut.result()
            with lock:
                results[pg] = content
                done_count[0] += len(content)
                if len(results) % 500 == 0:
                    print(f"  {done_count[0]}/{total_el} devices ({len(results)}/{total_pages} pages)...")

    all_devices = []
    for pg in sorted(results):
        all_devices.extend(results[pg])

    print(f"  Downloaded: {len(all_devices)} devices")
    with open(cache_file, "w") as f:
        json.dump(all_devices, f)
    print(f"  Cached to {cache_file}")
    return all_devices

# ── Matching ──────────────────────────────────────────────────────────────────
def load_existing_devices() -> list:
    print("Loading existing devices from DB...")
    rows = mgmt_query("SELECT id, name FROM deviceatlas_devices ORDER BY id;")
    print(f"  {len(rows)} devices loaded")
    return rows

def match_eu_devices(eudamed_devices: list, existing_devices: list,
                     already_tracked: set) -> tuple:
    """Match EUDAMED devices to existing DB devices. Track every record."""
    exact_map:  dict[str, str] = {}
    bigram_map: dict[tuple, list] = {}

    for dev in existing_devices:
        name = dev.get("name", "") or ""
        norm = normalize(name)
        if not norm:
            continue
        exact_map[norm] = dev["id"]
        tokens = norm.split()
        key = (tokens[0], tokens[1]) if len(tokens) >= 2 else (tokens[0],)
        bigram_map.setdefault(key, []).append((norm, dev["id"]))

    matched: dict[str, dict] = {}  # basicUdi → {device_id, eu_dev, risk_class}
    eu_only: list = []             # unmatched EUDAMED records

    exact_hits = fuzzy_hits = no_match = skipped_no_name = skipped_tracked = 0

    print(f"Matching {len(eudamed_devices)} EUDAMED devices...")
    for i, eu_dev in enumerate(eudamed_devices):
        if i % 50000 == 0 and i > 0:
            print(f"  {i}/{len(eudamed_devices)} — exact={exact_hits} fuzzy={fuzzy_hits} "
                  f"unmatched={no_match}")
            flush_tracking()

        basic_udi  = eu_dev.get("basicUdi", "") or ""
        name       = eu_dev.get("deviceName") or ""
        risk_code  = (eu_dev.get("riskClass") or {}).get("code", "")
        risk_class = RISK_CLASS_MAP.get(risk_code, "Unknown")

        # Skip records already in tracking table (fully processed)
        if basic_udi and basic_udi in already_tracked:
            skipped_tracked += 1
            continue

        if not name:
            skipped_no_name += 1
            track(basic_udi or f"no-udi-{i}", "skipped_no_name", None,
                  f"No deviceName in EUDAMED record; risk_class={risk_class}")
            continue

        norm = normalize(name)

        # Exact match
        if norm in exact_map:
            exact_hits += 1
            device_id = exact_map[norm]
            matched[basic_udi] = {"device_id": device_id, "eu": eu_dev, "risk_class": risk_class}
            track(basic_udi, "matched", device_id,
                  f"Exact name match; risk_class={risk_class}; name='{name}'")
            continue

        # Bigram fuzzy match
        tokens = norm.split()
        key = (tokens[0], tokens[1]) if len(tokens) >= 2 else ((tokens[0],) if tokens else None)

        if key is None:
            no_match += 1
            eu_only.append({"eu": eu_dev, "risk_class": risk_class})
            track(basic_udi, "skipped_no_name", None,
                  f"Name normalises to empty; risk_class={risk_class}")
            continue

        candidates = bigram_map.get(key, [])[:20]
        best_score, best_id = 0.0, None
        for cand_norm, cand_id in candidates:
            s = similarity(norm, cand_norm)
            if s > best_score:
                best_score, best_id = s, cand_id

        if best_score >= MATCH_THRESHOLD and best_id:
            fuzzy_hits += 1
            matched[basic_udi] = {"device_id": best_id, "eu": eu_dev, "risk_class": risk_class}
            track(basic_udi, "matched", best_id,
                  f"Fuzzy match score={best_score:.3f}; risk_class={risk_class}; name='{name}'")
        else:
            no_match += 1
            eu_only.append({"eu": eu_dev, "risk_class": risk_class})
            track(basic_udi, "unmatched", None,
                  f"No DB match; best_score={best_score:.3f}; risk_class={risk_class}; name='{name}'")

    flush_tracking(force=True)
    print(f"Match results: {len(matched)} matched ({exact_hits}+{fuzzy_hits}), "
          f"{no_match} unmatched, {skipped_no_name} no-name, {skipped_tracked} already-tracked")
    return matched, eu_only

# ── Insertion ─────────────────────────────────────────────────────────────────
def insert_eu_approvals_for_matches(matched: dict, existing_eu_refs: set) -> int:
    print(f"Inserting EU approvals for {len(matched)} matched devices...")
    rows, tracking_updates = [], []
    already_done = 0

    for basic_udi, m in matched.items():
        if basic_udi in existing_eu_refs:
            already_done += 1
            # Update tracking status to already_imported
            tracking_updates.append({
                "source": SOURCE, "source_ref": basic_udi,
                "source_url": EUDAMED_LINK.format(basic_udi),
                "fetch_status": "already_imported",
                "device_id": m["device_id"],
                "notes": "EU approval already in deviceatlas_approvals",
            })
            continue
        rows.append({
            "device_id": m["device_id"],
            "disease_state_id": None,
            "country": "EU",
            "status": "Approved",
            "approval_date": None,
            "source_ref": basic_udi,
            "is_active": True,
        })

    print(f"  {len(rows)} to insert, {already_done} already present")
    inserted = 0
    for i in range(0, len(rows), 500):
        try:
            rest_post("deviceatlas_approvals", rows[i:i+500])
            inserted += len(rows[i:i+500])
        except Exception as e:
            print(f"  ERROR approvals batch {i//500}: {e}")
        if inserted % 5000 == 0 and inserted > 0:
            print(f"  {inserted}/{len(rows)} inserted...")

    # Update tracking status for newly inserted rows
    new_tracking = [
        {"source": SOURCE, "source_ref": r["source_ref"],
         "source_url": EUDAMED_LINK.format(r["source_ref"]),
         "fetch_status": "matched_imported",
         "device_id": r["device_id"],
         "notes": "EU approval inserted into deviceatlas_approvals"}
        for r in rows
    ]
    for batch in [new_tracking[i:i+500] for i in range(0, len(new_tracking), 500)]:
        try:
            rest_post(TRACKING_TABLE, batch, upsert=True)
        except Exception as e:
            print(f"  Tracking update error: {e}")
    for batch in [tracking_updates[i:i+500] for i in range(0, len(tracking_updates), 500)]:
        try:
            rest_post(TRACKING_TABLE, batch, upsert=True)
        except Exception as e:
            print(f"  Tracking update error: {e}")

    print(f"  Done. {inserted} EU approvals inserted.")
    return inserted

def insert_eu_only_devices(eu_only: list, existing_eu_refs: set) -> int:
    """Insert EU-only (no FDA/HC match) devices — Class IIa and above only."""
    to_add = [
        e for e in eu_only
        if e["eu"].get("deviceName")
        and e["eu"].get("basicUdi", "") not in existing_eu_refs
        and (e["eu"].get("riskClass") or {}).get("code", "") in HIGH_RISK_CLASSES
    ]
    skipped_class_i = [
        e for e in eu_only
        if e["eu"].get("basicUdi", "") not in existing_eu_refs
        and (e["eu"].get("riskClass") or {}).get("code", "") not in HIGH_RISK_CLASSES
        and e["eu"].get("basicUdi", "")
    ]

    print(f"Inserting {len(to_add)} EU-only devices (Class IIa+); "
          f"skipping {len(skipped_class_i)} Class I")

    # Batch-track the Class I skips
    class_i_tracking = [
        {"source": SOURCE,
         "source_ref": e["eu"]["basicUdi"],
         "source_url": EUDAMED_LINK.format(e["eu"]["basicUdi"]),
         "fetch_status": "skipped_class_i",
         "device_id": None,
         "notes": f"Class I device not inserted; name='{e['eu'].get('deviceName','')}'"}
        for e in skipped_class_i
    ]
    for batch in [class_i_tracking[i:i+500] for i in range(0, len(class_i_tracking), 500)]:
        try:
            rest_post(TRACKING_TABLE, batch, upsert=True)
        except Exception as e:
            print(f"  Class I tracking error: {e}")

    device_rows, approval_rows, tracking_rows = [], [], []

    for item in to_add:
        eu       = item["eu"]
        dev_id   = str(uuid.uuid4())
        basic_udi = eu.get("basicUdi", "")
        name     = (eu.get("deviceName", "") or "").strip()
        rc       = item["risk_class"]

        device_rows.append({
            "id": dev_id, "name": name, "manufacturer": None,
            "category": None, "description": None, "is_active": True,
            "device_class": rc, "clearance_type": "CE Marking",
        })
        approval_rows.append({
            "device_id": dev_id, "disease_state_id": None, "country": "EU",
            "status": "Approved", "approval_date": None,
            "source_ref": basic_udi, "is_active": True,
        })
        tracking_rows.append({
            "source": SOURCE, "source_ref": basic_udi,
            "source_url": EUDAMED_LINK.format(basic_udi),
            "fetch_status": "inserted",
            "device_id": dev_id,
            "notes": f"New EU-only device inserted; risk_class={rc}; name='{name}'",
        })

    d_inserted = a_inserted = 0
    for i in range(0, len(device_rows), 500):
        try:
            rest_post("deviceatlas_devices", device_rows[i:i+500])
            d_inserted += len(device_rows[i:i+500])
            rest_post("deviceatlas_approvals", approval_rows[i:i+500])
            a_inserted += len(approval_rows[i:i+500])
        except Exception as e:
            print(f"  ERROR EU devices batch {i//500}: {e}")
        if d_inserted % 10000 == 0 and d_inserted > 0:
            print(f"  {d_inserted}/{len(device_rows)} EU devices inserted...")

    for batch in [tracking_rows[i:i+500] for i in range(0, len(tracking_rows), 500)]:
        try:
            rest_post(TRACKING_TABLE, batch, upsert=True)
        except Exception as e:
            print(f"  Tracking error: {e}")

    print(f"  Done. {d_inserted} devices + {a_inserted} approvals inserted.")
    return d_inserted

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 62)
    print("DeviceAtlas — EUDAMED EU Device Import (with tracking)")
    print("=" * 62)

    # Load existing EU approval refs (for deduplication)
    existing = mgmt_query(
        "SELECT source_ref FROM deviceatlas_approvals WHERE country='EU';"
    )
    existing_eu_refs = {r["source_ref"] for r in existing if r.get("source_ref")}
    print(f"Existing EU approvals: {len(existing_eu_refs)}")

    # Load already-tracked basicUdis so we can skip them in matching
    already_tracked = load_tracked_refs()

    # Download (uses /tmp/eudamed_devices.json cache if present)
    eudamed_devices = download_all_eudamed()

    # Load our device DB for matching
    existing_devices = load_existing_devices()

    # Match + track every EUDAMED record
    matched, eu_only = match_eu_devices(eudamed_devices, existing_devices, already_tracked)

    # Insert EU approvals for matches, insert EU-only devices
    insert_eu_approvals_for_matches(matched, existing_eu_refs)
    insert_eu_only_devices(eu_only, existing_eu_refs)

    # Summary query
    counts = mgmt_query(
        "SELECT "
        "(SELECT COUNT(*) FROM deviceatlas_devices) as total_devices,"
        "(SELECT COUNT(*) FROM deviceatlas_approvals WHERE country='EU') as eu_approvals,"
        "(SELECT COUNT(*) FROM deviceatlas_approvals WHERE country='US') as us_approvals,"
        "(SELECT COUNT(*) FROM deviceatlas_approvals WHERE country='CA') as ca_approvals,"
        f"(SELECT COUNT(*) FROM {TRACKING_TABLE} WHERE source='{SOURCE}') as tracked_refs,"
        f"(SELECT COUNT(*) FROM {TRACKING_TABLE} WHERE source='{SOURCE}' AND fetch_status='matched') as matched_count,"
        f"(SELECT COUNT(*) FROM {TRACKING_TABLE} WHERE source='{SOURCE}' AND fetch_status='inserted') as inserted_count,"
        f"(SELECT COUNT(*) FROM {TRACKING_TABLE} WHERE source='{SOURCE}' AND fetch_status='skipped_class_i') as class_i_count;"
    )
    if counts:
        c = counts[0]
        print("\n" + "=" * 62)
        print("IMPORT COMPLETE")
        print(f"  Total devices:       {c['total_devices']}")
        print(f"  US approvals:        {c['us_approvals']}")
        print(f"  CA approvals:        {c['ca_approvals']}")
        print(f"  EU approvals:        {c['eu_approvals']}")
        print(f"  EUDAMED records tracked: {c['tracked_refs']}")
        print(f"    → matched to existing: {c['matched_count']}")
        print(f"    → inserted as new:     {c['inserted_count']}")
        print(f"    → skipped (Class I):   {c['class_i_count']}")
        print("=" * 62)


if __name__ == "__main__":
    main()
