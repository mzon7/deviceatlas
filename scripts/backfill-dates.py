#!/usr/bin/env python3
"""
Backfill dates and metadata for devices already in DB from FDA 510k + PMA bulk JSON.
Re-streams /tmp/fda-510k.json (already extracted), matches devices by name,
and UPDATEs cleared_date, submitted_date, product_code, device_class, submission_number, clearance_type.

Also streams PMA data for PMA devices.
"""

import json, os, uuid, time
import urllib.request, urllib.error

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_PROJECT_REF = os.environ["SUPABASE_PROJECT_REF"]
SUPABASE_MGMT_TOKEN = os.environ["SUPABASE_MGMT_TOKEN"]

JSON_510K = "/tmp/fda-510k.json"
JSON_PMA  = "/tmp/fda-pma.json"

PMA_ZIP_URL = "https://download.open.fda.gov/device/pma/device-pma-0001-of-0001.json.zip"
PMA_ZIP_PATH = "/tmp/fda-pma.zip"

BATCH_SIZE = 500
MGMT_BASE = f"https://api.supabase.com/v1/projects/{SUPABASE_PROJECT_REF}/database/query"


def mgmt_query(sql: str):
    body = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        MGMT_BASE,
        data=body,
        headers={
            "Authorization": f"Bearer {SUPABASE_MGMT_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "curl/7.81.0",
        },
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def bulk_update(updates: list):
    """Update devices by id with new metadata fields."""
    if not updates:
        return 0
    # Build a single SQL with multiple CASE WHEN updates
    ids = [u["id"] for u in updates]
    ids_sql = ", ".join(f"'{i}'" for i in ids)

    def case_expr(field, val_map):
        cases = " ".join(
            f"WHEN id = '{uid}' THEN {val_map[uid]}"
            for uid in val_map
            if val_map[uid] is not None
        )
        if not cases:
            return None
        return f"CASE {cases} ELSE {field} END"

    cleared_map = {u["id"]: f"'{u['cleared_date']}'" if u.get("cleared_date") else None for u in updates}
    submitted_map = {u["id"]: f"'{u['submitted_date']}'" if u.get("submitted_date") else None for u in updates}
    product_map = {u["id"]: f"'{u['product_code'].replace(chr(39), chr(39)+chr(39))}'" if u.get("product_code") else None for u in updates}
    class_map = {u["id"]: f"'{u['device_class'].replace(chr(39), chr(39)+chr(39))}'" if u.get("device_class") else None for u in updates}
    subnum_map = {u["id"]: f"'{u['submission_number'].replace(chr(39), chr(39)+chr(39))}'" if u.get("submission_number") else None for u in updates}
    ctype_map = {u["id"]: f"'{u['clearance_type'].replace(chr(39), chr(39)+chr(39))}'" if u.get("clearance_type") else None for u in updates}

    sets = []
    for field, val_map in [
        ("cleared_date", cleared_map),
        ("submitted_date", submitted_map),
        ("product_code", product_map),
        ("device_class", class_map),
        ("submission_number", subnum_map),
        ("clearance_type", ctype_map),
    ]:
        expr = case_expr(field, val_map)
        if expr:
            sets.append(f"{field} = {expr}")

    if not sets:
        return 0

    sql = f"UPDATE deviceatlas_devices SET {', '.join(sets)} WHERE id IN ({ids_sql}) AND cleared_date IS NULL;"
    try:
        mgmt_query(sql)
        return len(updates)
    except Exception as e:
        print(f"  Update error: {e}", flush=True)
        return 0


def stream_parse_array(filepath: str):
    decoder = json.JSONDecoder()
    BUFFER = 8 * 1024 * 1024
    with open(filepath, "r", encoding="utf-8") as f:
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
                    raw = raw[-100:]
                    continue
                arr_start = raw.find("[", idx)
                if arr_start == -1:
                    continue
                raw = raw[arr_start + 1:]
                in_results = True
            while True:
                raw = raw.lstrip()
                if not raw:
                    break
                if raw[0] in ("]", "}"):
                    return
                if raw[0] == ",":
                    raw = raw[1:]
                    continue
                try:
                    obj, end = decoder.raw_decode(raw)
                    yield obj
                    raw = raw[end:]
                except json.JSONDecodeError:
                    more = f.read(BUFFER)
                    if not more:
                        return
                    raw += more


def load_device_name_map():
    """Load all devices from DB: { lower(name): id }"""
    print("Loading device name→id map from DB...", flush=True)
    # Paginate since 150k+ rows
    name_map = {}
    offset = 0
    batch = 10000
    while True:
        rows = mgmt_query(
            f"SELECT id, LOWER(name) as n FROM deviceatlas_devices "
            f"WHERE cleared_date IS NULL ORDER BY id LIMIT {batch} OFFSET {offset};"
        )
        if not rows:
            break
        for r in rows:
            name_map[r["n"]] = r["id"]
        if len(rows) < batch:
            break
        offset += batch
        print(f"  Loaded {len(name_map):,} names...", flush=True)
    print(f"  Total needing backfill: {len(name_map):,}", flush=True)
    return name_map


