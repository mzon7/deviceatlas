#!/usr/bin/env python3
"""
DeviceAtlas — Structured Disease State & Description Enrichment

Pipeline:
─────────────────────────────────────────────────────────────────
For FDA devices (have product_code):
  1. Look up FDA Product Classification cache → generic_name, specialty,
     device_class, regulation_number
  2. Grok gets this structured context → disease states + description
  enrichment_method = "fda_classification", confidence = high/medium

For non-FDA devices (HC-only, EU-only — no product_code):
  1. Grok gets: device trade name + device_class (HC I-IV / EUDAMED risk class)
  2. System prompt instructs Grok to use FDA disease taxonomy terms for
     disease state names → ensures cross-country consistency
  enrichment_method = "grok_inferred", confidence = low/medium based on
  how specific the device name is

All disease states created are matched/created in deviceatlas_disease_states
using the same normalized names → HC and EU approvals share identical
disease state records with FDA approvals for the same type of device.

Each device gets one approval row per (country × disease_state), so a device
approved in US, CA, EU for 2 indications gets 6 approval rows total.

Usage:
  nohup python3 -u enrich-structured.py 0 > /tmp/enrich-s0.log 2>&1 &
  nohup python3 -u enrich-structured.py 1 > /tmp/enrich-s1.log 2>&1 &
"""

import json, os, re, sys, time, threading, urllib.request, urllib.error, uuid
from difflib import SequenceMatcher

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL   = os.environ["SUPABASE_URL"]
SERVICE_KEY    = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
PROJECT_REF    = os.environ["SUPABASE_PROJECT_REF"]
GROK_API_KEY   = os.environ["GROK_API_KEY"]

WORKER_ID      = int(sys.argv[1]) if len(sys.argv) > 1 else 0
BATCH          = 25
GROK_MODEL     = "grok-4-1-fast-non-reasoning"
GROK_ENDPOINT  = "https://api.x.ai/v1/chat/completions"
FDA_CLASS_CACHE = "/tmp/fda_class_cache.json"
MGMT_TOKEN_FILE = "/tmp/mgmt_token.txt"

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

def rest_post(path: str, data) -> None:
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

# ── FDA Product Code Classification Cache ────────────────────────────────────
def fetch_fda_classification(product_code: str) -> dict | None:
    url = f"https://api.fda.gov/device/classification.json?search=product_code:{product_code}&limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.81.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
            if "results" not in d:
                return None
            rec = d["results"][0]
            return {
                "generic_name": rec.get("device_name", "") or "",
                "specialty": rec.get("medical_specialty_description", "") or "",
                "device_class": rec.get("device_class", "") or "",
                "regulation_number": rec.get("regulation_number", "") or "",
                "definition": (rec.get("definition", "") or "")[:500],
            }
    except Exception:
        return None

def build_fda_class_cache(product_codes: list) -> dict:
    if os.path.exists(FDA_CLASS_CACHE):
        with open(FDA_CLASS_CACHE) as f:
            cache = json.load(f)
        missing = [c for c in product_codes if c not in cache]
        if missing:
            print(f"[W{WORKER_ID}] Fetching {len(missing)} missing product codes...")
            for i, code in enumerate(missing):
                cache[code] = fetch_fda_classification(code)
                if (i + 1) % 200 == 0:
                    print(f"[W{WORKER_ID}]   {i+1}/{len(missing)} codes...")
                    with open(FDA_CLASS_CACHE, "w") as f:
                        json.dump(cache, f)
                time.sleep(0.05)
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
        time.sleep(0.05)
    with open(FDA_CLASS_CACHE, "w") as f:
        json.dump(cache, f)
    print(f"[W{WORKER_ID}] FDA cache complete: {len(cache)} entries")
    return cache

