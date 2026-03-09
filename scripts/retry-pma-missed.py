#!/usr/bin/env python3
"""
Retry missed PMA supplements that failed with 429 in the main loader.
Uses 1 req/sec (60/min) to stay well under OpenFDA's 240/min limit.
On 429, backs off 60s before retrying.
"""

import json, os, time, uuid, urllib.parse
import urllib.request, urllib.error

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_PROJECT_REF = os.environ["SUPABASE_PROJECT_REF"]
SUPABASE_MGMT_TOKEN = os.environ["SUPABASE_MGMT_TOKEN"]

MGMT_BASE = f"https://api.supabase.com/v1/projects/{SUPABASE_PROJECT_REF}/database/query"
FDA_API = "https://api.fda.gov/device/pma.json"

# All PMAs that received 429 in the main run
MISSED_PMAS = [
    "P210017","P210018","P210019","P210020","P210025","P210026","P210027","P210030","P210032","P210034",
    "P210035","P210036","P210037","P210039","P210040","P220002","P220003","P220004","P220005","P220006",
    "P220007","P220009","P220012","P220013","P220014","P220020","P220021","P220023","P220024","P220025",
    "P220026","P220029","P220030","P220031","P220032","P220034","P230001","P230002","P230003","P230005",
    "P230007","P230011","P230012","P230013","P230014","P230015","P230016","P230017","P230018","P230019",
    "P230020","P230021","P230022","P230023","P230024","P230025","P230026","P230030","P230032","P230035",
    "P230036","P230040","P230042","P230043","P230044","P240001","P240003","P240004","P240005","P240006",
    "P240008","P240009","P240010","P240011","P240012","P240013","P240014","P240015","P240020","P240022",
    "P240023","P240024","P240026","P240027","P240028","P240029","P240031","P240035","P240036","P240037",
    "P240038","P240039","P240040","P240042","P240043","P240045","P250002","P250003","P250004","P250005",
    "P250007","P250009","P250010","P250011","P250012","P250017","P250019","P250022","P250023","P250034",
    "P760001","P770001","P770002","P770005","P780002","P780005","P780006","P780007","P780009","P780010",
    "P780011","P780012","P790002","P790005","P790006","P790007","P790010","P790016","P790017","P790018",
    "P790019","P790020","P790025","P790027","P790028","P790032","P800002","P800003","P800012","P800016",
    "P800017","P800019","P800022","P800025","P800027","P800029","P800030","P800032","P800035","P800036",
    "P800049","P800058","P800061","P800064","P800068","P810001","P810002","P810005","P810006","P810007",
    "P810018","P810020","P810023","P810024","P810025","P810031","P810032","P810033","P810040","P810042",
    "P810044","P810046","P810048","P810055","P810056","P820002","P820003","P820008","P820009","P820012",
    "P820018","P820021","P820022","P820023","P820027","P820032","P820033","P820034","P820035","P820044",
    "P820049","P820052","P820060","P820072","P820073","P820075","P820076","P820077","P820078","P820079",
    "P820088","P830007","P830010","P830018","P830025","P830026","P830028","P830033","P830035","P830037",
    "P830039","P830040","P830045","P830047","P830054","P830055","P830056","P830060","P830061","P830062",
    "P830063","P830069","P830070","P830079","P830080","P840001","P840002","P840008","P840012","P840014",
    "P840015","P840024","P840027","P840029","P840031","P840039","P840040","P840044","P840045","P840047",
    "P840049","P840050","P840060","P840062","P840064","P840065","P840068","P840070","P850006","P850007",
    "P850010","P850019","P850020","P850021","P850022","P850023","P850027","P850029","P850033","P850035",
    "P850038","P850039","P850048","P850049","P850051","P850053","P850054","P850057","P850058","P850059",
    "P850062","P850063","P850064","P850068","P850069","P850072","P850077","P850078","P850079","P850089",
    "P850091","P850092","P860003","P860004","P860005","P860007","P860008","P860012","P860015","P860019",
    "P860022","P860026","P860027","P860034","P860035","P860040","P860042","P860046","P860047","P860057",
    "P860059","P860064","P860067","P870011","P870013","P870015","P870018","P870021","P870024","P870025",
    "P870036","P870038","P870043","P870045","P870048","P870049","P870054","P870056","P870059","P870062",
    "P870072","P870073","P870076","P870077","P870078","P870080","P880003","P880006","P880009","P880010",
    "P880011","P880013","P880016","P880026","P880027","P880028","P880029","P880031","P880032","P880038",
    "P880040","P880042","P880045","P880047","P880055","P880062","P880064","P880065","P880070","P880072",
    "P880078","P880081","P880082","P880085","P880086","P880087","P880089","P880090","P880091","P880094",
    "P880098","P890001","P890002","P890003","P890012","P890013","P890014","P890017","P890019","P890020",
    "P890024","P890025","P890027","P890029","P890032","P890034","P890039","P890040","P890043","P890045",
    "P890047","P890048","P890049","P890055","P890056","P890057","P890061","P890063","P890064","P890065",
    "P890066","P890068","P890070","P900007","P900009","P900013","P900016","P900022","P900023","P900025",
    "P900030","P900032","P900033","P900037","P900038","P900039","P900042","P900043","P900048","P900050",
    "P900052","P900053","P900056","P900060","P900061","P900066","P900067","P900070","P910001","P910007",
    "P910016","P910018","P910019","P910020","P910023","P910030","P910031","P910054","P910056","P910058",
    "P910061","P910062","P910063","P910064","P910065","P910066","P910067","P910068","P910071","P910073",
    "P910077","P920004","P920006","P920011","P920014","P920015","P920023","P920027","P920030","P920032",
    "P920034","P920038","P920046","P920047","P920048","P920051","P930014","P930016","P930021","P930022",
    "P930024","P930027","P930029","P930030","P930031","P930034","P930035","P930036","P930038","P930039",
    "P940001","P940002","P940004","P940005","P940007","P940008","P940009","P940010","P940011","P940012",
    "P940013","P940015","P940016","P940019","P940022","P940024","P940029","P940031","P940033","P940034",
    "P940035","P940036","P940040","P950001","P950002","P950005","P950008","P950009","P950011","P950014",
    "P950015","P950018","P950019","P950020","P950021","P950022","P950024","P950027","P950029","P950032",
    "P950034","P950035","P950037","P950039","P950040","P950042","P950043","P960001","P960004","P960006",
    "P960007","P960009","P960010","P960011","P960013","P960014","P960016","P960018","P960019","P960020",
    "P960022","P960025","P960028","P960030","P960031","P960033","P960034","P960036","P960039","P960040",
    "P960042","P960043","P960044","P960047","P960052","P960053","P960054","P960057","P960058","P970002",
    "P970003","P970004","P970005","P970007","P970008","P970010","P970012","P970013","P970015","P970017",
    "P970018","P970019","P970020","P970021","P970024","P970025","P970026","P970027","P970029","P970030",
    "P970031","P970032","P970033","P970034","P970035","P970036","P970037","P970038","P970040","P970042",
    "P970043","P970044","P970049","P970051","P970052","P970053","P970054","P970055","P970056","P970058",
    "P970061","P970062","P980001","P980003","P980006","P980007","P980008","P980009","P980010","P980012",
    "P980015","P980016","P980017","P980018","P980020","P980022","P980023","P980024","P980025","P980031",
    "P980035","P980037","P980040","P980041","P980043","P980044","P980046","P980048","P980049","P980050",
    "P980052","P980053","P990001","P990002","P990004","P990008","P990009","P990010","P990012","P990013",
    "P990014","P990015","P990016","P990017","P990019","P990020","P990021","P990023","P990025","P990026",
    "P990027","P990028","P990030","P990033","P990034","P990035","P990036","P990037","P990038","P990039",
    "P990040","P990041","P990042","P990043","P990044","P990045","P990046","P990048","P990049","P990050",
    "P990052","P990053","P990054","P990055","P990056","P990064","P990065","P990066","P990069","P990071",
    "P990072","P990074","P990075","P990078","P990080","P990081","P990085","P990086",
]