def run_510k(name_map: dict):
    if not os.path.exists(JSON_510K):
        print(f"510k JSON not found at {JSON_510K}, skipping.", flush=True)
        return

    print(f"\nBackfilling from 510k JSON ({os.path.getsize(JSON_510K)//1024//1024} MB)...", flush=True)
    batch = []
    matched = 0
    seen = 0

    for record in stream_parse_array(JSON_510K):
        seen += 1
        name = (record.get("device_name") or "").strip().lower()[:200]
        if not name or name not in name_map:
            continue

        device_id = name_map[name]
        openfda = record.get("openfda") or {}

        update = {
            "id": device_id,
            "cleared_date": record.get("decision_date"),
            "submitted_date": record.get("date_received"),
            "product_code": record.get("product_code") or (openfda.get("product_code") or [None])[0],
            "device_class": openfda.get("device_class", [None])[0] if isinstance(openfda.get("device_class"), list) else openfda.get("device_class"),
            "submission_number": record.get("k_number"),
            "clearance_type": record.get("clearance_type"),
        }
        batch.append(update)
        # Remove from map so we don't overwrite with a later duplicate
        del name_map[name]
        matched += 1

        if len(batch) >= BATCH_SIZE:
            n = bulk_update(batch)
            batch = []
            if matched % 10000 == 0:
                print(f"  Seen {seen:,} | Matched+updated {matched:,}", flush=True)

    if batch:
        bulk_update(batch)

    print(f"  510k backfill complete: {matched:,} devices updated (seen {seen:,} records)", flush=True)
    return name_map  # remaining unmatched


def download_pma_json():
    import zipfile
    if os.path.exists(JSON_PMA):
        print(f"PMA JSON already exists ({os.path.getsize(JSON_PMA)//1024//1024} MB)", flush=True)
        return
    if not os.path.exists(PMA_ZIP_PATH):
        print(f"Downloading PMA zip...", flush=True)
        req = urllib.request.Request(PMA_ZIP_URL, headers={"User-Agent": "curl/7.81.0"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(PMA_ZIP_PATH, "wb") as f:
            downloaded = 0
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
        print(f"  Downloaded: {downloaded//1024//1024} MB", flush=True)
    print("Extracting PMA zip...", flush=True)
    import zipfile
    with zipfile.ZipFile(PMA_ZIP_PATH) as zf:
        for name in zf.namelist():
            if name.endswith(".json"):
                zf.extract(name, "/tmp")
                extracted = f"/tmp/{name}"
                if extracted != JSON_PMA:
                    os.rename(extracted, JSON_PMA)
                break
    print(f"  PMA JSON: {os.path.getsize(JSON_PMA)//1024//1024} MB", flush=True)


def run_pma(name_map: dict):
    download_pma_json()
    print(f"\nBackfilling from PMA JSON...", flush=True)
    batch = []
    matched = 0
    seen = 0

    for record in stream_parse_array(JSON_PMA):
        seen += 1
        # Skip supplements
        if record.get("supplement_number", "").strip():
            continue
        name = (record.get("device_name") or record.get("trade_name") or "").strip().lower()[:200]
        if not name or name not in name_map:
            continue

        device_id = name_map[name]
        openfda = record.get("openfda") or {}

        update = {
            "id": device_id,
            "cleared_date": record.get("decision_date"),
            "submitted_date": record.get("date_received"),
            "product_code": record.get("product_code") or (openfda.get("product_code") or [None])[0],
            "device_class": openfda.get("device_class", [None])[0] if isinstance(openfda.get("device_class"), list) else openfda.get("device_class"),
            "submission_number": record.get("pma_number"),
            "clearance_type": "PMA",
        }
        batch.append(update)
        del name_map[name]
        matched += 1

        if len(batch) >= BATCH_SIZE:
            bulk_update(batch)
            batch = []

    if batch:
        bulk_update(batch)

    print(f"  PMA backfill complete: {matched:,} devices updated (seen {seen:,} records)", flush=True)


def main():
    print("=" * 60, flush=True)
    print("DeviceAtlas — Backfill Dates & Metadata", flush=True)
    print("=" * 60, flush=True)

    name_map = load_device_name_map()
    if not name_map:
        print("All devices already have dates! Nothing to do.", flush=True)
        return

    remaining = run_510k(name_map)
    if remaining is None:
        remaining = name_map

    print(f"\n{len(remaining):,} devices not matched in 510k data, trying PMA...", flush=True)
    if remaining:
        run_pma(remaining)

    # Final count
    result = mgmt_query("SELECT COUNT(*) as c FROM deviceatlas_devices WHERE cleared_date IS NOT NULL;")
    print(f"\nDevices with dates: {result[0]['c']:,}", flush=True)
    result2 = mgmt_query("SELECT COUNT(*) as c FROM deviceatlas_devices;")
    print(f"Total devices: {result2[0]['c']:,}", flush=True)


if __name__ == "__main__":
    main()
