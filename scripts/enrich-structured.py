#!/usr/bin/env python3
"""
DeviceAtlas — Structured Disease State & Description Enrichment

Pipeline:
1. Fetch FDA Product Classification for every unique product_code (~4,893 codes)
   → cache to /tmp/fda_class_cache.json
2. Process devices in cursor batches of 25
3. For each device, build a structured Grok prompt using:
   - Trade name (device.name)
   - FDA generic device name (from classification)
   - FDA medical specialty (Cardiovascular, Dental, etc.)
   - FDA device class (I / II / III)
   - clearance_type (PMA / Traditional / De Novo)
   Grok returns:
     description       (2-3 sentence clinical description)
     disease_states    (list of {name, confidence: high|medium|low})
     enrichment_method (fda_classification | grok_inferred)
4. For each disease state:
   - Match/create in deviceatlas_disease_states
   - Create one approval row per (device × country × disease_state)
     Existing approval rows for this device+country are preserved for source_ref/date,
     but disease_state_id is applied across all countries the device appears in.
5. Save device fields: description, indications_text, indications_source,
   enrichment_method, enrichment_confidence

Usage:
  python3 -u enrich-structured.py [worker_id]
  worker_id: 0 = even last-hex-digit UUIDs, 1 = odd (default: 0)

  Run two workers in parallel:
    nohup python3 -u enrich-structured.py 0 > /tmp/enrich-s0.log 2>&1 &
    nohup python3 -u enrich-structured.py 1 > /tmp/enrich-s1.log 2>&1 &
"""

import json, os, re, sys, time, urllib.request, urllib.error, uuid
from difflib import SequenceMatcher

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL        = os.environ["SUPABASE_URL"]
SERVICE_KEY         = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
PROJECT_REF         = os.environ["SUPABASE_PROJECT_REF"]
GROK_API_KEY        = os.environ["GROK_API_KEY"]

WORKER_ID           = int(sys.argv[1]) if len(sys.argv) > 1 else 0
BATCH               = 25
GROK_MODEL          = "grok-4-1-fast-non-reasoning"
GROK_ENDPOINT       = "https://api.x.ai/v1/chat/completions"
FDA_CLASS_CACHE     = "/tmp/fda_class_cache.json"
MGMT_TOKEN_FILE     = "/tmp/mgmt_token.txt"

