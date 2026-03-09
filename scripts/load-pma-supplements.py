#!/usr/bin/env python3
"""
Load PMA supplement data from OpenFDA API.
For each PMA base device in our DB:
  1. Update cleared_date to the most recent supplement's decision_date
  2. Add supplement trade_names as new devices if they are distinct new products
"""

import json, os, time, uuid
import urllib.request, urllib.error

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_PROJECT_REF = os.environ["SUPABASE_PROJECT_REF"]
SUPABASE_MGMT_TOKEN = os.environ["SUPABASE_MGMT_TOKEN"]

MGMT_BASE = f"https://api.supabase.com/v1/projects/{SUPABASE_PROJECT_REF}/database/query"
FDA_API = "https://api.fda.gov/device/pma.json"


def mgmt_query(sql: str):
    body = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        MGMT_BASE, data=body,
        headers={"Authorization": f"Bearer {SUPABASE_MGMT_TOKEN}",
                 "Content-Type": "application/json", "User-Agent": "curl/7.81.0"},
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt == 2: raise
            time.sleep(2 ** attempt)


def fda_api(params: dict) -> list:
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url = f"{FDA_API}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.81.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return data.get("results", [])
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise


import urllib.parse


def clean_name(name: str) -> str:
    """Clean Windows-1252 artifacts from name."""
    replacements = {
        '\x99': '™', '\x93': '"', '\x94': '"', '\x95': '·',
        '\x96': '–', '\x97': '—', '\x91': '\u2018', '\x92': '\u2019',
    }
    for bad, good in replacements.items():
        name = name.replace(bad, good)
    return name.strip()


def names_are_similar(a: str, b: str) -> bool:
    """Check if two device names are essentially the same product."""
    a_words = set(a.lower().split())
    b_words = set(b.lower().split())
    if not a_words or not b_words:
        return False
    overlap = len(a_words & b_words) / min(len(a_words), len(b_words))
    return overlap > 0.6


def main():
    print("=" * 60)
    print("PMA Supplement Loader")
    print("=" * 60)

    # Load all PMA devices from DB — only real P-prefixed PMAs
    print("\nLoading PMA devices from DB...")
    rows = mgmt_query("""
        SELECT id, name, manufacturer, category, cleared_date, submission_number
        FROM deviceatlas_devices
        WHERE clearance_type = 'PMA'
          AND submission_number IS NOT NULL
          AND submission_number LIKE 'P%'
        ORDER BY submission_number
    """)
    print(f"Found {len(rows)} PMA base devices")

    # Load existing device names for dedup
    print("Loading existing device names for dedup...")
    existing_rows = mgmt_query("SELECT LOWER(name) as n FROM deviceatlas_devices")
    existing_names = {r["n"] for r in existing_rows}
    print(f"Existing names: {len(existing_names):,}")

    updates = []   # (id, new_cleared_date)
    new_devices = []

    total = len(rows)
    for i, device in enumerate(rows):
        pma_num = device["submission_number"]
        device_id = device["id"]
        current_name = device["name"]
        category = device["category"]
        manufacturer = device["manufacturer"]

        # Query OpenFDA for all supplements to this PMA, sorted newest first
        try:
            results = fda_api({
                "search": f"pma_number:{pma_num}",
                "limit": "100",
                "sort": "decision_date:desc",
            })
            # Keep only supplement records (have non-empty supplement_number)
            results = [r for r in results if r.get("supplement_number", "").strip()]
        except Exception as e:
            print(f"  [{i+1}/{total}] {pma_num}: API error {e}")
            time.sleep(1)
            continue

        if not results:
            time.sleep(0.3)
            continue

        # Most recent supplement = update cleared_date of base device
        most_recent = results[0]
        most_recent_date = most_recent.get("decision_date") or device.get("cleared_date")

        if most_recent_date and most_recent_date != device.get("cleared_date"):
            updates.append((device_id, most_recent_date))

        # Collect unique trade_names from supplements to add as new devices
        seen_trade_names = set()
        seen_trade_names.add(current_name.lower())

        for rec in results:
            trade_name = clean_name(rec.get("trade_name") or "")
            if not trade_name or len(trade_name) < 4:
                continue
            # Truncate to 200 chars
            trade_name = trade_name[:200]
            trade_lower = trade_name.lower()

            # Skip if too similar to base device name or already seen
            if trade_lower in seen_trade_names:
                continue
            if names_are_similar(current_name, trade_name):
                seen_trade_names.add(trade_lower)
                continue
            # Skip if already in our global name set
            if trade_lower in existing_names:
                seen_trade_names.add(trade_lower)
                continue

            seen_trade_names.add(trade_lower)
            existing_names.add(trade_lower)

            cleared = rec.get("decision_date")
            new_devices.append({
                "id": str(uuid.uuid4()),
                "name": trade_name,
                "manufacturer": manufacturer or "Unknown",
                "category": category or "General Surgery",
                "description": "",
                "is_active": True,
                "cleared_date": cleared,
                "submission_number": f"{pma_num}/{rec.get('supplement_number','')}",
                "clearance_type": "PMA",
            })

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{total}] Processed | {len(updates)} date updates | {len(new_devices)} new devices")

        # Flush updates every 100
        if len(updates) >= 100:
            _flush_updates(updates)
            updates = []
        if len(new_devices) >= 200:
            _flush_devices(new_devices)
            new_devices = []

        time.sleep(0.25)  # ~4 req/sec, respectful

    # Final flush
    if updates:
        _flush_updates(updates)
    if new_devices:
        _flush_devices(new_devices)

    result = mgmt_query("SELECT COUNT(*) as c FROM deviceatlas_devices")
    print(f"\nDone! Total devices in DB: {result[0]['c']:,}")


def _flush_updates(updates: list):
    """Batch-update cleared_date for PMA base devices."""
    if not updates:
        return
    ids_sql = ", ".join(f"'{uid}'" for uid, _ in updates)
    case = " ".join(f"WHEN id = '{uid}' THEN '{date}'" for uid, date in updates)
    sql = f"UPDATE deviceatlas_devices SET cleared_date = CASE {case} ELSE cleared_date END WHERE id IN ({ids_sql}) AND clearance_type = 'PMA';"
    mgmt_query(sql)
    print(f"  Updated cleared_date for {len(updates)} PMA devices")


def _flush_devices(devices: list):
    """Insert new supplement trade-name devices."""
    if not devices:
        return
    rest_url = f"{SUPABASE_URL}/rest/v1/deviceatlas_devices"
    body = json.dumps(devices).encode()
    req = urllib.request.Request(
        rest_url, data=body,
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        print(f"  Inserted {len(devices)} new supplement devices")
    except Exception as e:
        print(f"  Insert error: {e}")


if __name__ == "__main__":
    main()
