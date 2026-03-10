#!/usr/bin/env python3
"""
Enrich HC-only devices (country=CA, disease_state_id=null) with:
1. Description of what the device does
2. Disease states it treats (matched to existing deviceatlas_disease_states)

For each batch of devices:
- Ask GPT-4o for description + 1-3 disease states
(NOTE: original run used Grok/xAI; switched to GPT-4o on 2026-03-10)
- Match disease states to existing DB records (fuzzy by name)
- Create new disease states if genuinely novel
- Update device description
- Update/split approval records to link real disease_state_ids

Usage:
  python3 enrich-hc-devices.py 0   # even-UUID devices
  python3 enrich-hc-devices.py 1   # odd-UUID devices
"""

import os, json, sys, time, uuid, urllib.request, urllib.error
from difflib import SequenceMatcher

SUPABASE_URL      = os.environ["SUPABASE_URL"]
SERVICE_KEY       = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
PROJECT_REF       = os.environ["SUPABASE_PROJECT_REF"]
OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]  # switched from GROK_API_KEY on 2026-03-10
MGMT_TOKEN_FILE   = "/tmp/mgmt_token.txt"

WORKER = sys.argv[1] if len(sys.argv) > 1 else "0"
PARITY = int(WORKER) % 2
BATCH  = 20

EVEN_DIGITS = "('0','2','4','6','8','a','c','e')"
ODD_DIGITS  = "('1','3','5','7','9','b','d','f')"
PARITY_FILTER = f"AND right(d.id::text, 1) IN {EVEN_DIGITS if PARITY == 0 else ODD_DIGITS}"


def get_mgmt_token() -> str:
    try:
        with open(MGMT_TOKEN_FILE) as f:
            t = f.read().strip()
            if t: return t
    except FileNotFoundError:
        pass
    return os.environ.get("SUPABASE_MGMT_TOKEN", "")


def mgmt_query(sql: str) -> list:
    url = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"
    req = urllib.request.Request(url, data=json.dumps({"query": sql}).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {get_mgmt_token()}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "curl/7.81.0")
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())
        if isinstance(result, dict) and result.get("message"):
            raise RuntimeError(f"MGMT error: {result['message']}")
        return result if isinstance(result, list) else []


def rest_post(path: str, data: list) -> int:
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=payload, method="POST",
        headers={
            "apikey": SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
            "User-Agent": "curl/7.81.0",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def rest_patch(path: str, params: dict, data: dict) -> int:
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}?{qs}",
        data=payload, method="PATCH",
        headers={
            "apikey": SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
            "User-Agent": "curl/7.81.0",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def gpt(prompt: str, system: str = "Medical device expert. Return ONLY valid JSON, no markdown.") -> str:
    url = "https://api.openai.com/v1/chat/completions"
    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.15,
        "max_tokens": 4000,
    }).encode()
    for attempt in range(8):
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {OPENAI_API_KEY}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 60 * (attempt + 1)
                print(f"[W{WORKER}] GPT 429 — sleeping {wait}s", flush=True)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("GPT exhausted retries")


def load_all_disease_states() -> dict:
    """Load all disease states from DB as {normalized_name: id}."""
    rows = mgmt_query("SELECT id, name FROM deviceatlas_disease_states ORDER BY name;")
    result = {}
    for r in rows:
        norm = r["name"].lower().strip()
        result[norm] = r["id"]
    return result


def find_or_create_disease_state(name: str, ds_map: dict) -> str | None:
    """Match disease state name to existing record or create new one."""
    if not name:
        return None
    norm = name.lower().strip()

    # Exact match
    if norm in ds_map:
        return ds_map[norm]

    # Fuzzy match (threshold 0.82)
    best_score = 0.0
    best_id = None
    for existing_norm, did in ds_map.items():
        score = SequenceMatcher(None, norm, existing_norm).ratio()
        if score > best_score:
            best_score = score
            best_id = did

    if best_score >= 0.82 and best_id:
        return best_id

    # Create new disease state
    new_id = str(uuid.uuid4())
    try:
        rest_post("deviceatlas_disease_states", [{"id": new_id, "name": name.title(), "description": ""}])
        ds_map[norm] = new_id
        print(f"[W{WORKER}]   + New disease state: {name.title()}", flush=True)
        return new_id
    except Exception as e:
        print(f"[W{WORKER}]   ! Failed to create disease state '{name}': {e}", flush=True)
        return None


