#!/usr/bin/env python3
"""
DeviceAtlas — Batch Disease State Enrichment (Two-Pass)

Pass 1: Batch-classify devices → raw disease states (no descriptions)
  - FDA product codes: 50 per Grok call
  - Non-FDA device names: 200 per Grok call
Pass 2: Consolidate/deduplicate all disease state names
Pass 3: Write to DB — create disease states, link approvals

Descriptions are NOT generated here — they load lazily when a user views a device.
"""

import json, os, re, sys, time, urllib.request, urllib.error, uuid
from collections import defaultdict
from difflib import SequenceMatcher

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY  = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
PROJECT_REF  = os.environ["SUPABASE_PROJECT_REF"]
GROK_API_KEY = os.environ["GROK_API_KEY"]

GROK_MODEL    = "grok-4"
GROK_ENDPOINT = "https://api.x.ai/v1/chat/completions"
FDA_CLASS_CACHE = "/tmp/fda_class_cache.json"
RESULTS_FILE    = "/tmp/batch_ds_results.json"  # checkpoint: raw results from pass 1

HEADERS_REST = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
    "User-Agent": "curl/7.81.0",
}

# ── HTTP helpers ──────────────────────────────────────────────────────────────
def mgmt_query(sql):
    tok = os.environ.get("SUPABASE_MGMT_TOKEN", "")
    payload = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=payload, method="POST",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                 "User-Agent": "curl/7.81.0"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                result = json.loads(r.read())
                if isinstance(result, dict) and result.get("message"):
                    if attempt < 2:
                        time.sleep(5)
                        continue
                    raise RuntimeError(f"MGMT error: {result['message']}")
                return result if isinstance(result, list) else []
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if attempt < 2:
                time.sleep(5)
                continue
            raise RuntimeError(f"MGMT HTTP {e.code}: {body}")
    return []

def rest_post(path, data):
    payload = json.dumps(data if isinstance(data, list) else [data]).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=payload, method="POST", headers=HEADERS_REST,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        pass

def rest_patch(path, params, data):
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}?{params}",
        data=payload, method="PATCH", headers=HEADERS_REST,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        pass

def rest_delete(path, params):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}?{params}",
        method="DELETE", headers=HEADERS_REST,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        pass

