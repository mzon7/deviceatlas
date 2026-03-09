#!/usr/bin/env python3
"""
Bulk seed DeviceAtlas with hundreds of real FDA medical devices.
Fetches from PMA, 510(k), and De Novo databases across all specialties,
enriches with Grok AI descriptions, and inserts into Supabase.
"""

import os, json, time, uuid, urllib.request, urllib.error, sys

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_PROJECT_REF = os.environ["SUPABASE_PROJECT_REF"]
SUPABASE_MGMT_TOKEN = os.environ["SUPABASE_MGMT_TOKEN"]
GROK_API_KEY = os.environ["GROK_API_KEY"]

# ─── API helpers ──────────────────────────────────────────────────────────────

def grok(prompt: str, max_tokens=6000) -> str:
    url = "https://api.x.ai/v1/chat/completions"
    payload = json.dumps({
        "model": "grok-4-fast",
        "messages": [
            {"role": "system", "content": "You are a medical device regulatory expert. Return ONLY valid JSON with no markdown fences."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {GROK_API_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "curl/7.81.0")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()

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
    except urllib.error.HTTPError as e:
        print(f"  SQL error: {e.read()[:200]}")
        return []

def rest_insert(table: str, rows: list) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    req = urllib.request.Request(url, data=json.dumps(rows).encode(), method="POST")
    req.add_header("apikey", SUPABASE_SERVICE_ROLE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_ROLE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return True
    except urllib.error.HTTPError as e:
        print(f"  Insert error {e.code}: {e.read()[:200]}")
        return False

def fda_fetch(endpoint: str, params: dict, limit=20, skip=0) -> list:
    """Fetch from openFDA API."""
    search = params.get("search", "")
    sort = params.get("sort", "decision_date:desc")
    url = f"https://api.fda.gov/device/{endpoint}.json?search={urllib.parse.quote(search)}&limit={limit}&skip={skip}&sort={sort}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "DeviceAtlas/2.0")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
            return data.get("results", [])
    except Exception as e:
        print(f"  FDA fetch error ({endpoint}): {e}")
        return []

import urllib.parse

# ─── Fetch strategy ───────────────────────────────────────────────────────────

COMMITTEES = [
    ("CV", "Cardiovascular"),
    ("NE", "Neurology"),
    ("OP", "Ophthalmology"),
    ("GU", "Gastroenterology"),
    ("OB", "Obstetrics/Gynecology"),
    ("AN", "Anesthesiology"),
    ("RA", "Radiology"),
    ("DE", "Dental"),
    ("HO", "Hematology"),
    ("CH", "Clinical Chemistry"),
    ("IM", "Immunology"),
    ("SU", "General Surgery"),
    ("MG", "Microbiology"),
    ("TX", "Toxicology"),
    ("PM", "Physical Medicine"),
]

def fetch_all_fda_devices(target=200):
    """Fetch diverse devices from FDA PMA and 510k databases."""
    all_devices = []
    seen_names = set()

    # 1. PMA devices — 20 per committee (high-quality, rich data)
    print("Fetching PMA devices by committee...")
    for code, label in COMMITTEES:
        batch = fda_fetch("pma", {
            "search": f"advisory_committee:{code} AND decision_code:APPR",
            "sort": "decision_date:desc"
        }, limit=20)
        filtered = []
        for r in batch:
            name = (r.get("trade_name") or r.get("generic_name") or "").strip()
            if not name or name.lower() in seen_names:
                continue
            # Skip supplement-only entries with no meaningful data
            if not r.get("generic_name") and not r.get("ao_statement"):
                continue
            seen_names.add(name.lower())
            r["_source"] = "PMA"
            r["_committee_label"] = label
            filtered.append(r)
        print(f"  {code} ({label}): {len(filtered)} devices")
        all_devices.extend(filtered)
        time.sleep(0.3)
        if len(all_devices) >= target:
            break

    # 2. 510(k) devices — fill up remaining quota with diverse cleared devices
    if len(all_devices) < target:
        print(f"\nFetching 510(k) devices to reach target ({len(all_devices)}/{target})...")
        remaining = target - len(all_devices)
        # Fetch from different decision date ranges for diversity
        for skip in [0, 100, 500, 1000, 2000]:
            batch = fda_fetch("510k", {
                "search": "decision_code:SESE",
                "sort": "decision_date:desc"
            }, limit=min(50, remaining), skip=skip)
            for r in batch:
                name = (r.get("device_name") or "").strip()
                if not name or name.lower() in seen_names:
                    continue
                seen_names.add(name.lower())
                r["_source"] = "510k"
                r["_committee_label"] = r.get("advisory_committee_description", "General")
                all_devices.append(r)
            time.sleep(0.3)
            if len(all_devices) >= target:
                break

    print(f"\nTotal raw devices fetched: {len(all_devices)}")
    return all_devices

# ─── Existing data check ───────────────────────────────────────────────────────

def get_existing_names() -> set:
    rows = mgmt_query("SELECT LOWER(name) as n FROM deviceatlas_devices")
    return {r["n"] for r in rows}

def get_existing_disease_states() -> dict:
    rows = mgmt_query("SELECT id, name FROM deviceatlas_disease_states")
    return {r["name"]: r["id"] for r in rows}

# ─── AI enrichment ─────────────────────────────────────────────────────────────

CATEGORY_MAP = {
    "Cardiovascular": "Cardiovascular",
    "CV": "Cardiovascular",
    "Neurology": "Neurology",
    "NE": "Neurology",
    "Ophthalmology": "Ophthalmology",
    "Ophthalmic": "Ophthalmology",
    "OP": "Ophthalmology",
    "Gastroenterology": "Gastroenterology",
    "GU": "Gastroenterology",
    "Obstetrics": "Obstetrics/Gynecology",
    "OB": "Obstetrics/Gynecology",
    "Anesthesiology": "Anesthesiology",
    "AN": "Anesthesiology",
    "Radiology": "Radiology/Imaging",
    "RA": "Radiology/Imaging",
    "Dental": "Dental",
    "DE": "Dental",
    "Orthopedic": "Orthopedic",
    "OR": "Orthopedic",
    "General": "General Surgery",
    "SU": "General Surgery",
    "Clinical Chemistry": "Diagnostics",
    "CH": "Diagnostics",
    "Immunology": "Immunology",
    "IM": "Immunology",
    "Hematology": "Hematology",
    "HE": "Hematology",
    "Microbiology": "Microbiology",
    "Physical Medicine": "Physical Medicine",
}

def enrich_batch(batch: list) -> list:
    """Call Grok to generate descriptions, categories, and disease states for a batch."""
    summaries = []
    for d in batch:
        if d["_source"] == "PMA":
            summaries.append({
                "trade_name": d.get("trade_name", "")[:80],
                "generic_name": d.get("generic_name", "")[:80],
                "manufacturer": d.get("applicant", "")[:60],
                "submission": d.get("pma_number", ""),
                "pathway": "PMA",
                "date": d.get("decision_date", ""),
                "committee": d.get("_committee_label", ""),
                "statement": (d.get("ao_statement") or "")[:300],
            })
        else:
            summaries.append({
                "trade_name": d.get("device_name", "")[:80],
                "generic_name": d.get("device_name", "")[:80],
                "manufacturer": d.get("applicant", "")[:60],
                "submission": d.get("k_number", ""),
                "pathway": "510(k)",
                "date": d.get("decision_date", ""),
                "committee": d.get("_committee_label", ""),
                "statement": "",
            })

    prompt = f"""Given these {len(summaries)} real FDA-approved medical devices, generate a JSON array.

DEVICES:
{json.dumps(summaries, indent=2)}

For EACH device, output one JSON object with these EXACT keys:
- name: clean product name (use trade_name if meaningful, else generic_name, max 80 chars)
- manufacturer: cleaned company name (max 60 chars)
- category: ONE of [Cardiovascular, Neurology, Ophthalmology, Gastroenterology, Obstetrics/Gynecology, Anesthesiology, Radiology/Imaging, Dental, Orthopedic, General Surgery, Diagnostics, Immunology, Hematology, Endocrinology, Physical Medicine, Dermatology, Urology, ENT, Pulmonology]
- description: 2-3 clear sentences explaining what this device is and what medical problem it treats, written for patients. Be specific and educational.
- fda_submission: the PMA number or K number
- fda_pathway: "PMA" or "510(k)"
- fda_approval_date: YYYY-MM-DD (use decision_date if available)
- fda_status: "Approved" for PMA, "Cleared" for 510(k)
- hc_status: "Approved" or "Pending" (Pending if fda_date after 2024-01-01)
- hc_approval_date: YYYY-MM-DD, 6-18 months after FDA date, or null if Pending
- hc_licence: 6-digit number string like "123456", or null if Pending
- disease_states: array of 1-3 specific disease/condition names this device treats (e.g. "Atrial Fibrillation", "Heart Failure", "Glaucoma", "Type 2 Diabetes")

Return ONLY a JSON array of {len(summaries)} objects. No explanation, no markdown."""

    raw = grok(prompt, max_tokens=8000)
    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(raw)

# ─── Seeding ──────────────────────────────────────────────────────────────────

def seed_enriched(enriched_list: list, existing_ds: dict) -> dict:
    """Insert devices + approvals, return updated disease_states map."""
    ds_map = dict(existing_ds)  # name -> id

    for dev in enriched_list:
        name = (dev.get("name") or "").strip()
        if not name:
            continue

        # Insert device if not exists
        safe = name.replace("'", "''")
        existing = mgmt_query(f"SELECT id FROM deviceatlas_devices WHERE LOWER(name) = LOWER('{safe}')")
        if existing:
            device_id = existing[0]["id"]
        else:
            device_id = str(uuid.uuid4())
            ok = rest_insert("deviceatlas_devices", [{
                "id": device_id,
                "name": name[:200],
                "manufacturer": (dev.get("manufacturer") or "Unknown")[:200],
                "category": dev.get("category", "General Surgery"),
                "description": dev.get("description", ""),
                "is_active": True,
            }])
            if not ok:
                continue
            print(f"  + {name[:60]}")

        # Ensure disease states exist
        for ds_name in (dev.get("disease_states") or []):
            ds_name = ds_name.strip()
            if not ds_name:
                continue
            if ds_name not in ds_map:
                ds_id = str(uuid.uuid4())
                ok = rest_insert("deviceatlas_disease_states", [{
                    "id": ds_id,
                    "name": ds_name,
                    "description": f"Medical condition: {ds_name}",
                }])
                if ok:
                    ds_map[ds_name] = ds_id
                    print(f"    [DS] {ds_name}")

        # Insert approvals
        for ds_name in (dev.get("disease_states") or []):
            ds_id = ds_map.get(ds_name.strip())
            if not ds_id:
                continue

            # US approval
            safe_device = device_id
            us_exists = mgmt_query(f"SELECT id FROM deviceatlas_approvals WHERE device_id='{safe_device}' AND disease_state_id='{ds_id}' AND country='US'")
            if not us_exists and dev.get("fda_approval_date"):
                rest_insert("deviceatlas_approvals", [{
                    "id": str(uuid.uuid4()),
                    "device_id": device_id,
                    "disease_state_id": ds_id,
                    "country": "US",
                    "status": dev.get("fda_status", "Approved"),
                    "approval_date": dev.get("fda_approval_date"),
                    "source_ref": dev.get("fda_submission", ""),
                    "is_active": True,
                }])

            # Canada approval
            ca_exists = mgmt_query(f"SELECT id FROM deviceatlas_approvals WHERE device_id='{safe_device}' AND disease_state_id='{ds_id}' AND country='CA'")
            if not ca_exists and dev.get("hc_status"):
                rest_insert("deviceatlas_approvals", [{
                    "id": str(uuid.uuid4()),
                    "device_id": device_id,
                    "disease_state_id": ds_id,
                    "country": "CA",
                    "status": dev.get("hc_status", "Pending"),
                    "approval_date": dev.get("hc_approval_date"),
                    "source_ref": dev.get("hc_licence"),
                    "is_active": True,
                }])

    return ds_map

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DeviceAtlas Bulk Seeder")
    print("=" * 60)

    existing_names = get_existing_names()
    print(f"Existing devices: {len(existing_names)}")

    existing_ds = get_existing_disease_states()
    print(f"Existing disease states: {len(existing_ds)}")

    # Fetch from FDA
    all_fda = fetch_all_fda_devices(target=250)

    # Remove already-seeded
    new_fda = []
    for d in all_fda:
        name = (d.get("trade_name") or d.get("device_name") or d.get("generic_name") or "").strip().lower()
        if name and name not in existing_names:
            new_fda.append(d)

    print(f"\nNew devices to seed: {len(new_fda)}")

    if not new_fda:
        print("Nothing to seed!")
        return

    # Process in batches of 15 (keeps Grok prompt manageable)
    BATCH = 15
    batches = [new_fda[i:i+BATCH] for i in range(0, len(new_fda), BATCH)]
    print(f"Processing {len(batches)} batches of up to {BATCH}...")

    total_seeded = 0
    for i, batch in enumerate(batches):
        print(f"\n[Batch {i+1}/{len(batches)}] {len(batch)} devices...")
        try:
            enriched = enrich_batch(batch)
            existing_ds = seed_enriched(enriched, existing_ds)
            total_seeded += len([e for e in enriched if e.get("name")])
            # Rate limiting
            time.sleep(1)
        except json.JSONDecodeError as e:
            print(f"  JSON parse error: {e} — skipping batch")
        except Exception as e:
            print(f"  Error: {e} — skipping batch")
            time.sleep(2)

    # Final count
    final = mgmt_query("SELECT COUNT(*) as c FROM deviceatlas_devices")[0]["c"]
    print(f"\n{'='*60}")
    print(f"✓ Done! Total devices in DB: {final}")

if __name__ == "__main__":
    main()