def fetch_batch(after_id: str) -> list:
    """Fetch BATCH HC-only devices with null disease_state_id."""
    id_filter = f"AND d.id > '{after_id}'" if after_id else ""
    sql = f"""
        SELECT DISTINCT d.id, d.name, d.manufacturer, d.description, a.id as approval_id, a.source_ref, a.approval_date
        FROM deviceatlas_devices d
        JOIN deviceatlas_approvals a ON a.device_id = d.id
        WHERE a.country = 'CA'
          AND a.disease_state_id IS NULL
          {PARITY_FILTER}
          {id_filter}
        ORDER BY d.id
        LIMIT {BATCH};
    """
    return mgmt_query(sql)


def enrich_batch(devices: list, ds_map: dict) -> int:
    """Ask GPT-4o to enrich a batch of devices, update DB."""
    summaries = []
    for d in devices:
        summaries.append({
            "id": d["id"],
            "name": d["name"],
            "manufacturer": d.get("manufacturer", "Unknown") or "Unknown",
        })

    prompt = f"""Given these {len(summaries)} medical devices (Health Canada licensed), for each provide:
1. description: 1-2 clear sentences explaining what the device does and what medical condition it treats. Be specific (NOT generic). Patient-friendly language.
2. disease_states: array of 1-3 disease states or medical conditions this device treats/diagnoses/monitors. Use standard medical terminology.

Devices:
{json.dumps(summaries, indent=2)}

Return a JSON array with exactly {len(summaries)} objects, preserving the "id" field:
[{{"id":"...","description":"...","disease_states":["condition 1","condition 2"]}}]"""

    try:
        raw = gpt(prompt)
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        items = json.loads(raw)
        if not isinstance(items, list):
            items = list(items.values()) if isinstance(items, dict) else []
    except Exception as e:
        print(f"[W{WORKER}] GPT parse error: {e}", flush=True)
        return 0

    updated = 0
    for item in items:
        dev_id = item.get("id")
        desc = (item.get("description") or "").strip()
        disease_names = item.get("disease_states") or []

        if not dev_id:
            continue

        # Find the matching device record
        device = next((d for d in devices if d["id"] == dev_id), None)
        if not device:
            continue

        approval_id = device["approval_id"]

        # Update device description if missing or short
        existing_desc = (device.get("description") or "").strip()
        if desc and len(desc) > 40 and (not existing_desc or len(existing_desc) < 40):
            try:
                rest_patch("deviceatlas_devices", {"id": f"eq.{dev_id}"}, {"description": desc[:500]})
            except Exception as e:
                print(f"[W{WORKER}]   ! desc update failed: {e}", flush=True)

        # Resolve disease states
        ds_ids = []
        for ds_name in disease_names[:3]:
            ds_id = find_or_create_disease_state(ds_name, ds_map)
            if ds_id and ds_id not in ds_ids:
                ds_ids.append(ds_id)

        if not ds_ids:
            continue

        # Update existing null approval with first disease state
        try:
            rest_patch(
                "deviceatlas_approvals",
                {"id": f"eq.{approval_id}"},
                {"disease_state_id": ds_ids[0]}
            )
        except Exception as e:
            print(f"[W{WORKER}]   ! approval update failed: {e}", flush=True)
            continue

        # Insert additional approvals for extra disease states
        if len(ds_ids) > 1:
            extra = []
            for ds_id in ds_ids[1:]:
                extra.append({
                    "device_id": dev_id,
                    "disease_state_id": ds_id,
                    "country": "CA",
                    "status": "Approved",
                    "approval_date": device.get("approval_date"),
                    "source_ref": device.get("source_ref"),
                    "is_active": True,
                })
            try:
                rest_post("deviceatlas_approvals", extra)
            except Exception as e:
                print(f"[W{WORKER}]   ! extra approvals insert failed: {e}", flush=True)

        updated += 1

    return updated


def main():
    print(f"[W{WORKER}] HC device enricher started (parity={PARITY})", flush=True)

    # Load all disease states into memory
    ds_map = load_all_disease_states()
    print(f"[W{WORKER}] Loaded {len(ds_map)} existing disease states", flush=True)

    cursor = ""
    total = 0
    batch_num = 0

    while True:
        devices = fetch_batch(cursor)
        if not devices:
            print(f"[W{WORKER}] No more devices. Total enriched: {total}", flush=True)
            break

        batch_num += 1
        n = enrich_batch(devices, ds_map)
        total += n
        cursor = devices[-1]["id"]

        print(f"[W{WORKER}] batch={batch_num} cursor={cursor[:8]}... ✓ +{n} (total={total})", flush=True)

        # Small delay to avoid GPT rate limits
        time.sleep(1)


if __name__ == "__main__":
    main()
