#!/usr/bin/env python3
"""
Parallel re-enrichment — worker handles a slice of devices by offset range.
Usage: python3 reenrich-parallel.py <start_offset> <end_offset>
"""
import os, json, sys, time, urllib.request, urllib.error

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_PROJECT_REF = os.environ["SUPABASE_PROJECT_REF"]
SUPABASE_MGMT_TOKEN = os.environ["SUPABASE_MGMT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

CATEGORIES = [
    "Cardiovascular", "Neurology", "Ophthalmology", "Radiology/Imaging",
    "Dental", "Gastroenterology", "Diagnostics", "Obstetrics/Gynecology",
    "General Surgery", "ENT", "Immunology", "Hematology", "Endocrinology",
    "Anesthesiology", "Orthopedic", "Physical Medicine", "Urology",
    "Dermatology", "Pulmonology",
]

START = int(sys.argv[1]) if len(sys.argv) > 1 else 0
END = int(sys.argv[2]) if len(sys.argv) > 2 else 9999
WORKER = sys.argv[3] if len(sys.argv) > 3 else "0"
BATCH = 25

def grok(prompt: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Medical device expert. Return ONLY valid JSON array, no markdown, no explanation."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.15,
        "max_tokens": 6000,
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {OPENAI_API_KEY}")
    req.add_header("Content-Type", "application/json")
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
    except Exception as e:
        print(f"[W{WORKER}] SQL err: {e}", flush=True)
        return []

def patch(device_id: str, updates: dict) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/deviceatlas_devices?id=eq.{device_id}"
    req = urllib.request.Request(url, data=json.dumps(updates).encode(), method="PATCH")
    req.add_header("apikey", SUPABASE_SERVICE_ROLE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_ROLE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return True
    except Exception as e:
        return False

def fetch_slice(offset: int, limit: int) -> list:
    return mgmt_query(f"""
        SELECT id, name, manufacturer
        FROM deviceatlas_devices
        WHERE (description IS NULL OR description LIKE '%FDA-cleared%' OR LENGTH(description) < 40)
        AND is_active = true
        ORDER BY name
        LIMIT {limit} OFFSET {offset}
    """)

def enrich(devices: list) -> list:
    items = [{"id": d["id"], "name": d["name"][:80], "mfr": (d.get("manufacturer") or "")[:50]} for d in devices]
    prompt = f"""You are a medical device regulatory expert. For each device below, provide:
1. A clear 1-2 sentence description of what the device does and what medical condition it treats (patient-friendly, specific — NOT generic like "FDA-cleared device")
2. The single best category from this exact list: {json.dumps(CATEGORIES)}

Devices:
{json.dumps(items, indent=1)}

Return ONLY a JSON array (same order, {len(items)} items):
[{{"id":"...","description":"...","category":"..."}}]"""

    raw = grok(prompt)
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() in ("```", "```json") else lines[1:])
    return json.loads(raw)

def main():
    print(f"[W{WORKER}] Starting — offsets {START}–{END}", flush=True)
    processed = 0
    offset = START

    while offset < END:
        batch = fetch_slice(offset, BATCH)
        if not batch:
            break

        try:
            enriched = enrich(batch)
            for item in enriched:
                if not item.get("id"):
                    continue
                updates = {}
                desc = (item.get("description") or "").strip()
                cat = (item.get("category") or "").strip()
                if desc and "FDA-cleared" not in desc and len(desc) > 20:
                    updates["description"] = desc[:500]
                if cat in CATEGORIES:
                    updates["category"] = cat
                if updates:
                    patch(item["id"], updates)
                    processed += 1

            print(f"[W{WORKER}] offset={offset} ✓ +{len(enriched)} (total={processed})", flush=True)
        except Exception as e:
            print(f"[W{WORKER}] offset={offset} ERR: {e}", flush=True)
            time.sleep(10)

        offset += BATCH
        time.sleep(2)

    print(f"[W{WORKER}] Done — updated {processed} devices", flush=True)

if __name__ == "__main__":
    main()