# ── Grok enrichment ───────────────────────────────────────────────────────────
FDA_SYSTEM_PROMPT = """You are a medical device classification expert with deep knowledge of
FDA regulatory taxonomy and global medical device categories.

Given FDA structured data about a medical device, return a JSON object with:
- "description": 2-3 sentence clinical description for healthcare professionals.
  Ground in the FDA classification data (generic name and specialty).
- "disease_states": list of objects {name, confidence} for medical conditions
  this device diagnoses, treats, or monitors. Use standard FDA medical terminology.
  confidence: "high" = definitively established for this FDA device type,
  "medium" = likely, "low" = inferred. Limit to 1-4. Return [] if unclear.
- "enrichment_method": "fda_classification"

Return ONLY the JSON object."""

NON_FDA_SYSTEM_PROMPT = """You are a medical device classification expert.

Given a medical device from Health Canada, EUDAMED (EU), or MHRA (UK), classify
its disease states and write a clinical description. IMPORTANT:

1. Use the SAME disease state names and FDA medical terminology that the US FDA uses
   in its device classification system. This ensures cross-country consistency so that
   the same disease states link Canadian, European, and US approved devices.

2. Use the FDA Medical Specialty categories where applicable:
   Cardiovascular, Orthopedic, Neurology, Radiology, General Hospital,
   General Surgery, Dental, Ophthalmology, Ear, Nose & Throat, Gastroenterology,
   Endocrinology, Hematology, Immunology, Anesthesiology, Physical Medicine, etc.

Return a JSON object with:
- "description": 2-3 sentence clinical description.
- "disease_states": list of {name, confidence}. Use standard disease names
  (e.g. "Type 2 Diabetes Mellitus", "Hypertension", "Osteoarthritis of the Knee").
  confidence: "high" if the device name clearly indicates the indication,
  "medium" if likely, "low" if inferred. Limit 1-4. Return [] if genuinely unclear.
- "enrichment_method": "grok_inferred"

Return ONLY the JSON object."""

def grok_enrich_fda(device_name: str, classification: dict) -> dict | None:
    context = (
        f"Trade name: {device_name}\n"
        f"FDA generic name: {classification['generic_name']}\n"
        f"FDA medical specialty: {classification['specialty']}\n"
        f"FDA device class: {classification['device_class']}\n"
        f"FDA regulation: {classification.get('regulation_number','')}\n"
    )
    if classification.get("definition"):
        context += f"FDA definition: {classification['definition']}\n"
    return _grok_call(FDA_SYSTEM_PROMPT, context)

def grok_enrich_non_fda(device_name: str, device_class: str | None,
                        country_origin: str) -> dict | None:
    class_label = ""
    if device_class:
        class_label = f"\nDevice risk class: {device_class}"
    context = (
        f"Device trade name: {device_name}\n"
        f"Regulatory origin: {country_origin}{class_label}\n"
        f"(No FDA product code — classify using FDA disease taxonomy for consistency)"
    )
    return _grok_call(NON_FDA_SYSTEM_PROMPT, context)

