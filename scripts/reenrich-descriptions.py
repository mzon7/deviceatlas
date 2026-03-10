#!/usr/bin/env python3
"""
Re-enrich devices that have generic/missing descriptions.
Processes in batches of 20, asking GPT-4o for proper descriptions and correct categories.
(NOTE: original run used Grok/xAI; switched to GPT-4o on 2026-03-10)
"""
import os, json, time, urllib.request, urllib.error

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_PROJECT_REF = os.environ["SUPABASE_PROJECT_REF"]
SUPABASE_MGMT_TOKEN = os.environ["SUPABASE_MGMT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]  # switched from GROK_API_KEY on 2026-03-10

CATEGORIES = [
    "Cardiovascular", "Neurology", "Ophthalmology", "Radiology/Imaging",
    "Dental", "Gastroenterology", "Diagnostics", "Obstetrics/Gynecology",
    "General Surgery", "ENT", "Immunology", "Hematology", "Endocrinology",
    "Anesthesiology", "Orthopedic", "Physical Medicine", "Urology",
    "Dermatology", "Pulmonology",
]

def gpt(prompt: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are a medical device expert. Return ONLY valid JSON, no markdown."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
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
        print(f"  SQL err: {e}")
        return []

def rest_patch(device_id: str, updates: dict) -> bool:
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
        print(f"  Patch err: {e}")
        return False

def fetch_batch(offset: int, limit: int) -> list:
    """Fetch devices with poor descriptions."""
    return mgmt_query(f"""
        SELECT id, name, manufacturer, category
        FROM deviceatlas_devices
        WHERE (
            description IS NULL
            OR description = ''
            OR description LIKE '%FDA-cleared Class II%'
            OR LENGTH(description) < 40
        )
        AND is_active = true
        ORDER BY name
        LIMIT {limit} OFFSET {offset}
    """)

def enrich_batch(devices: list) -> list:
    items = [{"id": d["id"], "name": d["name"], "manufacturer": d.get("manufacturer", ""), "category": d.get("category", "")} for d in devices]
    prompt = f"""For each of these {len(items)} medical devices, generate:
1. A clear 2-sentence description of what the device is and what medical problem it treats (for patients, be specific)
2. The correct medical category from this list: {json.dumps(CATEGORIES)}

Devices:
{json.dumps(items, indent=2)}

Return a JSON array with one object per device, same order:
[{{"id": "...", "description": "...", "category": "..."}}]

Rules:
- If the device name is unclear or seems like lab/industrial equipment, set category to "Diagnostics" or "General Surgery"
- Descriptions must be genuinely informative, NOT "FDA-cleared Class II medical device"
- Each description should be 1-3 sentences, patient-friendly
- Return ONLY the JSON array"""

    raw = gpt(prompt)
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(raw)

def main():
    print("=== Description Re-Enricher ===\n")

    # Count total to fix
    total_rows = mgmt_query("""
        SELECT COUNT(*) as c FROM deviceatlas_devices
        WHERE (description IS NULL OR description = '' OR description LIKE '%FDA-cleared Class II%' OR LENGTH(description) < 40)
        AND is_active = true
    """)
    total = int(total_rows[0]["c"]) if total_rows else 0
    print(f"Devices needing re-enrichment: {total}")

    BATCH = 20
    processed = 0
    failed = 0
    offset = 0

    while offset < total:
        batch = fetch_batch(offset, BATCH)
        if not batch:
            break

        print(f"\n[{offset+1}-{offset+len(batch)}/{total}] Enriching {len(batch)} devices...")
        try:
            enriched = enrich_batch(batch)
            for item in enriched:
                if not item.get("id"):
                    continue
                updates = {}
                if item.get("description") and "FDA-cleared" not in item["description"]:
                    updates["description"] = item["description"]
                if item.get("category") and item["category"] in CATEGORIES:
                    updates["category"] = item["category"]
                if updates:
                    if rest_patch(item["id"], updates):
                        processed += 1
                    else:
                        failed += 1
            print(f"  ✓ Updated {len(enriched)} devices (total: {processed})")
            time.sleep(1)
        except json.JSONDecodeError as e:
            print(f"  JSON error: {e} — skipping batch")
            failed += len(batch)
        except Exception as e:
            print(f"  Error: {e} — skipping batch")
            failed += len(batch)
            time.sleep(2)

        offset += BATCH

    print(f"\n✓ Done! Updated: {processed}, Failed: {failed}")

if __name__ == "__main__":
    main()