def mgmt_query(sql: str):
    body = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        MGMT_BASE, data=body,
        headers={"Authorization": f"Bearer {SUPABASE_MGMT_TOKEN}",
                 "Content-Type": "application/json", "User-Agent": "curl/7.81.0"},
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt == 2: raise
            time.sleep(2 ** attempt)


def fda_api_with_retry(params: dict) -> list:
    """Call OpenFDA API with retry on 429 — backs off 60s."""
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url = f"{FDA_API}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.81.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
            return data.get("results", [])
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            if e.code == 429:
                wait = 60 * (attempt + 1)
                print(f"    429 rate limit — waiting {wait}s before retry {attempt+1}/5...")
                time.sleep(wait)
                continue
            raise
    print("    Exhausted retries on 429, skipping")
    return None  # Signal skip


def clean_name(name: str) -> str:
    replacements = {
        '\x99': '™', '\x93': '"', '\x94': '"', '\x95': '·',
        '\x96': '–', '\x97': '—', '\x91': '\u2018', '\x92': '\u2019',
    }
    for bad, good in replacements.items():
        name = name.replace(bad, good)
    return name.strip()


def names_are_similar(a: str, b: str) -> bool:
    a_words = set(a.lower().split())
    b_words = set(b.lower().split())
    if not a_words or not b_words:
        return False
    overlap = len(a_words & b_words) / min(len(a_words), len(b_words))
    return overlap > 0.6