# ── HTTP helpers ──────────────────────────────────────────────────────────────
HEADERS_REST = {
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
                if isinstance(result, dict) and result.get("message"):
                    if attempt < 2:
                        time.sleep(5)
                        continue
                    raise RuntimeError(f"MGMT error: {result['message']}")
                return result if isinstance(result, list) else []
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if "canceling statement" in body or e.code == 408:
                time.sleep(10)
                continue
            raise RuntimeError(f"MGMT HTTP {e.code}: {body}")
    return []

def rest_get(path: str, params: str = "") -> list:
    url = f"{SUPABASE_URL}/rest/v1/{path}{'?' + params if params else ''}"
    req = urllib.request.Request(url, headers={**HEADERS_REST, "Prefer": "return=representation"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def rest_post(path: str, data: list | dict) -> None:
    payload = json.dumps(data if isinstance(data, list) else [data]).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=payload, method="POST", headers=HEADERS_REST,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        pass

def rest_patch(path: str, params: str, data: dict) -> None:
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}?{params}",
        data=payload, method="PATCH", headers=HEADERS_REST,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        pass

def rest_delete(path: str, params: str) -> None:
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}?{params}",
        method="DELETE", headers=HEADERS_REST,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        pass

# ── FDA Classification Cache ──────────────────────────────────────────────────
def fetch_fda_classification(product_code: str) -> dict | None:
    url = f"https://api.fda.gov/device/classification.json?search=product_code:{product_code}&limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.81.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
            if "results" not in d:
                return None
            r = d["results"][0]
            return {
                "generic_name": r.get("device_name", "") or "",
                "specialty": r.get("medical_specialty_description", "") or "",
                "device_class": r.get("device_class", "") or "",
                "regulation_number": r.get("regulation_number", "") or "",
                "definition": (r.get("definition", "") or "")[:500],
            }
    except Exception:
        return None

def build_fda_class_cache(product_codes: list[str]) -> dict:
    if os.path.exists(FDA_CLASS_CACHE):
        print(f"[W{WORKER_ID}] Loading FDA classification cache from disk...")
        with open(FDA_CLASS_CACHE) as f:
            cache = json.load(f)
        print(f"[W{WORKER_ID}]   {len(cache)} entries loaded")
        # Fetch any missing codes
        missing = [c for c in product_codes if c not in cache]
        if missing:
            print(f"[W{WORKER_ID}]   Fetching {len(missing)} new codes...")
            for i, code in enumerate(missing):
                cache[code] = fetch_fda_classification(code)
                if (i + 1) % 200 == 0:
                    print(f"[W{WORKER_ID}]   {i+1}/{len(missing)}...")
                    with open(FDA_CLASS_CACHE, "w") as f:
                        json.dump(cache, f)
            with open(FDA_CLASS_CACHE, "w") as f:
                json.dump(cache, f)
        return cache

    print(f"[W{WORKER_ID}] Building FDA classification cache ({len(product_codes)} codes)...")
    cache = {}
    for i, code in enumerate(product_codes):
        cache[code] = fetch_fda_classification(code)
        if (i + 1) % 100 == 0:
            print(f"[W{WORKER_ID}]   {i+1}/{len(product_codes)} codes fetched...")
            with open(FDA_CLASS_CACHE, "w") as f:
                json.dump(cache, f)
        time.sleep(0.05)  # gentle rate limiting
    with open(FDA_CLASS_CACHE, "w") as f:
        json.dump(cache, f)
    print(f"[W{WORKER_ID}]   Cache saved: {len(cache)} entries")
    return cache

# ── Grok ──────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a medical device classification expert.
Given FDA structured data about a medical device, return a JSON object with:
- "description": 2-3 sentence clinical description for healthcare professionals.
  Use the FDA generic name and specialty as primary grounding. Be factual and precise.
- "disease_states": list of objects {name, confidence} identifying medical conditions
  this device is used to diagnose, treat, or monitor. Use established medical terminology.
  confidence: "high" if the indication is definitively established for this device type,
  "medium" if likely but the device serves a broader purpose, "low" if inferred.
  Limit to 1-4 disease states. If none can be determined, return [].
- "enrichment_method": "fda_classification" if you used FDA generic name/specialty data,
  "grok_inferred" if you only had the trade name to work with.

IMPORTANT: Ground your response in the FDA classification data provided.
Do NOT invent indications. If the device is a general diagnostic tool (e.g., MRI),
list the specialties/conditions it is primarily used for in clinical practice.
Return ONLY the JSON object, no other text."""

def grok_enrich(device_name: str, classification: dict | None) -> dict | None:
    """Call Grok with structured FDA data. Returns parsed JSON or None."""
    has_class = classification and (
        classification.get("generic_name") or classification.get("specialty")
    )

    if has_class:
        context = (
            f"Trade name: {device_name}\n"
            f"FDA generic device name: {classification['generic_name']}\n"
            f"FDA medical specialty: {classification['specialty']}\n"
            f"FDA device class: {classification['device_class']}\n"
            f"FDA regulation number: {classification['regulation_number']}\n"
        )
        if classification.get("definition"):
            context += f"FDA definition: {classification['definition']}\n"
    else:
        context = f"Trade name: {device_name}\n(No FDA classification data available)"

    payload = json.dumps({
        "model": GROK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        "temperature": 0.1,
        "max_tokens": 600,
    }).encode()

    for attempt in range(5):
        try:
            req = urllib.request.Request(
                GROK_ENDPOINT, data=payload, method="POST",
                headers={
                    "Authorization": f"Bearer {GROK_API_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": "curl/7.81.0",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            content = data["choices"][0]["message"]["content"].strip()
            # Strip markdown fences if present
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content.strip())
            return json.loads(content)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 60 * (attempt + 1)
                print(f"[W{WORKER_ID}]   Grok 429 — sleeping {wait}s")
                time.sleep(wait)
                continue
            raise
        except (json.JSONDecodeError, KeyError) as e:
            if attempt < 4:
                time.sleep(5)
                continue
            return None
    return None

# ── Disease State Matching ────────────────────────────────────────────────────
def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

class DiseaseStateCache:
    def __init__(self):
        self._cache: dict[str, str] = {}  # norm_name → id
        self._load()

    def _load(self):
        rows = mgmt_query("SELECT id, name FROM deviceatlas_disease_states;")
        for r in rows:
            self._cache[normalize(r["name"])] = r["id"]

    def get_or_create(self, name: str) -> str:
        norm = normalize(name)
        # Exact match
        if norm in self._cache:
            return self._cache[norm]
        # Fuzzy match (≥0.85)
        best_score, best_id = 0.0, None
        for cand_norm, cand_id in self._cache.items():
            s = similarity(norm, cand_norm)
            if s > best_score:
                best_score, best_id = s, cand_id
        if best_score >= 0.85 and best_id:
            # Map to existing entry
            self._cache[norm] = best_id
            return best_id
        # Create new
        new_id = str(uuid.uuid4())
        rest_post("deviceatlas_disease_states", {"id": new_id, "name": name.strip().title()})
        self._cache[norm] = new_id
        return new_id

# ── Approval Row Helpers ──────────────────────────────────────────────────────
def get_approvals_for_device(device_id: str) -> list:
    """Get all approval rows for a device across countries."""
    rows = rest_get(
        "deviceatlas_approvals",
        f"device_id=eq.{device_id}&select=id,country,source_ref,approval_date,status,is_active",
    )
    return rows

def update_approvals_with_disease_states(
    device_id: str,
    disease_state_ids: list[str],  # ordered by confidence (primary first)
    ds_cache: DiseaseStateCache,
) -> None:
    """
    For each country this device has approvals in, ensure there's one approval
    row per disease state. We keep existing source_ref / approval_date.
    """
    existing = get_approvals_for_device(device_id)
    if not disease_state_ids:
        return

    # Group by country
    by_country: dict[str, list] = {}
    for row in existing:
        by_country.setdefault(row["country"], []).append(row)

    for country, rows in by_country.items():
        # Take the canonical source_ref / date from the first (primary) row
        primary = rows[0]
        source_ref = primary.get("source_ref")
        approval_date = primary.get("approval_date")
        status = primary.get("status", "Approved")
        is_active = primary.get("is_active", True)

        # Delete all existing approval rows for this device+country
        existing_ids = ",".join(r["id"] for r in rows)
        rest_delete("deviceatlas_approvals", f"id=in.({existing_ids})")

        # Insert one row per disease state
        new_rows = []
        for ds_id in disease_state_ids:
            new_rows.append({
                "device_id": device_id,
                "disease_state_id": ds_id,
                "country": country,
                "status": status,
                "approval_date": approval_date,
                "source_ref": source_ref,
                "is_active": is_active,
            })
        if new_rows:
            rest_post("deviceatlas_approvals", new_rows)

# ── Main enrichment loop ──────────────────────────────────────────────────────
def build_indications_text(disease_states: list[dict]) -> str:
    """Construct a readable indications text from disease state list."""
    if not disease_states:
        return ""
    parts = []
    for ds in disease_states:
        conf = ds.get("confidence", "medium")
        parts.append(f"{ds['name']} [{conf}]")
    return "; ".join(parts)

def main():
    print("=" * 62)
    print(f"DeviceAtlas — Structured Enrichment — Worker {WORKER_ID}")
    print("=" * 62)

    # Load disease state cache
    print(f"[W{WORKER_ID}] Loading disease state cache...")
    ds_cache = DiseaseStateCache()
    print(f"[W{WORKER_ID}]   {len(ds_cache._cache)} disease states loaded")

    # Get all unique product codes and build classification cache
    # (only worker 0 builds the cache; worker 1 waits and loads it)
    rows = mgmt_query("SELECT DISTINCT product_code FROM deviceatlas_devices WHERE product_code IS NOT NULL;")
    all_codes = [r["product_code"] for r in rows if r.get("product_code")]
    print(f"[W{WORKER_ID}]   {len(all_codes)} unique product codes")

    if WORKER_ID == 0:
        fda_cache = build_fda_class_cache(all_codes)
    else:
        # Wait for worker 0 to create the cache
        waited = 0
        while not os.path.exists(FDA_CLASS_CACHE) and waited < 3600:
            print(f"[W{WORKER_ID}] Waiting for FDA cache from worker 0... ({waited}s)")
            time.sleep(30)
            waited += 30
        fda_cache = build_fda_class_cache(all_codes)

    # Find devices not yet enriched, split by worker parity (last hex digit of UUID)
    # Process ALL devices (both US/FDA and HC-only)
    cursor = "00000000-0000-0000-0000-000000000000"
    total_done = 0

    print(f"[W{WORKER_ID}] Starting enrichment loop...")
    while True:
        # Fetch next batch of un-enriched devices for this worker's parity
        sql = f"""
            SELECT d.id, d.name, d.product_code, d.submission_number,
                   d.clearance_type, d.device_class, d.manufacturer
            FROM deviceatlas_devices d
            WHERE d.id > '{cursor}'
              AND d.enrichment_method IS NULL
              AND (
                -- Even UUIDs for worker 0, odd for worker 1
                get_byte(decode(replace(d.id::text, '-', ''), 'hex'), 15) % 2 = {WORKER_ID}
              )
            ORDER BY d.id
            LIMIT {BATCH};
        """
        devices = mgmt_query(sql)
        if not devices:
            print(f"[W{WORKER_ID}] No more devices to process — done!")
            break

        cursor = devices[-1]["id"]
        batch_num = total_done // BATCH + 1

        for dev in devices:
            dev_id = dev["id"]
            dev_name = dev.get("name") or ""
            product_code = dev.get("product_code")

            # Get classification data
            classification = fda_cache.get(product_code) if product_code else None

            # Call Grok
            result = grok_enrich(dev_name, classification)
            if not result:
                # Mark as attempted-but-failed to skip next run
                rest_patch(
                    "deviceatlas_devices", f"id=eq.{dev_id}",
                    {"enrichment_method": "not_enriched", "enrichment_confidence": "low",
                     "updated_at": "now()"}
                )
                continue

            description = result.get("description", "")
            disease_states_raw = result.get("disease_states", [])
            enrichment_method = result.get("enrichment_method", "grok_inferred")

            # Determine confidence
            high_confs = sum(1 for d in disease_states_raw if d.get("confidence") == "high")
            if enrichment_method == "fda_classification" and high_confs > 0:
                confidence = "high"
            elif enrichment_method == "fda_classification":
                confidence = "medium"
            else:
                confidence = "low"

            # Indications source
            if product_code:
                indications_source = f"FDA Product Classification (product_code: {product_code})"
                if dev.get("submission_number"):
                    k = dev["submission_number"]
                    prefix = k[1:3] if k.upper().startswith("K") and len(k) >= 3 else ""
                    if prefix.isdigit():
                        indications_source += f"; FDA 510(k) Summary https://www.accessdata.fda.gov/cdrh_docs/pdf{prefix}/{k}.pdf"
            else:
                indications_source = "Grok inference from device trade name only"

            indications_text = build_indications_text(disease_states_raw)

            # Resolve disease state IDs (in confidence order)
            sorted_ds = sorted(disease_states_raw, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("confidence", "low"), 2))
            ds_ids = []
            for ds in sorted_ds:
                name = (ds.get("name") or "").strip()
                if not name:
                    continue
                try:
                    ds_id = ds_cache.get_or_create(name)
                    if ds_id not in ds_ids:
                        ds_ids.append(ds_id)
                except Exception as e:
                    print(f"[W{WORKER_ID}] DS create error for '{name}': {e}")

            # Update approvals for all countries this device appears in
            if ds_ids:
                try:
                    update_approvals_with_disease_states(dev_id, ds_ids, ds_cache)
                except Exception as e:
                    print(f"[W{WORKER_ID}] Approval update error for {dev_id}: {e}")

            # Update device record
            try:
                rest_patch(
                    "deviceatlas_devices", f"id=eq.{dev_id}",
                    {
                        "description": description or None,
                        "indications_text": indications_text or None,
                        "indications_source": indications_source,
                        "enrichment_method": enrichment_method,
                        "enrichment_confidence": confidence,
                        "updated_at": "now()",
                    }
                )
            except Exception as e:
                print(f"[W{WORKER_ID}] Device patch error for {dev_id}: {e}")

        total_done += len(devices)
        print(
            f"[W{WORKER_ID}] batch={batch_num} cursor={cursor[:8]}... "
            f"✓ +{len(devices)} (total={total_done})"
        )

    # Final count
    counts = mgmt_query(
        "SELECT enrichment_method, COUNT(*) as cnt "
        "FROM deviceatlas_devices GROUP BY enrichment_method ORDER BY cnt DESC;"
    )
    print("\n" + "=" * 62)
    print("ENRICHMENT COMPLETE")
    for r in counts:
        print(f"  {r['enrichment_method'] or 'null':30s} {r['cnt']}")
    print("=" * 62)


if __name__ == "__main__":
    main()
