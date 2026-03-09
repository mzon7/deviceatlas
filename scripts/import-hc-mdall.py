#!/usr/bin/env python3
"""
Import real Health Canada MDALL data into DeviceAtlas.

Strategy:
1. Download all active HC licences + companies from official API
2. Fuzzy-match HC licences to our FDA devices by name + manufacturer
3. Delete all fake CA approvals
4. Insert real CA approvals for matched devices (inheriting disease states from FDA side)
5. Store HC licence number in source_ref field

HC API docs: https://health-products.canada.ca/api/documentation/mdall-documentation-en.html
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from difflib import SequenceMatcher

SUPABASE_PROJECT_REF = os.environ["SUPABASE_PROJECT_REF"]
SUPABASE_MGMT_TOKEN = os.environ["SUPABASE_MGMT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HC_LICENCE_URL = "https://health-products.canada.ca/api/medical-devices/licence/?state=active&type=json&lang=en"
HC_LICENCE_ARCHIVED_URL = "https://health-products.canada.ca/api/medical-devices/licence/?state=archived&type=json&lang=en"
HC_COMPANY_URL = "https://health-products.canada.ca/api/medical-devices/company/?type=json"

MATCH_THRESHOLD = 0.72  # Minimum similarity score to count as a match


def normalize(s: str) -> str:
    """Normalize a device name for comparison."""
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)  # replace punctuation with space
    s = re.sub(r"\s+", " ", s).strip()
    # Remove common noise words
    noise = {"the", "a", "an", "and", "or", "for", "of", "with", "by", "to", "in", "on"}
    tokens = [t for t in s.split() if t not in noise]
    return " ".join(tokens)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def mgmt_query(sql: str):
    """Run SQL via Supabase Management API."""
    payload = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{SUPABASE_PROJECT_REF}/database/query",
        data=payload,
        headers={
            "Authorization": f"Bearer {SUPABASE_MGMT_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "curl/7.81.0",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def rest_get(path: str, params: dict = None):
    """Call Supabase REST API with service role key."""
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "curl/7.81.0",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def rest_post(path: str, data: list):
    """Insert rows via Supabase REST API."""
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=payload,
        method="POST",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status


def fetch_json(url: str) -> list:
    print(f"Fetching {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.81.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    print(f"  → {len(data)} records")
    return data


def load_hc_data():
    """Download and cache HC data."""
    cache_licences = "/tmp/hc_licences.json"
    cache_archived = "/tmp/hc_licences_archived.json"
    cache_companies = "/tmp/hc_companies.json"

    if os.path.exists(cache_licences):
        print("Loading HC licences from cache...")
        with open(cache_licences) as f:
            licences = json.load(f)
    else:
        licences = fetch_json(HC_LICENCE_URL)
        with open(cache_licences, "w") as f:
            json.dump(licences, f)

    if os.path.exists(cache_archived):
        print("Loading HC archived licences from cache...")
        with open(cache_archived) as f:
            archived = json.load(f)
    else:
        archived = fetch_json(HC_LICENCE_ARCHIVED_URL)
        with open(cache_archived, "w") as f:
            json.dump(archived, f)

    if os.path.exists(cache_companies):
        print("Loading HC companies from cache...")
        with open(cache_companies) as f:
            companies = json.load(f)
    else:
        companies = fetch_json(HC_COMPANY_URL)
        with open(cache_companies, "w") as f:
            json.dump(companies, f)

    return licences, archived, companies


def build_hc_index(licences: list, archived: list, companies: list):
    """Build normalized lookup structures."""
    company_map = {c["company_id"]: c["company_name"] for c in companies}

    all_licences = licences + archived

    hc = []
    for lic in all_licences:
        name = lic.get("licence_name", "") or ""
        company_id = lic.get("company_id")
        company = company_map.get(company_id, "") or ""
        status = lic.get("licence_status", "")  # I=Active, C=Cancelled/Archived
        date = lic.get("first_licence_status_dt") or lic.get("end_date")
        end_date = lic.get("end_date")
        risk_class = lic.get("appl_risk_class")
        licence_no = lic.get("original_licence_no")

        if not name or not licence_no:
            continue

        hc.append({
            "licence_no": licence_no,
            "name": name,
            "company": company,
            "status": status,
            "date": date,
            "end_date": end_date,
            "risk_class": risk_class,
            "norm_name": normalize(name),
            "norm_company": normalize(company),
        })

    print(f"HC index built: {len(hc)} total licences (active + archived)")
    return hc


def load_fda_devices():
    """Load all FDA devices from our DB in batches."""
    print("Loading FDA devices from DB...")
    all_devices = []
    limit = 1000
    offset = 0
    while True:
        rows = rest_get(
            "deviceatlas_devices",
            {"select": "id,name,manufacturer", "limit": limit, "offset": offset}
        )
        if not rows:
            break
        all_devices.extend(rows)
        offset += limit
        if len(rows) < limit:
            break
        if offset % 10000 == 0:
            print(f"  Loaded {offset} devices...")
    print(f"  Total FDA devices: {len(all_devices)}")
    return all_devices


def match_devices(fda_devices: list, hc_index: list):
    """
    Match FDA devices to HC licences.

    Strategy (fast):
    1. Exact normalized name match (hash lookup) — catches most real matches
    2. Two-token prefix match with SequenceMatcher, capped at 30 candidates — catches minor variations
    """
    # Build exact name → hc mapping (prefer active over archived)
    hc_by_exact_name = {}
    for h in hc_index:
        key = h["norm_name"]
        if key not in hc_by_exact_name or h["status"] == "I":
            hc_by_exact_name[key] = h

    # Build two-token prefix index (only index HC by bigram of first two name tokens)
    hc_by_bigram = {}
    for h in hc_index:
        tokens = h["norm_name"].split()
        if len(tokens) >= 2:
            bigram = (tokens[0], tokens[1])
            hc_by_bigram.setdefault(bigram, []).append(h)
        elif tokens:
            hc_by_bigram.setdefault((tokens[0],), []).append(h)

    matches = []
    no_match = 0
    exact_hits = 0
    fuzzy_hits = 0

    print(f"Matching {len(fda_devices)} FDA devices against {len(hc_index)} HC licences...")

    for i, dev in enumerate(fda_devices):
        if i % 20000 == 0 and i > 0:
            print(f"  {i}/{len(fda_devices)} — {exact_hits} exact, {fuzzy_hits} fuzzy, {no_match} unmatched")

        name = dev.get("name", "") or ""
        norm_name = normalize(name)

        if not norm_name:
            no_match += 1
            continue

        # Pass 1: exact normalized name match (O(1))
        if norm_name in hc_by_exact_name:
            exact_hits += 1
            matches.append({"device_id": dev["id"], "hc": hc_by_exact_name[norm_name], "score": 1.0})
            continue

        # Pass 2: two-token bigram match with similarity scoring, cap at 30 candidates
        tokens = norm_name.split()
        if len(tokens) >= 2:
            bigram = (tokens[0], tokens[1])
        elif tokens:
            bigram = (tokens[0],)
        else:
            no_match += 1
            continue

        candidates = hc_by_bigram.get(bigram, [])
        if not candidates:
            no_match += 1
            continue

        # Cap candidates to avoid slow matches on common bigrams
        if len(candidates) > 30:
            candidates = candidates[:30]

        best_score = 0.0
        best_hc = None
        for h in candidates:
            score = similarity(norm_name, h["norm_name"])
            if score > best_score:
                best_score = score
                best_hc = h

        if best_score >= MATCH_THRESHOLD and best_hc:
            fuzzy_hits += 1
            matches.append({"device_id": dev["id"], "hc": best_hc, "score": best_score})
        else:
            no_match += 1

    print(f"Matching complete: {len(matches)} total ({exact_hits} exact + {fuzzy_hits} fuzzy), {no_match} unmatched")
    return matches


def load_disease_states_for_devices(device_ids: list):
    """Get US disease states for each device (to inherit for CA approvals)."""
    print("Loading disease state mappings from existing US approvals...")
    device_ds_map = {}  # device_id -> list of disease_state_ids
    # Use REST API with PostgREST IN filter, batch by 100
    batch_size = 100
    for i in range(0, len(device_ids), batch_size):
        batch = device_ids[i:i+batch_size]
        ids_csv = ",".join(batch)
        rows = rest_get(
            "deviceatlas_approvals",
            {
                "select": "device_id,disease_state_id",
                "country": "eq.US",
                "is_active": "eq.true",
                f"device_id": f"in.({ids_csv})",
                "limit": "10000",
            }
        )
        for row in rows:
            did = row["device_id"]
            dsid = row["disease_state_id"]
            device_ds_map.setdefault(did, [])
            if dsid not in device_ds_map[did]:
                device_ds_map[did].append(dsid)
        if i % 2000 == 0 and i > 0:
            print(f"  Processed {i}/{len(device_ids)} devices...")

    print(f"  Got disease state mappings for {len(device_ds_map)} devices")
    return device_ds_map


def delete_fake_ca_approvals():
    """Delete all existing CA approvals (they're all fake) via REST API."""
    print("Deleting fake CA approvals...")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/deviceatlas_approvals?country=eq.CA",
        method="DELETE",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Prefer": "return=minimal",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        print(f"  DELETE status: {resp.status}")
    rows = rest_get("deviceatlas_approvals", {"select": "id", "country": "eq.CA", "limit": "1"})
    print(f"  CA approvals remaining: {'0' if not rows else '>0'}")


def insert_ca_approvals(matches: list, device_ds_map: dict):
    """Insert real CA approvals for matched devices."""
    print(f"Inserting CA approvals for {len(matches)} matched devices...")

    rows_to_insert = []
    skipped_no_ds = 0

    for m in matches:
        device_id = m["device_id"]
        hc = m["hc"]

        disease_state_ids = device_ds_map.get(device_id, [])

        if not disease_state_ids:
            # Insert one approval with null disease state for devices with no US approvals
            # (less common but possible)
            skipped_no_ds += 1
            continue

        # Map HC status
        hc_status = "Approved" if hc["status"] == "I" else "Retired"
        if hc["end_date"] and hc["status"] != "I":
            hc_status = "Retired"

        for ds_id in disease_state_ids:
            rows_to_insert.append({
                "device_id": device_id,
                "disease_state_id": ds_id,
                "country": "CA",
                "status": hc_status,
                "approval_date": hc["date"],
                "retired_date": hc["end_date"] if hc_status == "Retired" else None,
                "source_ref": str(hc["licence_no"]),
                "is_active": hc["status"] == "I",
                "pma_number": None,
                "submission_number": None,
            })

    print(f"  Total CA approval rows to insert: {len(rows_to_insert)}")
    print(f"  Skipped (no disease states): {skipped_no_ds}")

    # Insert in batches of 500
    batch_size = 500
    inserted = 0
    for i in range(0, len(rows_to_insert), batch_size):
        batch = rows_to_insert[i:i+batch_size]
        try:
            rest_post("deviceatlas_approvals", batch)
            inserted += len(batch)
            if inserted % 5000 == 0:
                print(f"  Inserted {inserted}/{len(rows_to_insert)}...")
        except Exception as e:
            print(f"  ERROR inserting batch {i//batch_size}: {e}")
            time.sleep(2)

    print(f"  Done. Inserted {inserted} CA approval rows.")
    return inserted


def main():
    print("=" * 60)
    print("DeviceAtlas — Health Canada MDALL Real Data Import")
    print("=" * 60)

    # Step 1: Download HC data
    licences, archived, companies = load_hc_data()

    # Step 2: Build index
    hc_index = build_hc_index(licences, archived, companies)

    # Step 3 & 4: Match (use cache if available, else load devices and match)
    match_cache = "/tmp/hc_matches.json"
    if os.path.exists(match_cache):
        print("Loading matches from cache (skipping device load + matching)...")
        with open(match_cache) as f:
            matches = json.load(f)
        fda_count = 173768  # known total
        print(f"  {len(matches)} matches loaded")
    else:
        fda_devices = load_fda_devices()
        fda_count = len(fda_devices)
        matches = match_devices(fda_devices, hc_index)
        with open(match_cache, "w") as f:
            json.dump(matches, f)
        print(f"Matches cached to {match_cache}")

    # Show sample matches
    print("\nSample matches:")
    for m in matches[:10]:
        print(f"  [{m['score']:.2f}] {m['hc']['name']} (HC#{m['hc']['licence_no']})")

    # Step 5: Load disease states for matched devices
    matched_device_ids = [m["device_id"] for m in matches]
    device_ds_map = load_disease_states_for_devices(matched_device_ids)

    # Step 6: Delete fake CA approvals
    delete_fake_ca_approvals()

    # Step 7: Insert real CA approvals
    inserted = insert_ca_approvals(matches, device_ds_map)

    # Final summary
    final_rows = rest_get("deviceatlas_approvals", {"select": "id", "country": "eq.CA", "limit": "1", "offset": "0"})
    final_count = [{"cnt": "check DB directly"}]  # REST HEAD count not needed for summary
    print("\n" + "=" * 60)
    print(f"DONE. Real HC CA approvals in DB: {final_count[0]['cnt'] if final_count else inserted}")
    print(f"Devices matched to HC licences: {len(matches)}/{fda_count} ({100*len(matches)//fda_count}%)")
    print("=" * 60)


if __name__ == "__main__":
    main()
