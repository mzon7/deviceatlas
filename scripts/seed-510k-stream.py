#!/usr/bin/env python3
"""
Stream-processes the FDA 510(k) bulk JSON without loading all into RAM.
Downloads zip → extracts to disk → reads objects one at a time → bulk inserts.
"""
import os, json, sys, time, uuid, zipfile, urllib.request

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_PROJECT_REF = os.environ["SUPABASE_PROJECT_REF"]
SUPABASE_MGMT_TOKEN = os.environ["SUPABASE_MGMT_TOKEN"]

ZIP_URL = "https://download.open.fda.gov/device/510k/device-510k-0001-of-0001.json.zip"
ZIP_PATH = "/tmp/fda-510k.zip"
JSON_PATH = "/tmp/fda-510k.json"

COMMITTEE_CATEGORY = {
    "CV": "Cardiovascular", "NE": "Neurology", "OP": "Ophthalmology",
    "GU": "Gastroenterology", "OB": "Obstetrics/Gynecology", "AN": "Anesthesiology",
    "RA": "Radiology/Imaging", "DE": "Dental", "OR": "Orthopedic",
    "PM": "Physical Medicine", "HE": "Hematology", "CH": "Diagnostics",
    "IM": "Immunology", "SU": "General Surgery", "ENT": "ENT",
    "PU": "Pulmonology", "UR": "Urology", "EN": "Endocrinology",
    "TX": "Diagnostics", "MI": "Diagnostics", "MG": "Diagnostics",
}

def map_category(code: str, desc: str) -> str:
    if code in COMMITTEE_CATEGORY:
        return COMMITTEE_CATEGORY[code]
    d = (desc or "").lower()
    if "cardio" in d: return "Cardiovascular"
    if "neuro" in d: return "Neurology"
    if "ophthal" in d: return "Ophthalmology"
    if "gastro" in d or "urol" in d: return "Gastroenterology"
    if "ortho" in d: return "Orthopedic"
    if "dent" in d: return "Dental"
    if "radio" in d: return "Radiology/Imaging"
    if "obstet" in d or "gynec" in d: return "Obstetrics/Gynecology"
    if "anesthes" in d: return "Anesthesiology"
    if "hematol" in d: return "Hematology"
    if "immuno" in d: return "Immunology"
    if "ear" in d or "nose" in d: return "ENT"
    if "pulmon" in d: return "Pulmonology"
    if "dermatol" in d or "skin" in d: return "Dermatology"
    if "endocrin" in d: return "Endocrinology"
    if "chem" in d or "micro" in d or "toxico" in d: return "Diagnostics"
    if "physic" in d or "rehab" in d: return "Physical Medicine"
    return "General Surgery"

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
        print(f"  Insert err {e.code}: {e.read()[:200]}", flush=True)
        return 0

def download_zip():
    if os.path.exists(ZIP_PATH):
        size = os.path.getsize(ZIP_PATH)
        print(f"  Zip already on disk ({size//1024//1024} MB), skipping download.", flush=True)
        return
    print(f"  Downloading 510(k) zip (~237 MB)...", flush=True)
    req = urllib.request.Request(ZIP_URL)
    req.add_header("User-Agent", "DeviceAtlas/3.0")
    with urllib.request.urlopen(req, timeout=600) as r:
        with open(ZIP_PATH, "wb") as f:
            downloaded = 0
            while True:
                chunk = r.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded % (20 * 1024 * 1024) == 0:
                    print(f"  ... {downloaded//1024//1024} MB downloaded", flush=True)
    print(f"  Download complete: {os.path.getsize(ZIP_PATH)//1024//1024} MB", flush=True)

def extract_zip():
    if os.path.exists(JSON_PATH):
        size = os.path.getsize(JSON_PATH)
        print(f"  JSON already extracted ({size//1024//1024} MB), skipping.", flush=True)
        return
    print(f"  Extracting zip...", flush=True)
    with zipfile.ZipFile(ZIP_PATH) as zf:
        for name in zf.namelist():
            if name.endswith(".json"):
                zf.extract(name, "/tmp")
                extracted = f"/tmp/{name}"
                if extracted != JSON_PATH:
                    os.rename(extracted, JSON_PATH)
                break
    print(f"  Extracted: {os.path.getsize(JSON_PATH)//1024//1024} MB", flush=True)

