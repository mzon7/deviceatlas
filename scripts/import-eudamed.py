#!/usr/bin/env python3
"""
Import EU EUDAMED devices into DeviceAtlas.

Strategy:
1. Page through EUDAMED public API (425K devices)
2. Match by exact/fuzzy normalized name to existing devices
3. Add EU approval records for matched devices
4. Add EU-only devices for unmatched ones (no manufacturer name available)

EUDAMED fields available: deviceName, riskClass, basicUdi, manufacturerSrn
EUDAMED link: https://ec.europa.eu/tools/eudamed/#/screen/search-device?basicUdi={basicUdi}
"""

import json, os, re, sys, time, urllib.request, urllib.error, uuid
from difflib import SequenceMatcher

SUPABASE_URL          = os.environ["SUPABASE_URL"]
SERVICE_KEY           = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
PROJECT_REF           = os.environ["SUPABASE_PROJECT_REF"]
SUPABASE_MGMT_TOKEN   = os.environ["SUPABASE_MGMT_TOKEN"]

EUDAMED_BASE = "https://ec.europa.eu/tools/eudamed/api/devices/basicUdiData"
PAGE_SIZE = 500
MATCH_THRESHOLD = 0.88  # Higher threshold since no manufacturer to disambiguate

RISK_CLASS_MAP = {
    "refdata.risk-class.class-i": "Class I",
    "refdata.risk-class.class-iia": "Class IIa",
    "refdata.risk-class.class-iib": "Class IIb",
    "refdata.risk-class.class-iii": "Class III",
    "refdata.risk-class.class-a": "Class A",
    "refdata.risk-class.class-b": "Class B",
    "refdata.risk-class.class-c": "Class C",
    "refdata.risk-class.class-d": "Class D",
}


def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    noise = {"the", "a", "an", "and", "or", "for", "of", "with", "by", "to", "in", "on"}
    return " ".join(t for t in s.split() if t not in noise)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def fetch_eudamed_page(page: int) -> dict:
    url = f"{EUDAMED_BASE}?page={page}&pageSize={PAGE_SIZE}&lang=en&latestVersion=true"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json",
    })
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt < 4:
                time.sleep(3 * (attempt + 1))
            else:
                raise
    return {}


