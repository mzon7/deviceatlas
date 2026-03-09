#!/usr/bin/env python3
"""
Parallel re-enrichment — cursor-based pagination, 2 workers split by ID parity.
Usage:
  python3 reenrich-parallel.py 0   # even IDs (worker 0)
  python3 reenrich-parallel.py 1   # odd IDs  (worker 1)

Changes vs original:
- Cursor pagination (WHERE id > last_id) instead of OFFSET — not affected by shrinking result set
- ID-parity sharding instead of offset ranges — stable split even as rows are enriched
- MGMT API for fetch (supports LENGTH filter) with 403/error logging that exits clearly
- Grok 429 exponential backoff: 60s, 120s, 180s... up to 8 attempts
- Only 2 workers to stay under Grok rate limits
"""
import os, json, sys, time, urllib.request, urllib.error

SUPABASE_URL       = os.environ["SUPABASE_URL"]
SERVICE_KEY        = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
PROJECT_REF        = os.environ["SUPABASE_PROJECT_REF"]
GROK_API_KEY       = os.environ["GROK_API_KEY"]
# MGMT_TOKEN is read dynamically from file so it can be refreshed without restarting workers.
# Update /tmp/mgmt_token.txt at the start of each new conversation session.
MGMT_TOKEN_FILE    = "/tmp/mgmt_token.txt"

def get_mgmt_token() -> str:
    try:
        with open(MGMT_TOKEN_FILE) as f:
            token = f.read().strip()
            if token:
                return token
    except FileNotFoundError:
        pass
    # Fallback to env var
    return os.environ.get("SUPABASE_MGMT_TOKEN", "")

CATEGORIES = [
    "Cardiovascular", "Neurology", "Ophthalmology", "Radiology/Imaging",
    "Dental", "Gastroenterology", "Diagnostics", "Obstetrics/Gynecology",
    "General Surgery", "ENT", "Immunology", "Hematology", "Endocrinology",
    "Anesthesiology", "Orthopedic", "Physical Medicine", "Urology",
    "Dermatology", "Pulmonology",
]

WORKER = sys.argv[1] if len(sys.argv) > 1 else "0"  # "0" or "1"
PARITY = int(WORKER) % 2                              # 0 = even UUIDs, 1 = odd
BATCH  = 25


def grok(prompt: str) -> str:
    url = "https://api.x.ai/v1/chat/completions"
    payload = json.dumps({
        "model": "grok-4-1-fast-non-reasoning",
        "messages": [
            {"role": "system", "content": "Medical device expert. Return ONLY valid JSON array, no markdown, no explanation."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.15,
        "max_tokens": 6000,
    }).encode()
    for attempt in range(8):
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {GROK_API_KEY}")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "curl/7.81.0")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 60 * (attempt + 1)
                print(f"[W{WORKER}] Grok 429 — sleeping {wait}s (attempt {attempt+1}/8)", flush=True)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Grok rate limit: exhausted all retries")


def mgmt_query(sql: str) -> list:
    url = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"
    req = urllib.request.Request(url, data=json.dumps({"query": sql}).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {get_mgmt_token()}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "curl/7.81.0")
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())
        if isinstance(result, dict) and result.get("message"):
            raise RuntimeError(f"MGMT API error: {result['message']}")
        return result if isinstance(result, list) else []


def fetch_batch(after_id: str) -> list:
    """Cursor-based: fetch BATCH devices with bad/missing description after given ID."""
    id_filter = f"AND id > '{after_id}'" if after_id else ""
    # Parity filter: split by last hex digit of UUID (even=0,2,4,6,8,a,c,e / odd=1,3,5,7,9,b,d,f)
    even_digits = "('0','2','4','6','8','a','c','e')"
    odd_digits  = "('1','3','5','7','9','b','d','f')"
    parity_filter = f"AND right(id::text, 1) IN {even_digits if PARITY == 0 else odd_digits}"
    sql = f"""
        SELECT id, name, manufacturer
        FROM deviceatlas_devices
        WHERE (description IS NULL OR description LIKE '%FDA-cleared%' OR LENGTH(description) < 40)
        AND is_active = true
        {id_filter}
        {parity_filter}
        ORDER BY id
        LIMIT {BATCH}
    """
    return mgmt_query(sql)


def patch(device_id: str, updates: dict) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/deviceatlas_devices?id=eq.{device_id}"
    req = urllib.request.Request(url, data=json.dumps(updates).encode(), method="PATCH")
    req.add_header("apikey", SERVICE_KEY)
    req.add_header("Authorization", f"Bearer {SERVICE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return True
    except Exception as e:
        print(f"[W{WORKER}] patch err for {device_id}: {e}", flush=True)
        return False


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
    print(f"[W{WORKER}] Starting — parity={'even' if PARITY==0 else 'odd'} UUIDs, cursor mode", flush=True)
    processed = 0
    batches = 0
    last_id = ""
    consecutive_errors = 0

    while True:
        try:
            batch = fetch_batch(last_id)
        except urllib.error.HTTPError as e:
            print(f"[W{WORKER}] MGMT API HTTP {e.code} — {e}", flush=True)
            if e.code == 403:
                print(f"[W{WORKER}] FATAL: MGMT token expired or invalid. Restart script with fresh session.", flush=True)
                break
            consecutive_errors += 1
            if consecutive_errors >= 5:
                print(f"[W{WORKER}] Too many MGMT errors, stopping.", flush=True)
                break
            time.sleep(10)
            continue
        except Exception as e:
            print(f"[W{WORKER}] fetch err: {e}", flush=True)
            consecutive_errors += 1
            if consecutive_errors >= 5:
                print(f"[W{WORKER}] Too many errors, stopping.", flush=True)
                break
            time.sleep(10)
            continue

        if not batch:
            print(f"[W{WORKER}] No more devices. Done — updated {processed} devices in {batches} batches.", flush=True)
            break

        consecutive_errors = 0
        last_id = batch[-1]["id"]  # advance cursor

        try:
            enriched = enrich(batch)
            for item in enriched:
                if not item.get("id"):
                    continue
                updates = {}
                desc = (item.get("description") or "").strip()
                cat  = (item.get("category") or "").strip()
                if desc and "FDA-cleared" not in desc and len(desc) > 20:
                    updates["description"] = desc[:500]
                if cat in CATEGORIES:
                    updates["category"] = cat
                if updates:
                    patch(item["id"], updates)
                    processed += 1

            batches += 1
            print(f"[W{WORKER}] batch={batches} cursor={last_id[:8]}... ✓ +{len(enriched)} (total={processed})", flush=True)
        except Exception as e:
            print(f"[W{WORKER}] enrich err: {e}", flush=True)
            time.sleep(10)

        time.sleep(3)  # 3s between batches (slightly slower than 2 but safer with 2 workers)

    print(f"[W{WORKER}] Exited — updated {processed} total", flush=True)


if __name__ == "__main__":
    main()
