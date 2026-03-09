#!/usr/bin/env python3
"""
Full FDA bulk downloader for DeviceAtlas.
Downloads ALL records from FDA PMA and 510(k) bulk export files.
- PMA:  55,858 records (20 MB zip)
- 510k: 174,201 records (237 MB zip)
Deduplicates against existing DB by device name.
Inserts without AI descriptions (description='') — re-enrichment handles those separately.
"""
import os, json, sys, time, uuid, zipfile, io, urllib.request, urllib.error

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_PROJECT_REF = os.environ["SUPABASE_PROJECT_REF"]
SUPABASE_MGMT_TOKEN = os.environ["SUPABASE_MGMT_TOKEN"]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def mgmt_query(sql: str) -> list:
    url = f"https://api.supabase.com/v1/projects/{SUPABASE_PROJECT_REF}/database/query"
    req = urllib.request.Request(url, data=json.dumps({"query": sql}).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {SUPABASE_MGMT_TOKEN}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "curl/7.81.0")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            return result if isinstance(result, list) else []
    except Exception as e:
        print(f"  SQL err: {e}", flush=True)
        return []

def bulk_insert(rows: list) -> int:
    """Insert a batch of device rows, return count inserted."""
    if not rows:
        return 0
    url = f"{SUPABASE_URL}/rest/v1/deviceatlas_devices"
    req = urllib.request.Request(url, data=json.dumps(rows).encode(), method="POST")
    req.add_header("apikey", SUPABASE_SERVICE_ROLE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_ROLE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return len(rows)
    except urllib.error.HTTPError as e:
        body = e.read()[:300]
        print(f"  Insert err {e.code}: {body}", flush=True)
        return 0

def download_zip(url: str) -> bytes:
    """Download a zip file, return raw bytes."""
    print(f"  Downloading {url.split('/')[-1]}...", flush=True)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "DeviceAtlas/3.0")
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    print(f"  Downloaded {len(data)//1024//1024} MB", flush=True)
    return data

