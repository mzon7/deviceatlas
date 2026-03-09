#!/usr/bin/env python3
"""
Import Health Canada MDALL devices that have no FDA equivalent.
These are Canada-only licensed medical devices.

Adds them to deviceatlas_devices with is_active=true and a CA approval
record (disease_state_id=null since HC doesn't provide indication data).
"""

import json
import os
import time
import urllib.request
import urllib.error
import uuid

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_PROJECT_REF = os.environ["SUPABASE_PROJECT_REF"]
SUPABASE_MGMT_TOKEN = os.environ["SUPABASE_MGMT_TOKEN"]

RISK_CLASS_MAP = {
    1: "Class I",
    2: "Class II",
    3: "Class III",
    4: "Class IV",
}

# Rough category from licence_type_desc / name patterns (best effort)
def guess_category(name: str, risk_class: int) -> str:
    name_l = name.lower()
    if any(k in name_l for k in ["cardiac", "heart", "stent", "coronary", "vascular", "blood pressure", "pacemaker", "defibrillator", "valve"]):
        return "Cardiovascular"
    if any(k in name_l for k in ["knee", "hip", "spine", "orthop", "bone", "joint", "fixat"]):
        return "Orthopedic"
    if any(k in name_l for k in ["neuro", "brain", "spinal cord", "stimulat"]):
        return "Neurology"
    if any(k in name_l for k in ["eye", "ophthalm", "lens", "cornea", "vitreous", "retina"]):
        return "Ophthalmology"
    if any(k in name_l for k in ["glucose", "insulin", "diabetes", "cgm"]):
        return "Endocrinology"
    if any(k in name_l for k in ["dental", "tooth", "orthodont", "implant"]) and "dental" in name_l:
        return "Dental"
    if any(k in name_l for k in ["breath", "lung", "pulmon", "ventilat", "cpap", "respir"]):
        return "Pulmonology"
    if any(k in name_l for k in ["renal", "kidney", "dialysis", "urolog", "bladder"]):
        return "Urology"
    if any(k in name_l for k in ["skin", "wound", "derma", "dressing"]):
        return "Dermatology"
    if any(k in name_l for k in ["assay", "test", "reagent", "diagnostic", "analyzer"]):
        return "Diagnostics"
    if any(k in name_l for k in ["imaging", "mri", "ct scan", "ultrasound", "x-ray", "xray"]):
        return "Radiology/Imaging"
    if risk_class >= 3:
        return "General Surgery"
    return "General"


def rest_post(path: str, data: list, retry: int = 3) -> int:
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
            "User-Agent": "curl/7.81.0",
        },
    )
    for attempt in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            print(f"    HTTP {e.code}: {body}")
            if attempt < retry - 1:
                time.sleep(2)
            else:
                raise
    return 0


def mgmt_query(sql: str):
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


def main():
    print("=" * 60)
    print("DeviceAtlas — Import Canada-Only HC Devices")
    print("=" * 60)

    # Load cached HC data
    print("Loading HC data from cache...")
    with open("/tmp/hc_licences.json") as f:
        active_licences = json.load(f)
    with open("/tmp/hc_companies.json") as f:
        companies = json.load(f)
    with open("/tmp/hc_matches.json") as f:
        matches = json.load(f)

    # Build company lookup
    company_map = {c["company_id"]: c["company_name"] for c in companies}

    # Find already-matched HC licence numbers
    matched_licence_nos = {m["hc"]["licence_no"] for m in matches}
    print(f"Already matched: {len(matched_licence_nos)} licences")

    # Get unmatched active licences
    unmatched = [
        l for l in active_licences
        if l.get("original_licence_no") not in matched_licence_nos
        and l.get("licence_name")
        and l.get("licence_status") == "I"  # Active only
    ]
    print(f"Canada-only devices to import: {len(unmatched)}")

    # Check for already-imported HC devices (by source_ref in approvals)
    print("Checking existing HC-only devices already in DB...")
    existing = mgmt_query(
        "SELECT source_ref FROM deviceatlas_approvals WHERE country='CA' AND disease_state_id IS NULL;"
    )
    existing_refs = {str(r["source_ref"]) for r in (existing or [])}
    print(f"  Already imported: {len(existing_refs)}")

    unmatched = [l for l in unmatched if str(l.get("original_licence_no", "")) not in existing_refs]
    print(f"  Remaining to import: {len(unmatched)}")

    # Batch insert devices + approvals
    batch_size = 200
    total_devices = 0
    total_approvals = 0
    errors = 0

    for i in range(0, len(unmatched), batch_size):
        batch = unmatched[i:i + batch_size]

        device_rows = []
        approval_rows = []

        for lic in batch:
            dev_id = str(uuid.uuid4())
            name = lic["licence_name"].strip()
            company_id = lic.get("company_id")
            manufacturer = company_map.get(company_id, "Unknown")
            risk_class = lic.get("appl_risk_class", 2)
            approval_date = lic.get("first_licence_status_dt")
            licence_no = lic.get("original_licence_no")
            licence_type = lic.get("licence_type_desc", "")

            device_rows.append({
                "id": dev_id,
                "name": name,
                "manufacturer": manufacturer,
                "category": guess_category(name, risk_class),
                "description": None,
                "is_active": True,
                "device_class": RISK_CLASS_MAP.get(risk_class, f"Class {risk_class}"),
                "clearance_type": licence_type,
                "cleared_date": approval_date,
            })

            approval_rows.append({
                "device_id": dev_id,
                "disease_state_id": None,
                "country": "CA",
                "status": "Approved",
                "approval_date": approval_date,
                "source_ref": str(licence_no),
                "is_active": True,
            })

        try:
            rest_post("deviceatlas_devices", device_rows)
            total_devices += len(device_rows)
            rest_post("deviceatlas_approvals", approval_rows)
            total_approvals += len(approval_rows)
        except Exception as e:
            print(f"  ERROR on batch {i//batch_size}: {e}")
            errors += 1
            time.sleep(3)
            continue

        if (i // batch_size) % 10 == 0 and i > 0:
            print(f"  {total_devices}/{len(unmatched)} devices inserted...")

    print("\n" + "=" * 60)
    print(f"DONE.")
    print(f"  Devices inserted: {total_devices}")
    print(f"  CA approvals inserted: {total_approvals}")
    print(f"  Errors: {errors}")

    # Final counts
    counts = mgmt_query(
        "SELECT "
        "(SELECT COUNT(*) FROM deviceatlas_devices) as total_devices, "
        "(SELECT COUNT(*) FROM deviceatlas_approvals WHERE country='CA') as ca_approvals, "
        "(SELECT COUNT(*) FROM deviceatlas_approvals WHERE country='US') as us_approvals;"
    )
    if counts:
        c = counts[0]
        print(f"  Total devices in DB: {c['total_devices']}")
        print(f"  US approvals: {c['us_approvals']}")
        print(f"  CA approvals: {c['ca_approvals']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