def _grok_call(system: str, user: str) -> dict | None:
    payload = json.dumps({
        "model": GROK_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
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
        except (json.JSONDecodeError, KeyError):
            if attempt < 4:
                time.sleep(5)
                continue
            return None
    return None

# ── Disease State Cache ───────────────────────────────────────────────────────
def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

class DiseaseStateCache:
    def __init__(self):
        self._cache: dict[str, str] = {}
        self._lock = threading.Lock()
        rows = mgmt_query("SELECT id, name FROM deviceatlas_disease_states;")
        for r in rows:
            self._cache[normalize(r["name"])] = r["id"]

    def get_or_create(self, name: str) -> str:
        norm = normalize(name)
        with self._lock:
            if norm in self._cache:
                return self._cache[norm]
            best_score, best_id = 0.0, None
            for cand_norm, cand_id in self._cache.items():
                s = SequenceMatcher(None, norm, cand_norm).ratio()
                if s > best_score:
                    best_score, best_id = s, cand_id
            if best_score >= 0.85 and best_id:
                self._cache[norm] = best_id
                return best_id
            new_id = str(uuid.uuid4())
            rest_post("deviceatlas_disease_states", {"id": new_id, "name": name.strip().title()})
            self._cache[norm] = new_id
            return new_id

# ── Approval Row Helpers ──────────────────────────────────────────────────────
def update_approvals_with_disease_states(device_id: str, ds_ids: list) -> None:
    """One approval row per (country × disease_state), preserving source_ref/date."""
    existing = rest_get(
        "deviceatlas_approvals",
        f"device_id=eq.{device_id}&select=id,country,source_ref,approval_date,status,is_active",
    )
    if not existing or not ds_ids:
        return

    by_country: dict[str, list] = {}
    for row in existing:
        by_country.setdefault(row["country"], []).append(row)

    for country, rows in by_country.items():
        primary = rows[0]
        ids_csv = ",".join(r["id"] for r in rows)
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

# ── Infer regulatory origin from device columns ───────────────────────────────
def infer_origin(dev: dict) -> str:
    ct = dev.get("clearance_type") or ""
    if ct:
        return "FDA (USA)"
    cl = dev.get("device_class") or ""
    # HC classes are Roman numerals I-IV; EUDAMED uses "Class I/IIa/IIb/III/IV"
    if cl.startswith("Class"):
        return "EU (EUDAMED)"
    if cl in ("1", "2", "3", "4"):
        return "Health Canada"
    return "International"

def build_indications_text(disease_states: list) -> str:
    if not disease_states:
        return ""
    return "; ".join(f"{d['name']} [{d.get('confidence','medium')}]" for d in disease_states)

# ── Main Loop ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 66)
    print(f"DeviceAtlas — Structured Enrichment — Worker {WORKER_ID}")
    print("=" * 66)

    ds_cache = DiseaseStateCache()
    print(f"[W{WORKER_ID}] Disease states loaded: {len(ds_cache._cache)}")

    # Get unique product codes for FDA cache
    rows = mgmt_query("SELECT DISTINCT product_code FROM deviceatlas_devices WHERE product_code IS NOT NULL;")
    all_codes = [r["product_code"] for r in rows if r.get("product_code")]
    print(f"[W{WORKER_ID}] Unique FDA product codes: {len(all_codes)}")

    # Worker 0 builds cache; worker 1 waits then picks up missing
    if WORKER_ID == 0:
        fda_cache = build_fda_class_cache(all_codes)
    else:
        waited = 0
        while not os.path.exists(FDA_CLASS_CACHE) and waited < 3600:
            print(f"[W{WORKER_ID}] Waiting for FDA class cache from worker 0... ({waited}s)")
            time.sleep(30)
            waited += 30
        fda_cache = build_fda_class_cache(all_codes)

    print(f"[W{WORKER_ID}] FDA classification cache ready: {len(fda_cache)} entries")
    print(f"[W{WORKER_ID}] Starting enrichment loop...")

    cursor = "00000000-0000-0000-0000-000000000000"
    total_done = fda_count = non_fda_count = 0

    while True:
        sql = f"""
            SELECT d.id, d.name, d.product_code, d.submission_number,
                   d.clearance_type, d.device_class, d.manufacturer
            FROM deviceatlas_devices d
            WHERE d.id > '{cursor}'
              AND d.enrichment_method IS NULL
              AND get_byte(decode(replace(d.id::text, '-', ''), 'hex'), 15) % 2 = {WORKER_ID}
            ORDER BY d.id
            LIMIT {BATCH};
        """
        devices = mgmt_query(sql)
        if not devices:
            print(f"[W{WORKER_ID}] No more un-enriched devices — done!")
            break

        cursor = devices[-1]["id"]
        batch_num = total_done // BATCH + 1

        for dev in devices:
            dev_id = dev["id"]
            dev_name = dev.get("name") or ""
            product_code = dev.get("product_code")

            # ── Enrich based on data availability ────────────────────────────
            if product_code:
                # FDA device — use structured classification
                classification = fda_cache.get(product_code)
                if classification and (classification.get("generic_name") or classification.get("specialty")):
                    result = grok_enrich_fda(dev_name, classification)
                    final_method = "fda_classification"
                    k = dev.get("submission_number", "")
                    source = f"FDA Product Classification (code: {product_code}, generic: '{classification['generic_name']}')"
                    if k and k.upper().startswith("K") and len(k) >= 3 and k[1:3].isdigit():
                        source += f"; 510(k) https://www.accessdata.fda.gov/cdrh_docs/pdf{k[1:3]}/{k}.pdf"
                    fda_count += 1
                else:
                    # product_code known but no classification data → fall back to inference
                    origin = infer_origin(dev)
                    result = grok_enrich_non_fda(dev_name, dev.get("device_class"), origin)
                    final_method = "grok_inferred"
                    source = f"FDA product_code {product_code} (no classification data); trade name inference using FDA taxonomy"
                    non_fda_count += 1
            else:
                # Non-FDA device (HC-only, EU-only) — infer using FDA taxonomy
                origin = infer_origin(dev)
                device_class = dev.get("device_class")
                result = grok_enrich_non_fda(dev_name, device_class, origin)
                final_method = "grok_inferred"
                class_info = f", device class {device_class}" if device_class else ""
                source = (
                    f"Inferred from {origin} device trade name{class_info}. "
                    f"Disease states aligned to FDA medical taxonomy for cross-country consistency."
                )
                non_fda_count += 1

            if not result:
                rest_patch("deviceatlas_devices", f"id=eq.{dev_id}",
                           {"enrichment_method": "not_enriched", "enrichment_confidence": "low",
                            "updated_at": "now()"})
                continue

            description = result.get("description", "")
            disease_states_raw = result.get("disease_states", [])

            # Confidence: high if FDA data + high confidence DSs, else medium/low
            if final_method == "fda_classification":
                confidence = "high" if any(d.get("confidence") == "high" for d in disease_states_raw) else "medium"
            elif disease_states_raw and any(d.get("confidence") in ("high", "medium") for d in disease_states_raw):
                confidence = "medium"
            else:
                confidence = "low"

            indications_text = build_indications_text(disease_states_raw)

            # Resolve / create disease state IDs (primary indication first)
            sorted_ds = sorted(disease_states_raw,
                               key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("confidence", "low"), 2))
            ds_ids: list[str] = []
            for ds in sorted_ds:
                name = (ds.get("name") or "").strip()
                if not name:
                    continue
                try:
                    ds_id = ds_cache.get_or_create(name)
                    if ds_id not in ds_ids:
                        ds_ids.append(ds_id)
                except Exception as e:
                    print(f"[W{WORKER_ID}] DS err '{name}': {e}")

            if ds_ids:
                try:
                    update_approvals_with_disease_states(dev_id, ds_ids)
                except Exception as e:
                    print(f"[W{WORKER_ID}] Approval update err {dev_id}: {e}")

            try:
                rest_patch("deviceatlas_devices", f"id=eq.{dev_id}", {
                    "description": description or None,
                    "indications_text": indications_text or None,
                    "indications_source": source,
                    "enrichment_method": final_method,
                    "enrichment_confidence": confidence,
                    "updated_at": "now()",
                })
            except Exception as e:
                print(f"[W{WORKER_ID}] Device patch err {dev_id}: {e}")

        total_done += len(devices)
        print(
            f"[W{WORKER_ID}] batch={batch_num} cursor={cursor[:8]}... "
            f"✓ +{len(devices)} total={total_done} "
            f"[fda={fda_count} inferred={non_fda_count}]"
        )

    # Final stats
    counts = mgmt_query(
        "SELECT enrichment_method, COUNT(*) as cnt "
        "FROM deviceatlas_devices GROUP BY enrichment_method ORDER BY cnt DESC;"
    )
    print("\n" + "=" * 66)
    print(f"WORKER {WORKER_ID} COMPLETE")
    for r in counts:
        print(f"  {(r['enrichment_method'] or 'null'):28s} {r['cnt']}")
    print("=" * 66)


if __name__ == "__main__":
    main()