def _flush_updates(updates: list):
    if not updates:
        return
    ids_sql = ", ".join(f"'{uid}'" for uid, _ in updates)
    case = " ".join(f"WHEN id = '{uid}' THEN '{date}'" for uid, date in updates)
    sql = f"UPDATE deviceatlas_devices SET cleared_date = CASE {case} ELSE cleared_date END WHERE id IN ({ids_sql}) AND clearance_type = 'PMA';"
    mgmt_query(sql)
    print(f"  Flushed: updated cleared_date for {len(updates)} PMA devices")


def _flush_devices(devices: list):
    if not devices:
        return
    rest_url = f"{SUPABASE_URL}/rest/v1/deviceatlas_devices"
    body = json.dumps(devices).encode()
    req = urllib.request.Request(
        rest_url, data=body,
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        print(f"  Flushed: inserted {len(devices)} new supplement devices")
    except Exception as e:
        print(f"  Insert error: {e}")


def main():
    print("=" * 60)
    print(f"PMA Retry Loader — {len(MISSED_PMAS)} missed PMAs")
    print("Rate: 1 req/sec (60/min), well under 240/min limit")
    print("=" * 60)

    # Load DB records for these PMAs
    pma_list_sql = ", ".join(f"'{p}'" for p in MISSED_PMAS)
    rows = mgmt_query(f"""
        SELECT id, name, manufacturer, category, cleared_date, submission_number
        FROM deviceatlas_devices
        WHERE submission_number IN ({pma_list_sql})
          AND clearance_type = 'PMA'
        ORDER BY submission_number
    """)
    print(f"Found {len(rows)} DB records for missed PMAs")

    # Load existing device names for dedup
    existing_rows = mgmt_query("SELECT LOWER(name) as n FROM deviceatlas_devices")
    existing_names = {r["n"] for r in existing_rows}
    print(f"Existing names: {len(existing_names):,}")

    updates = []
    new_devices = []
    skipped = 0
    total = len(rows)

    for i, device in enumerate(rows):
        pma_num = device["submission_number"]
        device_id = device["id"]
        current_name = device["name"]
        category = device["category"]
        manufacturer = device["manufacturer"]

        results = fda_api_with_retry({
            "search": f"pma_number:{pma_num}",
            "limit": "100",
            "sort": "decision_date:desc",
        })

        if results is None:
            skipped += 1
            time.sleep(1)
            continue

        # Keep only supplements (non-empty supplement_number)
        results = [r for r in results if r.get("supplement_number", "").strip()]

        if not results:
            time.sleep(1)
            continue

        # Most recent supplement → update cleared_date
        most_recent = results[0]
        most_recent_date = most_recent.get("decision_date") or device.get("cleared_date")
        if most_recent_date and most_recent_date != device.get("cleared_date"):
            updates.append((device_id, most_recent_date))

        # Collect unique trade_names to add as new devices
        seen_trade_names = {current_name.lower()}
        for rec in results:
            trade_name = clean_name(rec.get("trade_name") or "")
            if not trade_name or len(trade_name) < 4:
                continue
            trade_name = trade_name[:200]
            trade_lower = trade_name.lower()
            if trade_lower in seen_trade_names:
                continue
            if names_are_similar(current_name, trade_name):
                seen_trade_names.add(trade_lower)
                continue
            if trade_lower in existing_names:
                seen_trade_names.add(trade_lower)
                continue
            seen_trade_names.add(trade_lower)
            existing_names.add(trade_lower)
            cleared = rec.get("decision_date")
            new_devices.append({
                "id": str(uuid.uuid4()),
                "name": trade_name,
                "manufacturer": manufacturer or "Unknown",
                "category": category or "General Surgery",
                "description": "",
                "is_active": True,
                "cleared_date": cleared,
                "submission_number": f"{pma_num}/{rec.get('supplement_number','')}",
                "clearance_type": "PMA",
            })

        print(f"  [{i+1}/{total}] {pma_num}: {len(results)} supplements | updates={len(updates)} new={len(new_devices)}")

        # Flush every 50 updates or 100 new devices
        if len(updates) >= 50:
            _flush_updates(updates)
            updates = []
        if len(new_devices) >= 100:
            _flush_devices(new_devices)
            new_devices = []

        time.sleep(1.0)  # 1 req/sec = 60/min, well under 240/min limit

    # Final flush
    if updates:
        _flush_updates(updates)
    if new_devices:
        _flush_devices(new_devices)

    result = mgmt_query("SELECT COUNT(*) as c FROM deviceatlas_devices")
    print(f"\nDone! Skipped (exhausted retries): {skipped}")
    print(f"Total devices in DB: {result[0]['c']:,}")


if __name__ == "__main__":
    main()