def rest_post(path: str, data: list) -> int:
    if not data:
        return 200
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=payload, method="POST",
        headers={
            "apikey": SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
            "User-Agent": "curl/7.81.0",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def mgmt_query(sql: str) -> list:
    payload = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {SUPABASE_MGMT_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "curl/7.81.0",
        }
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        result = json.loads(r.read())
        return result if isinstance(result, list) else []


def download_all_eudamed():
    """Download all EUDAMED devices, cache to disk."""
    cache_file = "/tmp/eudamed_devices.json"
    if os.path.exists(cache_file):
        print("Loading EUDAMED from cache...")
        with open(cache_file) as f:
            devices = json.load(f)
        print(f"  {len(devices)} devices loaded from cache")
        return devices

    print("Downloading EUDAMED devices (425K records, this takes ~10 min)...")
    # Get total pages first
    first_page = fetch_eudamed_page(0)
    total_pages = first_page.get("totalPages", 0)
    total_elements = first_page.get("totalElements", 0)
    print(f"  Total: {total_elements} devices, {total_pages} pages")

    all_devices = []
    all_devices.extend(first_page.get("content", []))

    for page in range(1, total_pages):
        try:
            data = fetch_eudamed_page(page)
            all_devices.extend(data.get("content", []))
        except Exception as e:
            print(f"  Error on page {page}: {e} — skipping")
            continue
        if page % 50 == 0:
            print(f"  Downloaded {len(all_devices)}/{total_elements} devices (page {page}/{total_pages})...")

    print(f"  Total downloaded: {len(all_devices)}")
    with open(cache_file, "w") as f:
        json.dump(all_devices, f)
    print(f"  Cached to {cache_file}")
    return all_devices


def load_existing_devices():
    """Load existing device names from our DB for matching."""
    print("Loading existing devices from DB...")
    rows = mgmt_query("SELECT id, name, manufacturer FROM deviceatlas_devices ORDER BY id;")
    print(f"  Loaded {len(rows)} devices")
    return rows


def match_eu_devices(eudamed_devices: list, existing_devices: list):
    """Match EUDAMED devices to existing DB devices by name."""
    # Build exact name → device mapping
    exact_map = {}
    bigram_map = {}

    for dev in existing_devices:
        name = dev.get("name", "") or ""
        norm = normalize(name)
        if not norm:
            continue
        exact_map[norm] = dev["id"]
        tokens = norm.split()
        if len(tokens) >= 2:
            bigram = (tokens[0], tokens[1])
            bigram_map.setdefault(bigram, []).append((norm, dev["id"]))
        elif tokens:
            bigram_map.setdefault((tokens[0],), []).append((norm, dev["id"]))

    matched = {}   # eu_basicUdi -> device_id
    eu_only = []   # EUDAMED devices with no DB match

    print(f"Matching {len(eudamed_devices)} EUDAMED devices...")
    exact_hits = fuzzy_hits = no_match = 0

    for i, eu_dev in enumerate(eudamed_devices):
        if i % 50000 == 0 and i > 0:
            print(f"  {i}/{len(eudamed_devices)} — {exact_hits} exact, {fuzzy_hits} fuzzy, {no_match} unmatched")

        name = eu_dev.get("deviceName") or ""
        if not name:
            no_match += 1
            continue

        norm = normalize(name)
        basic_udi = eu_dev.get("basicUdi", "")
        risk_code = eu_dev.get("riskClass", {}).get("code", "")
        risk_class = RISK_CLASS_MAP.get(risk_code, "Unknown")

        # Exact match
        if norm in exact_map:
            exact_hits += 1
            matched[basic_udi] = {"device_id": exact_map[norm], "eu": eu_dev, "risk_class": risk_class}
            continue

        # Bigram fuzzy match
        tokens = norm.split()
        if len(tokens) >= 2:
            bigram = (tokens[0], tokens[1])
        elif tokens:
            bigram = (tokens[0],)
        else:
            no_match += 1
            eu_only.append({"eu": eu_dev, "risk_class": risk_class})
            continue

        candidates = bigram_map.get(bigram, [])
        if len(candidates) > 20:
            candidates = candidates[:20]

        best_score = 0.0
        best_id = None
        for cand_norm, cand_id in candidates:
            score = similarity(norm, cand_norm)
            if score > best_score:
                best_score = score
                best_id = cand_id

        if best_score >= MATCH_THRESHOLD and best_id:
            fuzzy_hits += 1
            matched[basic_udi] = {"device_id": best_id, "eu": eu_dev, "risk_class": risk_class}
        else:
            no_match += 1
            eu_only.append({"eu": eu_dev, "risk_class": risk_class})

    print(f"Matching complete: {len(matched)} matched ({exact_hits} exact + {fuzzy_hits} fuzzy), {no_match} EU-only")
    return matched, eu_only


def insert_eu_approvals_for_matches(matched: dict, existing_eu_refs: set):
    """Insert EU approval records for matched devices."""
    print(f"Inserting EU approvals for {len(matched)} matched devices...")
    rows = []
    skipped = 0

    for basic_udi, m in matched.items():
        if basic_udi in existing_eu_refs:
            skipped += 1
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

    print(f"  Inserting {len(rows)} rows (skipping {skipped} already imported)...")
    batch_size = 500
    inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        try:
            rest_post("deviceatlas_approvals", batch)
            inserted += len(batch)
        except Exception as e:
            print(f"  ERROR batch {i//batch_size}: {e}")
        if inserted % 5000 == 0 and inserted > 0:
            print(f"  {inserted}/{len(rows)} inserted...")

    print(f"  Done. {inserted} EU approvals inserted.")
    return inserted


def insert_eu_only_devices(eu_only: list, existing_eu_refs: set):
    """Insert EU-only devices (not in our FDA/HC DB)."""
    # Only add a sample to avoid bloating — filter for more interesting risk classes
    # and devices with actual names (skip null)
    to_add = [
        e for e in eu_only
        if e["eu"].get("deviceName")
        and e["eu"].get("basicUdi", "") not in existing_eu_refs
        and e["eu"].get("riskClass", {}).get("code", "") in
            {"refdata.risk-class.class-iii", "refdata.risk-class.class-iib",
             "refdata.risk-class.class-iia", "refdata.risk-class.class-d",
             "refdata.risk-class.class-c"}  # Only Class IIa+ (more significant devices)
    ]

    print(f"Inserting {len(to_add)} EU-only devices (Class IIa+ only)...")

    device_rows = []
    approval_rows = []

    for item in to_add:
        eu = item["eu"]
        dev_id = str(uuid.uuid4())
        basic_udi = eu.get("basicUdi", "")
        name = eu.get("deviceName", "").strip()
        risk_class = item["risk_class"]

        device_rows.append({
            "id": dev_id,
            "name": name,
            "manufacturer": None,  # Not available from EUDAMED public API
            "category": None,
            "description": None,
            "is_active": True,
            "device_class": risk_class,
            "clearance_type": "CE Marking",
        })

        approval_rows.append({
            "device_id": dev_id,
            "disease_state_id": None,
            "country": "EU",
            "status": "Approved",
            "approval_date": None,
            "source_ref": basic_udi,
            "is_active": True,
        })

    batch_size = 500
    d_inserted = a_inserted = 0
    for i in range(0, len(device_rows), batch_size):
        try:
            rest_post("deviceatlas_devices", device_rows[i:i+batch_size])
            d_inserted += len(device_rows[i:i+batch_size])
            rest_post("deviceatlas_approvals", approval_rows[i:i+batch_size])
            a_inserted += len(approval_rows[i:i+batch_size])
        except Exception as e:
            print(f"  ERROR batch {i//batch_size}: {e}")
        if d_inserted % 10000 == 0 and d_inserted > 0:
            print(f"  {d_inserted}/{len(device_rows)} EU devices inserted...")

    print(f"  Done. {d_inserted} EU devices + {a_inserted} approvals inserted.")
    return d_inserted


def main():
    print("=" * 60)
    print("DeviceAtlas — EUDAMED EU Device Import")
    print("=" * 60)

    # Check existing EU data
    existing = mgmt_query("SELECT source_ref FROM deviceatlas_approvals WHERE country='EU';")
    existing_eu_refs = {r["source_ref"] for r in existing if r.get("source_ref")}
    print(f"Existing EU approvals: {len(existing_eu_refs)}")

    # Download EUDAMED
    eudamed_devices = download_all_eudamed()

    # Load existing devices
    existing_devices = load_existing_devices()

    # Match
    matched, eu_only = match_eu_devices(eudamed_devices, existing_devices)

    # Save match cache
    with open("/tmp/eudamed_matches.json", "w") as f:
        json.dump({"matched_count": len(matched), "eu_only_count": len(eu_only)}, f)

    # Insert EU approvals for matched devices
    approved = insert_eu_approvals_for_matches(matched, existing_eu_refs)

    # Insert EU-only devices (Class IIa+)
    eu_devices_added = insert_eu_only_devices(eu_only, existing_eu_refs)

    # Final counts
    counts = mgmt_query(
        "SELECT "
        "(SELECT COUNT(*) FROM deviceatlas_devices) as total_devices, "
        "(SELECT COUNT(*) FROM deviceatlas_approvals WHERE country='EU') as eu_approvals, "
        "(SELECT COUNT(*) FROM deviceatlas_approvals WHERE country='US') as us_approvals, "
        "(SELECT COUNT(*) FROM deviceatlas_approvals WHERE country='CA') as ca_approvals;"
    )
    if counts:
        c = counts[0]
        print("\n" + "=" * 60)
        print("DONE.")
        print(f"  Total devices:  {c['total_devices']}")
        print(f"  US approvals:   {c['us_approvals']}")
        print(f"  CA approvals:   {c['ca_approvals']}")
        print(f"  EU approvals:   {c['eu_approvals']}")
        print("=" * 60)


if __name__ == "__main__":
    main()