def rest_get(path, params=""):
    url = f"{SUPABASE_URL}/rest/v1/{path}{'?' + params if params else ''}"
    req = urllib.request.Request(url, headers={**HEADERS_REST, "Prefer": "return=representation"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

# ── Grok API ──────────────────────────────────────────────────────────────────
def grok_call(system, user, max_tokens=4000):
    payload = json.dumps({
        "model": GROK_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }).encode()

    for attempt in range(6):
        try:
            req = urllib.request.Request(
                GROK_ENDPOINT, data=payload, method="POST",
                headers={
                    "Authorization": f"Bearer {GROK_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
            content = data["choices"][0]["message"]["content"].strip()
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content.strip())
            return json.loads(content)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 30 * (attempt + 1)
                print(f"  [429] sleeping {wait}s (attempt {attempt+1})")
                time.sleep(wait)
                continue
            body = e.read().decode()[:200]
            print(f"  [HTTP {e.code}] {body}")
            if attempt < 5:
                time.sleep(10)
                continue
            return None
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  [parse error] {e}")
            if attempt < 5:
                time.sleep(5)
                continue
            return None
    return None

# ── Name normalization ────────────────────────────────────────────────────────
def normalize_device_name(name):
    s = name.lower().strip().strip('"').strip()
    s = re.sub(r'\s*\([^)]*\d+[^)]*\)\s*$', '', s)
    s = re.sub(r'[\s,]*[#]?\s*\d[\d.xX/\-]*\s*(mm|cm|ml|fr|gauge|ga|inch|in|cc|mg|g|l)[\s\w]*$', '', s, flags=re.I)
    s = re.sub(r'[\s,]*[øØ]\s*\d.*$', '', s)
    s = re.sub(r'\s+\d[\d./]*\s*$', '', s)
    return s.strip()

# ── FDA Classification Cache ─────────────────────────────────────────────────
def load_fda_cache():
    if os.path.exists(FDA_CLASS_CACHE):
        with open(FDA_CLASS_CACHE) as f:
            return json.load(f)
    return {}

# ══════════════════════════════════════════════════════════════════════════════
# PASS 1: Batch classify → raw disease states
# ══════════════════════════════════════════════════════════════════════════════

FDA_BATCH_SYSTEM = """You are a medical device classification expert. Given a list of FDA product codes
with their generic names and medical specialties, return the disease states each device type
diagnoses, treats, or monitors.

Return a JSON object where keys are the product codes and values are arrays of disease state names.
Use standard FDA medical terminology. Limit to 1-4 disease states per code. Example:

{"QAS": ["Coronary Artery Disease", "Peripheral Artery Disease"],
 "DXY": ["Osteoarthritis of the Hip", "Hip Fracture"]}

Return ONLY the JSON object."""

NON_FDA_BATCH_SYSTEM = """You are a medical device classification expert. Given a list of medical device names
(from EU, Canada, or Japan regulatory databases), return the disease states each device type
diagnoses, treats, or monitors.

Use standard FDA medical terminology for disease state names to ensure cross-country consistency.
Limit to 1-4 disease states per device. If a device is too generic or unclear, return [].

Return a JSON object where keys are the device names (exactly as given) and values are arrays
of disease state names. Example:

{"acetabular cup cementless titanium plasma coated": ["Osteoarthritis of the Hip", "Hip Fracture"],
 "coronary stent drug-eluting": ["Coronary Artery Disease"]}

Return ONLY the JSON object."""


def pass1_fda(fda_cache):
    """Batch-classify FDA product codes → disease states."""
    print("\n=== PASS 1A: FDA Product Codes ===")

    # Get unique product codes for approved, unenriched devices
    rows = mgmt_query("""
        SELECT DISTINCT d.product_code
        FROM deviceatlas_devices d
        JOIN deviceatlas_approvals a ON a.device_id = d.id
        WHERE d.product_code IS NOT NULL
          AND d.enrichment_method IS NULL
        ORDER BY d.product_code;
    """)
    codes = [r["product_code"] for r in rows if r.get("product_code")]
    print(f"  Product codes to classify: {len(codes)}")

    results = {}  # code → [disease_states]
    batch_size = 50

    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(codes) + batch_size - 1) // batch_size

        # Build prompt with FDA classification context
        lines = []
        for code in batch:
            info = fda_cache.get(code)
            if info and (info.get("generic_name") or info.get("specialty")):
                lines.append(f"{code} | {info['generic_name']} | {info['specialty']}")
            else:
                lines.append(f"{code} | (no classification data)")

        user_prompt = "Classify these FDA product codes:\n\n" + "\n".join(lines)
        result = grok_call(FDA_BATCH_SYSTEM, user_prompt, max_tokens=4000)

        if result and isinstance(result, dict):
            results.update(result)
            print(f"  [{batch_num}/{total_batches}] +{len(result)} codes classified")
        else:
            print(f"  [{batch_num}/{total_batches}] FAILED — skipping batch")

        time.sleep(3)  # rate limit safety

    return results


def pass1_non_fda():
    """Batch-classify non-FDA device names → disease states."""
    print("\n=== PASS 1B: Non-FDA Device Names ===")

    # Get all unique normalized names for unenriched approved devices
    all_rows = []
    offset = 0
    while True:
        rows = mgmt_query(f"""
            SELECT DISTINCT LOWER(TRIM(d.name)) as n
            FROM deviceatlas_devices d
            JOIN deviceatlas_approvals a ON a.device_id = d.id
            WHERE d.product_code IS NULL
              AND d.enrichment_method IS NULL
            ORDER BY n
            LIMIT 5000 OFFSET {offset};
        """)
        if not rows:
            break
        all_rows.extend(rows)
        offset += 5000
        if len(rows) < 5000:
            break

    # Group by normalized name
    groups = defaultdict(list)  # normalized → [raw names]
    for row in all_rows:
        raw = row["n"]
        norm = normalize_device_name(raw)
        if norm:
            groups[norm].append(raw)

    unique_names = sorted(groups.keys())
    print(f"  Raw unique names: {len(all_rows):,}")
    print(f"  Normalized groups: {len(unique_names):,}")

    results = {}  # normalized_name → [disease_states]
    batch_size = 200

    for i in range(0, len(unique_names), batch_size):
        batch = unique_names[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(unique_names) + batch_size - 1) // batch_size

        user_prompt = "Classify these medical devices:\n\n" + "\n".join(f"- {n}" for n in batch)
        result = grok_call(NON_FDA_BATCH_SYSTEM, user_prompt, max_tokens=16000)

        if result and isinstance(result, dict):
            results.update(result)
            matched = sum(1 for n in batch if n in result)
            print(f"  [{batch_num}/{total_batches}] +{matched}/{len(batch)} names classified "
                  f"(total: {len(results):,})")
        else:
            print(f"  [{batch_num}/{total_batches}] FAILED — skipping batch")

        time.sleep(3)

    return results, groups


# ══════════════════════════════════════════════════════════════════════════════
# PASS 2: Consolidate disease state names
# ══════════════════════════════════════════════════════════════════════════════

CONSOLIDATION_SYSTEM = """You are a medical terminology expert. Given a list of disease state names used to
classify medical devices, consolidate them:

1. Merge exact/near duplicates (e.g. "Coronary Heart Disease" = "Coronary Artery Disease" → keep one)
2. Standardize to FDA medical terminology
3. Remove overly vague terms (e.g. "General Health", "Various Conditions")

Return a JSON object mapping original names to canonical names. Only include names that need
to be renamed. Names that are already correct should NOT appear.

Example: {"Coronary Heart Disease": "Coronary Artery Disease", "DM Type 2": "Type 2 Diabetes Mellitus"}

Return ONLY the JSON object."""


def pass2_consolidate(all_disease_names):
    """Send all unique disease state names to Grok for dedup/standardization."""
    print(f"\n=== PASS 2: Consolidate {len(all_disease_names)} disease state names ===")

    # Process in chunks (Grok can handle ~500 names per call)
    canonical_map = {}  # original → canonical
    chunk_size = 400

    sorted_names = sorted(all_disease_names)
    for i in range(0, len(sorted_names), chunk_size):
        chunk = sorted_names[i:i+chunk_size]
        chunk_num = i // chunk_size + 1
        total_chunks = (len(sorted_names) + chunk_size - 1) // chunk_size

        user_prompt = "Consolidate these disease state names:\n\n" + "\n".join(f"- {n}" for n in chunk)
        result = grok_call(CONSOLIDATION_SYSTEM, user_prompt, max_tokens=8000)

        if result and isinstance(result, dict):
            canonical_map.update(result)
            print(f"  [chunk {chunk_num}/{total_chunks}] {len(result)} names remapped")
        else:
            print(f"  [chunk {chunk_num}/{total_chunks}] FAILED — keeping originals")

        time.sleep(3)

    print(f"  Total remappings: {len(canonical_map)}")
    return canonical_map


# ══════════════════════════════════════════════════════════════════════════════
# PASS 3: Write to DB
# ══════════════════════════════════════════════════════════════════════════════

def normalize_ds_name(s):
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def pass3_write_to_db(fda_results, non_fda_results, non_fda_groups, canonical_map):
    """Create disease states and link to devices via approvals."""
    print("\n=== PASS 3: Write to DB ===")

    # Load existing disease states
    existing = mgmt_query("SELECT id, name FROM deviceatlas_disease_states;")
    ds_lookup = {}  # normalized_name → id
    for row in existing:
        ds_lookup[normalize_ds_name(row["name"])] = row["id"]

    def get_or_create_ds(name):
        """Get or create a disease state, return its ID."""
        # Apply canonical mapping
        canonical = canonical_map.get(name, name).strip().title()
        norm = normalize_ds_name(canonical)

        if norm in ds_lookup:
            return ds_lookup[norm]

        # Fuzzy match
        best_score, best_id = 0.0, None
        for cand_norm, cand_id in ds_lookup.items():
            s = SequenceMatcher(None, norm, cand_norm).ratio()
            if s > best_score:
                best_score, best_id = s, cand_id
        if best_score >= 0.90 and best_id:
            ds_lookup[norm] = best_id
            return best_id

        new_id = str(uuid.uuid4())
        try:
            rest_post("deviceatlas_disease_states", {"id": new_id, "name": canonical})
        except Exception as e:
            # Might already exist from a race condition
            print(f"  DS create err '{canonical}': {e}")
            return None
        ds_lookup[norm] = new_id
        return new_id

    # ── Process FDA devices ──────────────────────────────────────────────────
    print("  Processing FDA devices...")
    fda_processed = 0
    for code, disease_names in fda_results.items():
        if not disease_names:
            continue

        ds_ids = []
        for dn in disease_names:
            ds_id = get_or_create_ds(dn)
            if ds_id and ds_id not in ds_ids:
                ds_ids.append(ds_id)

        if not ds_ids:
            continue

        # Get all unenriched devices with this product code
        devices = mgmt_query(f"""
            SELECT d.id FROM deviceatlas_devices d
            JOIN deviceatlas_approvals a ON a.device_id = d.id
            WHERE d.product_code = '{code}'
              AND d.enrichment_method IS NULL
            LIMIT 5000;
        """)
        device_ids = list(set(r["id"] for r in devices))

        for dev_id in device_ids:
            try:
                update_device_approvals(dev_id, ds_ids)
                rest_patch("deviceatlas_devices", f"id=eq.{dev_id}", {
                    "enrichment_method": "fda_classification_batch",
                    "enrichment_confidence": "high",
                    "updated_at": "now()",
                })
                fda_processed += 1
            except Exception as e:
                print(f"  FDA dev err {dev_id}: {e}")

        if fda_processed % 500 == 0 and fda_processed > 0:
            print(f"    FDA: {fda_processed:,} devices linked")

    print(f"  FDA complete: {fda_processed:,} devices")

    # ── Process non-FDA devices ──────────────────────────────────────────────
    print("  Processing non-FDA devices...")
    non_fda_processed = 0

    for norm_name, disease_names in non_fda_results.items():
        if not disease_names:
            continue

        ds_ids = []
        for dn in disease_names:
            ds_id = get_or_create_ds(dn)
            if ds_id and ds_id not in ds_ids:
                ds_ids.append(ds_id)

        if not ds_ids:
            continue

        # Get all raw names that map to this normalized name
        raw_names = non_fda_groups.get(norm_name, [norm_name])

        for raw_name in raw_names:
            # Escape single quotes for SQL
            escaped = raw_name.replace("'", "''")
            devices = mgmt_query(f"""
                SELECT DISTINCT d.id FROM deviceatlas_devices d
                JOIN deviceatlas_approvals a ON a.device_id = d.id
                WHERE LOWER(TRIM(d.name)) = '{escaped}'
                  AND d.product_code IS NULL
                  AND d.enrichment_method IS NULL
                LIMIT 500;
            """)

            for dev in devices:
                try:
                    update_device_approvals(dev["id"], ds_ids)
                    rest_patch("deviceatlas_devices", f"id=eq.{dev['id']}", {
                        "enrichment_method": "batch_inferred",
                        "enrichment_confidence": "medium",
                        "updated_at": "now()",
                    })
                    non_fda_processed += 1
                except Exception as e:
                    print(f"  Non-FDA dev err {dev['id']}: {e}")

        if non_fda_processed % 1000 == 0 and non_fda_processed > 0:
            print(f"    Non-FDA: {non_fda_processed:,} devices linked")

    print(f"  Non-FDA complete: {non_fda_processed:,} devices")
    print(f"\n  TOTAL: {fda_processed + non_fda_processed:,} devices enriched")


def update_device_approvals(device_id, ds_ids):
    """Expand approval rows: one per (country x disease_state)."""
    existing = rest_get(
        "deviceatlas_approvals",
        f"device_id=eq.{device_id}&select=id,country,source_ref,approval_date,status,is_active",
    )
    if not existing or not ds_ids:
        return

    by_country = defaultdict(list)
    for row in existing:
        by_country[row["country"]].append(row)

    for country, rows in by_country.items():
        primary = rows[0]
        ids_csv = ",".join(f'"{r["id"]}"' for r in rows)
        rest_delete("deviceatlas_approvals", f"id=in.({ids_csv})")
        rest_post("deviceatlas_approvals", [
            {
                "device_id": device_id,
                "disease_state_id": ds_id,
                "country": country,
                "status": primary.get("status", "Approved"),
                "approval_date": primary.get("approval_date"),
                "source_ref": primary.get("source_ref"),
                "is_active": primary.get("is_active", True),
            }
            for ds_id in ds_ids
        ])


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    print("=" * 66)
    print("DeviceAtlas — Batch Disease State Enrichment")
    print(f"Mode: {mode}")
    print("=" * 66)

    # Load checkpoint if exists
    checkpoint = {}
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            checkpoint = json.load(f)
        print(f"Loaded checkpoint: {len(checkpoint.get('fda', {}))} FDA, "
              f"{len(checkpoint.get('non_fda', {}))} non-FDA results")

    if mode in ("all", "pass1", "fda"):
        fda_cache = load_fda_cache()
        print(f"FDA classification cache: {len(fda_cache)} entries")

        fda_results = pass1_fda(fda_cache)
        checkpoint["fda"] = fda_results

        with open(RESULTS_FILE, "w") as f:
            json.dump(checkpoint, f)
        print(f"Saved checkpoint: {len(fda_results)} FDA results")

    if mode in ("all", "pass1", "non_fda"):
        non_fda_results, non_fda_groups = pass1_non_fda()
        checkpoint["non_fda"] = non_fda_results
        # Store groups mapping too
        checkpoint["non_fda_groups"] = {k: v for k, v in non_fda_groups.items()}

        with open(RESULTS_FILE, "w") as f:
            json.dump(checkpoint, f)
        print(f"Saved checkpoint: {len(non_fda_results)} non-FDA results")

    if mode in ("all", "pass2"):
        fda_results = checkpoint.get("fda", {})
        non_fda_results = checkpoint.get("non_fda", {})

        # Collect all unique disease state names
        all_ds_names = set()
        for ds_list in fda_results.values():
            if isinstance(ds_list, list):
                all_ds_names.update(ds_list)
        for ds_list in non_fda_results.values():
            if isinstance(ds_list, list):
                all_ds_names.update(ds_list)

        print(f"Unique disease state names from pass 1: {len(all_ds_names)}")

        canonical_map = pass2_consolidate(all_ds_names)
        checkpoint["canonical_map"] = canonical_map

        with open(RESULTS_FILE, "w") as f:
            json.dump(checkpoint, f)

    if mode in ("all", "pass3"):
        fda_results = checkpoint.get("fda", {})
        non_fda_results = checkpoint.get("non_fda", {})
        non_fda_groups = checkpoint.get("non_fda_groups", {})
        canonical_map = checkpoint.get("canonical_map", {})

        pass3_write_to_db(fda_results, non_fda_results, non_fda_groups, canonical_map)

    print("\nDone!")


if __name__ == "__main__":
    main()