def extract_json(zip_bytes: bytes) -> list:
    """Extract and parse JSON from a zip archive."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        print(f"  Files in zip: {names}", flush=True)
        for name in names:
            if name.endswith(".json"):
                with zf.open(name) as f:
                    data = json.load(f)
                    results = data.get("results", data) if isinstance(data, dict) else data
                    print(f"  Parsed {len(results):,} records from {name}", flush=True)
                    return results
    return []

def get_existing_names() -> set:
    """Load all existing device names (lowercase) from DB."""
    print("  Loading existing device names...", flush=True)
    rows = mgmt_query("SELECT LOWER(name) as n FROM deviceatlas_devices")
    s = {r["n"] for r in rows}
    print(f"  {len(s):,} existing devices in DB", flush=True)
    return s

# ─── Committee → category mapping ─────────────────────────────────────────────

COMMITTEE_CATEGORY = {
    "CV": "Cardiovascular", "Cardiovascular": "Cardiovascular",
    "NE": "Neurology", "Neurology": "Neurology",
    "OP": "Ophthalmology", "Ophthalmic": "Ophthalmology",
    "GU": "Gastroenterology", "Gastroenterology/Urology": "Gastroenterology",
    "OB": "Obstetrics/Gynecology", "Obstetrics/Gynecology": "Obstetrics/Gynecology",
    "AN": "Anesthesiology", "Anesthesiology": "Anesthesiology",
    "RA": "Radiology/Imaging", "Radiology": "Radiology/Imaging",
    "DE": "Dental", "Dental": "Dental",
    "OR": "Orthopedic", "Orthopedic": "Orthopedic",
    "PM": "Physical Medicine", "Physical Medicine/Rehabilitation": "Physical Medicine",
    "HE": "Hematology", "Hematology": "Hematology",
    "CH": "Diagnostics", "Clinical Chemistry": "Diagnostics",
    "IM": "Immunology", "Immunology": "Immunology",
    "MI": "Diagnostics", "Microbiology": "Diagnostics",
    "TX": "Diagnostics", "Toxicology": "Diagnostics",
    "SU": "General Surgery", "General, Plastic Surgery": "General Surgery",
    "MG": "Diagnostics",
    "ENT": "ENT", "Ear, Nose, Throat": "ENT",
    "PU": "Pulmonology", "Pulmonary": "Pulmonology",
    "DE2": "Dermatology",
    "UR": "Urology", "Urology": "Urology",
    "EN": "Endocrinology",
}

def map_category(committee_code: str, committee_desc: str) -> str:
    for key in [committee_code, committee_desc]:
        if key and key in COMMITTEE_CATEGORY:
            return COMMITTEE_CATEGORY[key]
    # Try partial match on description
    desc = (committee_desc or "").lower()
    if "cardio" in desc: return "Cardiovascular"
    if "neuro" in desc: return "Neurology"
    if "ophthal" in desc: return "Ophthalmology"
    if "gastro" in desc or "urol" in desc: return "Gastroenterology"
    if "ortho" in desc: return "Orthopedic"
    if "dent" in desc: return "Dental"
    if "radio" in desc or "imaging" in desc: return "Radiology/Imaging"
    if "obstet" in desc or "gynec" in desc: return "Obstetrics/Gynecology"
    if "anesthes" in desc: return "Anesthesiology"
    if "hematol" in desc: return "Hematology"
    if "immuno" in desc: return "Immunology"
    if "ear" in desc or "nose" in desc or "throat" in desc: return "ENT"
    if "pulmon" in desc or "lung" in desc: return "Pulmonology"
    if "dermatol" in desc or "skin" in desc: return "Dermatology"
    if "endocrin" in desc or "metabol" in desc: return "Endocrinology"
    if "physical" in desc or "rehab" in desc: return "Physical Medicine"
    if "chem" in desc or "micro" in desc or "toxico" in desc: return "Diagnostics"
    return "General Surgery"

# ─── PMA processing ───────────────────────────────────────────────────────────

def process_pma(records: list, existing: set) -> tuple:
    """
    Deduplicate and transform PMA records.
    Skip supplements (supplement_number not empty) — only keep base PMAs.
    Returns (rows_to_insert, updated_existing_set).
    """
    rows = []
    skipped_dup = skipped_supp = 0
    seen_this_batch = set()

    for r in records:
        # Skip supplements — they're amendments to an existing approval
        if r.get("supplement_number", "").strip():
            skipped_supp += 1
            continue

        name = (r.get("trade_name") or r.get("generic_name") or "").strip()
        if not name or len(name) < 3:
            continue

        name_lower = name.lower()[:200]
        if name_lower in existing or name_lower in seen_this_batch:
            skipped_dup += 1
            continue

        seen_this_batch.add(name_lower)
        existing.add(name_lower)

        category = map_category(
            r.get("advisory_committee", ""),
            r.get("advisory_committee_description", "")
        )

        rows.append({
            "id": str(uuid.uuid4()),
            "name": name[:200],
            "manufacturer": (r.get("applicant") or "Unknown")[:200],
            "category": category,
            "description": "",  # to be enriched later
            "is_active": True,
        })

    return rows, existing, skipped_dup, skipped_supp

def process_510k(records: list, existing: set) -> tuple:
    """Transform 510(k) records."""
    rows = []
    skipped_dup = 0
    seen_this_batch = set()

    for r in records:
        name = (r.get("device_name") or "").strip()
        if not name or len(name) < 3:
            continue

        # Only include cleared devices
        if r.get("decision_code") not in ("SESE", "SESP", "SESK", "SESN", "SESE", "SE"):
            continue

        name_lower = name.lower()[:200]
        if name_lower in existing or name_lower in seen_this_batch:
            skipped_dup += 1
            continue

        seen_this_batch.add(name_lower)
        existing.add(name_lower)

        category = map_category(
            r.get("advisory_committee", ""),
            r.get("advisory_committee_description", "")
        )

        rows.append({
            "id": str(uuid.uuid4()),
            "name": name[:200],
            "manufacturer": (r.get("applicant") or "Unknown")[:200],
            "category": category,
            "description": "",
            "is_active": True,
        })

    return rows, existing, skipped_dup

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60, flush=True)
    print("FDA Bulk Device Loader — DeviceAtlas", flush=True)
    print("=" * 60, flush=True)

    existing = get_existing_names()
    starting_count = len(existing)

    total_inserted = 0
    INSERT_BATCH = 500  # rows per Supabase insert call

    # ── 1. PMA (55,858 records, ~21 MB zip) ──────────────────────────────────
    print("\n[1/2] Downloading FDA PMA database (all 55,858 records)...", flush=True)
    pma_url = "https://download.open.fda.gov/device/pma/device-pma-0001-of-0001.json.zip"
    try:
        pma_zip = download_zip(pma_url)
        pma_records = extract_json(pma_zip)
        del pma_zip  # free memory

        print(f"  Processing {len(pma_records):,} PMA records...", flush=True)
        to_insert, existing, skip_dup, skip_supp = process_pma(pma_records, existing)
        del pma_records

        print(f"  New unique devices: {len(to_insert):,} | Supplements skipped: {skip_supp:,} | Duplicates: {skip_dup:,}", flush=True)

        # Insert in batches
        for i in range(0, len(to_insert), INSERT_BATCH):
            batch = to_insert[i:i+INSERT_BATCH]
            n = bulk_insert(batch)
            total_inserted += n
            print(f"  PMA inserted {i+n}/{len(to_insert):,}...", flush=True)
            time.sleep(0.1)

        print(f"  ✓ PMA done. Total inserted so far: {total_inserted:,}", flush=True)
    except Exception as e:
        print(f"  ERROR in PMA: {e}", flush=True)

    # ── 2. 510(k) (174,201 records, ~237 MB zip) ──────────────────────────────
    print("\n[2/2] Downloading FDA 510(k) database (all 174,201 records)...", flush=True)
    k510_url = "https://download.open.fda.gov/device/510k/device-510k-0001-of-0001.json.zip"
    try:
        k510_zip = download_zip(k510_url)
        k510_records = extract_json(k510_zip)
        del k510_zip

        print(f"  Processing {len(k510_records):,} 510(k) records...", flush=True)
        to_insert, existing, skip_dup = process_510k(k510_records, existing)
        del k510_records

        print(f"  New unique devices: {len(to_insert):,} | Duplicates: {skip_dup:,}", flush=True)

        for i in range(0, len(to_insert), INSERT_BATCH):
            batch = to_insert[i:i+INSERT_BATCH]
            n = bulk_insert(batch)
            total_inserted += n
            if i % 5000 == 0:
                print(f"  510k inserted {i+n}/{len(to_insert):,}...", flush=True)
            time.sleep(0.05)

        print(f"  ✓ 510(k) done.", flush=True)
    except Exception as e:
        print(f"  ERROR in 510(k): {e}", flush=True)

    # ── Final count ────────────────────────────────────────────────────────────
    final = mgmt_query("SELECT COUNT(*) as c FROM deviceatlas_devices")
    final_count = final[0]["c"] if final else "?"
    print(f"\n{'='*60}", flush=True)
    print(f"✓ Complete!", flush=True)
    print(f"  Started with: {starting_count:,} devices", flush=True)
    print(f"  Inserted:     {total_inserted:,} new devices", flush=True)
    print(f"  DB total:     {final_count:,} devices", flush=True)

if __name__ == "__main__":
    main()