def stream_parse_array(filepath: str):
    """
    Stream-parse a JSON file containing {"results": [...]} without loading all into RAM.
    Yields individual objects one at a time using raw_decode.
    """
    decoder = json.JSONDecoder()
    BUFFER = 8 * 1024 * 1024  # 8MB read buffer

    with open(filepath, "r", encoding="utf-8") as f:
        # Skip to start of "results" array
        raw = ""
        in_results = False
        while True:
            chunk = f.read(BUFFER)
            if not chunk:
                break
            raw += chunk
            if not in_results:
                idx = raw.find('"results"')
                if idx == -1:
                    raw = raw[-100:]  # keep tail in case split mid-key
                    continue
                arr_start = raw.find("[", idx)
                if arr_start == -1:
                    continue
                raw = raw[arr_start + 1:]  # skip past opening [
                in_results = True

            # Parse objects from buffer
            while True:
                raw = raw.lstrip()
                if not raw:
                    break
                if raw[0] in ("]", "}"):
                    return  # end of array
                if raw[0] == ",":
                    raw = raw[1:]
                    continue
                try:
                    obj, end = decoder.raw_decode(raw)
                    yield obj
                    raw = raw[end:]
                except json.JSONDecodeError:
                    # Need more data
                    more = f.read(BUFFER)
                    if not more:
                        return
                    raw += more

def main():
    print("=" * 60, flush=True)
    print("FDA 510(k) Bulk Stream Loader", flush=True)
    print("=" * 60, flush=True)

    # Load existing names into a set for fast dedup
    print("\nLoading existing device names...", flush=True)
    rows = mgmt_query("SELECT LOWER(name) as n FROM deviceatlas_devices")
    existing = {r["n"] for r in rows}
    print(f"Existing: {len(existing):,} devices", flush=True)

    # Download + extract
    print("\n[1] Download", flush=True)
    download_zip()

    print("\n[2] Extract", flush=True)
    extract_zip()

    # Stream-process
    print("\n[3] Stream processing 510(k) records...", flush=True)
    batch = []
    total_inserted = 0
    total_seen = 0
    total_skipped = 0
    INSERT_BATCH = 500

    for record in stream_parse_array(JSON_PATH):
        total_seen += 1

        # Only include cleared decisions
        if record.get("decision_code") not in ("SESE", "SESP", "SESK", "SESN", "SE"):
            total_skipped += 1
            continue

        name = (record.get("device_name") or "").strip()
        if not name or len(name) < 3:
            total_skipped += 1
            continue

        name_lower = name.lower()[:200]
        if name_lower in existing:
            total_skipped += 1
            continue
        existing.add(name_lower)

        category = map_category(
            record.get("advisory_committee", ""),
            record.get("advisory_committee_description", "")
        )

        batch.append({
            "id": str(uuid.uuid4()),
            "name": name[:200],
            "manufacturer": (record.get("applicant") or "Unknown")[:200],
            "category": category,
            "description": "",
            "is_active": True,
        })

        if len(batch) >= INSERT_BATCH:
            n = bulk_insert(batch)
            total_inserted += n
            batch = []
            if total_inserted % 10000 == 0:
                print(f"  Seen {total_seen:,} | Inserted {total_inserted:,} | Skipped {total_skipped:,}", flush=True)

    # Flush remainder
    if batch:
        n = bulk_insert(batch)
        total_inserted += n

    print(f"\nStream complete:", flush=True)
    print(f"  Total seen:     {total_seen:,}", flush=True)
    print(f"  Inserted:       {total_inserted:,}", flush=True)
    print(f"  Skipped:        {total_skipped:,}", flush=True)

    final = mgmt_query("SELECT COUNT(*) as c FROM deviceatlas_devices")
    print(f"  DB total now:   {final[0]['c'] if final else '?':,}", flush=True)

if __name__ == "__main__":
    main()
