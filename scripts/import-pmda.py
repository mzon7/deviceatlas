#!/usr/bin/env python3
"""
DeviceAtlas — Japan PMDA Medical Device Import Pipeline

Data sources:
1. Comprehensive PDF: https://www.pmda.go.jp/files/000277670.pdf
   "New & Improved Medical Devices (April 2004 to June 2025)"
   Parsed using pdfminer spatial layout extraction.

2. HTML review reports page (for source URLs):
   https://www.pmda.go.jp/english/review-services/reviews/approved-information/devices/0003.html

Pipeline:
- Parse PDF into structured rows (review_category, approval_date, brand_name,
  manufacturer, approval_type, term_name, notes)
- Fuzzy-match each device to existing DeviceAtlas devices
- For matches: create JP approval linking to existing device
- For new: create new device record + JP approval
- Classify disease states via Grok (using FDA taxonomy terms for consistency)
- Write import_tracking row for every PMDA record (source='pmda')
- On re-runs: skip already-tracked records
"""

import json
import os
import re
import time
import uuid
import urllib.request
import urllib.error
import urllib.parse
import html.parser
from difflib import SequenceMatcher

# ─── Config ──────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_PROJECT_REF = os.environ["SUPABASE_PROJECT_REF"]
SUPABASE_MGMT_TOKEN = os.environ["SUPABASE_MGMT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]  # switched from GROK_API_KEY on 2026-03-10

PMDA_PDF_URL = "https://www.pmda.go.jp/files/000277670.pdf"
PMDA_PDF_CACHE = "/tmp/pmda_devices.pdf"
PMDA_REVIEW_URL = "https://www.pmda.go.jp/english/review-services/reviews/approved-information/devices/0003.html"
PMDA_BASE_URL = "https://www.pmda.go.jp"

MATCH_THRESHOLD = 0.72
TRACKING_SOURCE = "pmda"

# Column x-boundaries derived from layout analysis of the PMDA PDF
# Each column is identified by its x-range
COL_REVIEW_CATEGORY   = (80,  185)   # x≈108
COL_APPROVAL_DATE     = (185, 260)   # x≈191-198
COL_US_DATE           = (260, 380)   # x≈266-282
COL_BRAND_NAME        = (380, 530)   # x≈391-418
COL_APPROVAL_TYPE     = (530, 590)   # x≈533-547
COL_TERM_NAME         = (590, 660)   # x≈597-608
COL_NOTES             = (660, 900)   # x≈677-768

_tracking_buffer: list = []

# ─── Supabase helpers ─────────────────────────────────────────────────────────

def rest_get(path: str, params: dict = None) -> list:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "User-Agent": "curl/7.81.0",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def rest_post(path: str, data: list, upsert: bool = False) -> bool:
    payload = json.dumps(data).encode()
    prefer = "resolution=ignore-duplicates,return=minimal" if upsert else "return=minimal"
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=payload, method="POST",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": prefer,
            "User-Agent": "curl/7.81.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60):
            return True
    except urllib.error.HTTPError as e:
        print(f"  REST POST error {e.code}: {e.read()[:200]}")
        return False


def mgmt_query(sql: str) -> list:
    payload = json.dumps({"query": sql}).encode()
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{SUPABASE_PROJECT_REF}/database/query",
        data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {SUPABASE_MGMT_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "curl/7.81.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read())
            return result if isinstance(result, list) else []
    except Exception as e:
        print(f"  SQL error: {e}")
        return []

# ─── Import tracking ──────────────────────────────────────────────────────────

def load_tracked_pmda_refs() -> set:
    """Load already-tracked PMDA source_refs to skip on re-runs."""
    print("Loading already-tracked PMDA refs...")
    tracked = set()
    limit, offset = 5000, 0
    while True:
        try:
            rows = rest_get("deviceatlas_import_tracking", {
                "select": "source_ref",
                "source": "eq.pmda",
                "limit": str(limit),
                "offset": str(offset),
            })
            for r in rows:
                tracked.add(r["source_ref"])
            if len(rows) < limit:
                break
            offset += limit
        except Exception as e:
            print(f"  Warning: {e}")
            break
    print(f"  {len(tracked)} already-tracked PMDA records (will skip)")
    return tracked


def make_source_ref(brand_name: str, approval_date: str) -> str:
    """Create a stable unique source_ref from brand name + date."""
    slug = re.sub(r"[^\w]", "_", brand_name.lower())[:60].rstrip("_")
    date_slug = re.sub(r"[^\w]", "_", approval_date)[:20].rstrip("_")
    return f"{slug}__{date_slug}"


def flush_tracking(force: bool = False):
    global _tracking_buffer
    if not _tracking_buffer or (not force and len(_tracking_buffer) < 100):
        return
    batch = _tracking_buffer[:]
    _tracking_buffer = []
    rest_post("deviceatlas_import_tracking", batch, upsert=True)
    print(f"  [tracking] flushed {len(batch)} rows")


def track(source_ref: str, status: str, device_id: str = None,
          source_url: str = None, notes: str = None):
    row = {
        "source": TRACKING_SOURCE,
        "source_ref": source_ref,
        "source_url": source_url,
        "fetch_status": status,
        "notes": notes,
    }
    if device_id:
        row["device_id"] = device_id
    _tracking_buffer.append(row)
    flush_tracking()

# ─── GPT-4o AI (switched from Grok on 2026-03-10; existing rows have enrichment_method="grok_inferred") ──

PMDA_SYSTEM_PROMPT = """You are a medical device regulatory expert analyzing PMDA (Japan) approved devices.
Given a device name and its PMDA classification term, identify 1-4 disease states or clinical indications.

CRITICAL: Use the SAME disease state terminology used by the US FDA medical specialty classification system.
Use the exact FDA Medical Specialty category names and clinical terminology for cross-country consistency.

Return ONLY valid JSON (no markdown):
{
  "indications": [
    {"name": "Disease or condition name (FDA taxonomy)", "confidence": "high|medium|low"}
  ],
  "enrichment_method": "gpt_inferred",
  "enrichment_confidence": "high|medium|low"
}

Rules:
- Use precise FDA medical terminology (e.g., "Atrial Fibrillation" not "heart rhythm problems")
- 1-2 indications for specific devices, up to 4 for multi-use devices
- confidence=high if term_name clearly implies the indication
- enrichment_confidence = highest confidence of any indication"""


def gpt_classify(device_name: str, term_name: str, review_category: str, notes: str = "") -> dict | None:
    context = f"Device: {device_name}\nTerm name: {term_name}\nPMDA specialty: {review_category}"
    if notes:
        context += f"\nDescription: {notes[:500]}"

    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": PMDA_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        "temperature": 0.1,
        "max_tokens": 600,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            content = json.loads(r.read())["choices"][0]["message"]["content"].strip()
            # Strip markdown fences if present
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)
            return json.loads(content)
    except Exception as e:
        print(f"  GPT error: {e}")
        return None

# ─── PDF parsing ──────────────────────────────────────────────────────────────

def download_pdf():
    if os.path.exists(PMDA_PDF_CACHE):
        size = os.path.getsize(PMDA_PDF_CACHE)
        print(f"Using cached PDF ({size/1024/1024:.1f} MB): {PMDA_PDF_CACHE}")
        return
    print(f"Downloading PMDA PDF from {PMDA_PDF_URL} ...")
    req = urllib.request.Request(PMDA_PDF_URL, headers={"User-Agent": "curl/7.81.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(PMDA_PDF_CACHE, "wb") as f:
        f.write(r.read())
    print(f"  Saved to {PMDA_PDF_CACHE} ({os.path.getsize(PMDA_PDF_CACHE)/1024/1024:.1f} MB)")


def col_for_x(x: float) -> str | None:
    """Map an x-coordinate to a column name."""
    if COL_REVIEW_CATEGORY[0] <= x < COL_REVIEW_CATEGORY[1]:
        return "review_category"
    if COL_APPROVAL_DATE[0] <= x < COL_APPROVAL_DATE[1]:
        return "approval_date"
    if COL_US_DATE[0] <= x < COL_US_DATE[1]:
        return "us_date"
    if COL_BRAND_NAME[0] <= x < COL_BRAND_NAME[1]:
        return "brand_name"
    if COL_APPROVAL_TYPE[0] <= x < COL_APPROVAL_TYPE[1]:
        return "approval_type"
    if COL_TERM_NAME[0] <= x < COL_TERM_NAME[1]:
        return "term_name"
    if COL_NOTES[0] <= x < COL_NOTES[1]:
        return "notes"
    return None


def parse_pdf_to_rows() -> list[dict]:
    """
    Parse PMDA PDF using pdfminer spatial layout.

    Each device entry in the PDF spans MULTIPLE y-levels (multi-row cell layout):
      Level 1 (top):    review_category | approval_date | brand_name | approval_type | instrument_code | notes_text
      Level 2 (below):  (review_time)   | us_date_info  |            |               | clinical_term   |

    Strategy: A new device starts when review_category (x≈108) AND approval_date (x≈191)
    both appear at the same y-level. Everything until the next device start is merged
    into the current device's data.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextBox

    print("Parsing PMDA PDF (boundary-detection layout)...")

    # --- Pass 1: collect all text boxes from data pages ---
    all_boxes = []   # (page, y_top, x_left, col_name, raw_text)
    data_page_started = False

    for page_num, page_layout in enumerate(extract_pages(PMDA_PDF_CACHE)):
        page_boxes = []
        for element in page_layout:
            if isinstance(element, LTTextBox):
                x0, y0, x1, y1 = element.bbox
                text = element.get_text().strip()
                if not text:
                    continue
                col = col_for_x(x0)
                if col:
                    page_boxes.append((y1, x0, col, text))

        flat = " ".join(b[3] for b in page_boxes)
        if not data_page_started:
            if "Review Category" in flat and "Approval Date" in flat:
                data_page_started = True
            else:
                continue

        for y, x, col, text in page_boxes:
            all_boxes.append((page_num, y, x, col, text))

    print(f"  Collected {len(all_boxes)} text boxes from data pages")

    # --- Pass 2: Group boxes into y-bands (close y = same horizontal line) ---
    # Sort top-to-bottom, left-to-right
    all_boxes.sort(key=lambda b: (b[0], -b[1], b[2]))

    # Group into y-bands: boxes within 6 pts vertically → same band
    bands = []   # list of (page, y_avg, {col: text})
    Y_BAND = 6
    for page_num, y, x, col, text in all_boxes:
        if bands and bands[-1][0] == page_num and abs(y - bands[-1][1]) <= Y_BAND:
            bands[-1][2][col] = (bands[-1][2].get(col, "") + " " + text.replace("\n", " ")).strip()
        else:
            bands.append((page_num, y, {col: text.replace("\n", " ").strip()}))

    # --- Pass 3: Device boundary detection ---
    # A device starts when a band has BOTH review_category AND approval_date,
    # OR has brand_name AND approval_date (the main device header band).
    DATE_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{2},?\s+\d{4}\b|"
                          r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{4}\b", re.IGNORECASE)

    def is_device_start(band_cols: dict) -> bool:
        has_date = DATE_RE.search(band_cols.get("approval_date", ""))
        has_brand = bool(band_cols.get("brand_name", "").strip())
        has_cat = bool(band_cols.get("review_category", "").strip())
        return bool(has_date) and (has_brand or has_cat)

    def is_header_band(band_cols: dict) -> bool:
        brand = band_cols.get("brand_name", "")
        return "Brand Name" in brand or "Applicant Company" in brand

    devices = []
    current = None

    for page_num, y, band_cols in bands:
        if is_header_band(band_cols):
            continue  # skip table headers

        if is_device_start(band_cols):
            if current:
                devices.append(current)
            current = dict(band_cols)
        elif current is not None:
            # Merge into current device — secondary rows add clinical term, us_date, notes
            for col, text in band_cols.items():
                if col not in current:
                    current[col] = text
                else:
                    if col == "term_name":
                        existing = current[col]
                        # Replace only if existing is an instrument code and new text is a clinical desc
                        is_code = re.match(r"^(Instrument\s*&?\s*apparatus|Medical products|Reagent|In vitro)\s*\d*", existing, re.I)
                        is_clinical = not re.match(r"^(Instrument\s*&?\s*apparatus|Medical products|Reagent|In vitro)\s*\d*", text, re.I)
                        if is_code and is_clinical:
                            current[col] = text
                    elif col == "notes":
                        current[col] = current[col] + " " + text  # append notes

    if current:
        devices.append(current)

    print(f"  Parsed {len(devices)} device entries from PDF")
    return devices


def clean_rows(rows: list[dict]) -> list[dict]:
    """Extract manufacturer from brand_name field and clean up data."""
    cleaned = []
    for r in rows:
        brand_raw = r.get("brand_name", "")
        # Format: "Brand Name\n(Manufacturer)" or "Brand Name (Manufacturer)"
        m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", brand_raw, re.DOTALL)
        if m:
            brand = m.group(1).strip().replace("\n", " ")
            manufacturer = m.group(2).strip().replace("\n", " ")
        else:
            brand = brand_raw.strip().replace("\n", " ")
            manufacturer = ""

        approval_date_raw = r.get("approval_date", "").strip()
        # Parse date like "May 12, 2025" or "Jun. 26, 2025" or "Apr. 2004"
        approval_date = parse_date(approval_date_raw)

        approval_type = r.get("approval_type", "").strip().replace("\n", " ")
        term_name = r.get("term_name", "").strip().replace("\n", " ")
        review_category = r.get("review_category", "").strip().replace("\n", " ")
        notes = r.get("notes", "").strip().replace("\n", " ")

        if not brand or not approval_date:
            continue

        # Skip obvious header/section rows
        if brand.lower() in ("brand name", "new approval", "review category"):
            continue

        cleaned.append({
            "brand_name": brand,
            "manufacturer": manufacturer,
            "approval_date": approval_date,
            "approval_type": approval_type,  # "Approval" or "Change"
            "term_name": term_name,
            "review_category": review_category,
            "notes": notes,
        })

    print(f"  {len(cleaned)} clean device rows (after filtering headers/blanks)")
    return cleaned


def parse_date(s: str) -> str | None:
    """Parse PMDA date strings into YYYY-MM-DD or YYYY-MM."""
    s = s.strip()
    month_map = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    # "May 12, 2025"
    m = re.match(r"(\w+)\.?\s+(\d+),?\s+(\d{4})", s, re.IGNORECASE)
    if m:
        mon = month_map.get(m.group(1).lower()[:3])
        if mon:
            return f"{m.group(3)}-{mon}-{m.group(2).zfill(2)}"
    # "Apr. 2004" or "Jun 2025"
    m = re.match(r"(\w+)\.?\s+(\d{4})", s, re.IGNORECASE)
    if m:
        mon = month_map.get(m.group(1).lower()[:3])
        if mon:
            return f"{m.group(2)}-{mon}-01"
    return None

# ─── HTML review reports scrape ───────────────────────────────────────────────

class PMDAReviewParser(html.parser.HTMLParser):
    """Extract device name → review report URL mapping from the PMDA HTML page."""
    def __init__(self):
        super().__init__()
        self.devices = {}  # brand_name → source_url
        self._in_table = False
        self._in_td = False
        self._current_href = None
        self._current_text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._in_table = True
        if tag == "td":
            self._in_td = True
            self._current_text = ""
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v and v.endswith(".pdf"):
                    self._current_href = PMDA_BASE_URL + v if v.startswith("/") else v

    def handle_endtag(self, tag):
        if tag == "td":
            text = self._current_text.strip()
            if self._current_href and text and len(text) > 3:
                self.devices[text] = self._current_href
                self._current_href = None
            self._in_td = False

    def handle_data(self, data):
        if self._in_td:
            self._current_text += data


def scrape_review_urls() -> dict:
    """Fetch PMDA review reports page and extract brand_name → PDF URL mapping."""
    print(f"Scraping PMDA review reports page for source URLs...")
    try:
        req = urllib.request.Request(PMDA_REVIEW_URL, headers={"User-Agent": "curl/7.81.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html_content = r.read().decode("utf-8", errors="replace")
        parser = PMDAReviewParser()
        parser.feed(html_content)
        print(f"  Found {len(parser.devices)} devices with review report URLs")
        return parser.devices
    except Exception as e:
        print(f"  Warning: could not scrape review URLs: {e}")
        return {}

# ─── Device matching ──────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    noise = {"the", "a", "an", "and", "or", "for", "of", "with", "by", "to", "in", "on",
             "system", "device", "kit", "set", "unit"}
    tokens = [t for t in s.split() if t not in noise]
    return " ".join(tokens)


def load_db_devices() -> list:
    """Load existing devices from DB for matching (all pages, 1000 per request)."""
    print("Loading existing devices from DB for matching...")
    all_devices = []
    # Supabase REST caps at 1000 rows per request — use 1000 so pagination works correctly
    PAGE_SIZE = 1000
    offset = 0
    while True:
        rows = rest_get("deviceatlas_devices", {
            "select": "id,name,manufacturer",
            "limit": str(PAGE_SIZE),
            "offset": str(offset),
        })
        if not rows:
            break
        all_devices.extend(rows)
        if offset % 20000 == 0 and offset > 0:
            print(f"  Loaded {offset} devices...")
        if len(rows) < PAGE_SIZE:
            break  # last page
        offset += PAGE_SIZE
    print(f"  Total devices in DB: {len(all_devices)}")
    return all_devices


def match_to_db(pmda_rows: list[dict], db_devices: list) -> list[dict]:
    """
    Fuzzy-match PMDA devices to existing DB devices.
    Adds 'matched_device_id' and 'match_score' to each row.
    """
    print(f"Matching {len(pmda_rows)} PMDA devices to {len(db_devices)} DB devices...")

    # Build exact name index
    db_exact = {}
    db_bigram = {}
    for dev in db_devices:
        name = dev.get("name", "") or ""
        norm = normalize(name)
        if norm:
            db_exact[norm] = dev
            tokens = norm.split()
            if len(tokens) >= 2:
                key = (tokens[0], tokens[1])
            elif tokens:
                key = (tokens[0],)
            else:
                continue
            db_bigram.setdefault(key, []).append((norm, dev))

    matched = unmatched = 0
    for row in pmda_rows:
        brand = row["brand_name"]
        norm = normalize(brand)

        # Exact match
        if norm in db_exact:
            row["matched_device_id"] = db_exact[norm]["id"]
            row["match_score"] = 1.0
            matched += 1
            continue

        # Bigram fuzzy match
        tokens = norm.split()
        if len(tokens) >= 2:
            key = (tokens[0], tokens[1])
        elif tokens:
            key = (tokens[0],)
        else:
            row["matched_device_id"] = None
            row["match_score"] = 0.0
            unmatched += 1
            continue

        candidates = db_bigram.get(key, [])[:30]
        best_score, best_dev = 0.0, None
        for cand_norm, cand_dev in candidates:
            score = SequenceMatcher(None, norm, cand_norm).ratio()
            if score > best_score:
                best_score, best_dev = score, cand_dev

        if best_score >= MATCH_THRESHOLD and best_dev:
            row["matched_device_id"] = best_dev["id"]
            row["match_score"] = best_score
            matched += 1
        else:
            row["matched_device_id"] = None
            row["match_score"] = best_score
            unmatched += 1

    print(f"  Matched: {matched} | New devices: {unmatched}")
    return pmda_rows

# ─── Disease state resolution ─────────────────────────────────────────────────

_disease_state_cache: dict = {}  # name_lower → id


def load_disease_states():
    global _disease_state_cache
    rows = rest_get("deviceatlas_disease_states", {"select": "id,name", "limit": "5000"})
    _disease_state_cache = {r["name"].lower(): r["id"] for r in rows}
    print(f"  Loaded {len(_disease_state_cache)} disease states")


def get_or_create_disease_state(name: str) -> str | None:
    if not name:
        return None
    key = name.lower().strip()
    if key in _disease_state_cache:
        return _disease_state_cache[key]
    # Create new
    new_id = str(uuid.uuid4())
    rest_post("deviceatlas_disease_states", [{"id": new_id, "name": name.strip()}])
    _disease_state_cache[key] = new_id
    return new_id

# ─── Main import logic ────────────────────────────────────────────────────────

def guess_category(review_category: str, term_name: str) -> str:
    """Map PMDA review category to our device category."""
    cat = (review_category + " " + term_name).lower()
    if any(k in cat for k in ["cardio", "cardiac", "heart", "coronary", "valve", "aortic", "vascular"]):
        return "Cardiovascular"
    if any(k in cat for k in ["ortho", "bone", "knee", "hip", "spine", "joint", "plastic"]):
        return "Orthopedic"
    if any(k in cat for k in ["brain", "neuro", "spinal", "neural", "psychiatric"]):
        return "Neurology"
    if any(k in cat for k in ["gastro", "digest", "bowel", "colon", "esophag", "stomach"]):
        return "Gastroenterology"
    if any(k in cat for k in ["ophthalm", "eye", "retina", "cornea", "lens"]):
        return "Ophthalmology"
    if any(k in cat for k in ["pulmon", "respir", "lung", "breath", "ventilat"]):
        return "Pulmonology"
    if any(k in cat for k in ["renal", "kidney", "urology", "urolog", "dialysis"]):
        return "Urology"
    if any(k in cat for k in ["dental", "oral", "tooth"]):
        return "Dental"
    if any(k in cat for k in ["obstetric", "gynecol", "reproduct"]):
        return "Obstetrics/Gynecology"
    if any(k in cat for k in ["oncology", "tumor", "cancer"]):
        return "Oncology"
    if any(k in cat for k in ["diagnostic", "imaging", "radiology", "mri", "ct"]):
        return "Radiology/Imaging"
    if any(k in cat for k in ["robotics", "iot", "software"]):
        return "Digital Health"
    return "General"


def process_and_insert(pmda_rows: list[dict], review_urls: dict, already_tracked: set):
    """
    For each PMDA device row:
    1. Skip if already tracked
    2. Grok-classify disease states
    3. Get or create device record
    4. Insert JP approval
    5. Write tracking row
    """
    load_disease_states()

    new_devices = 0
    matched_devices = 0
    approvals_inserted = 0
    skipped = 0

    for i, row in enumerate(pmda_rows):
        brand = row["brand_name"]
        approval_date = row["approval_date"]
        source_ref = make_source_ref(brand, approval_date)

        if source_ref in already_tracked:
            skipped += 1
            continue

        if i % 50 == 0 and i > 0:
            print(f"  [{i}/{len(pmda_rows)}] {matched_devices} matched, {new_devices} new, {skipped} skipped")
            flush_tracking()
            time.sleep(0.3)  # be gentle

        # Find source URL (from HTML review page or construct PMDA search URL)
        source_url = None
        for name_key, url in review_urls.items():
            if brand.lower() in name_key.lower() or name_key.lower() in brand.lower():
                source_url = url
                break
        if not source_url:
            # Construct PMDA search URL as fallback
            search_q = urllib.parse.quote(brand)
            source_url = f"https://www.pmda.go.jp/english/review-services/reviews/approved-information/devices/0001.html"

        # Grok classification (only for "Approval" type, not "Change" which modifies existing)
        indications = []
        enrichment_method = "not_enriched"
        enrichment_confidence = None
        indications_text = None
        indications_source = None

        term_name = row.get("term_name", "")
        review_category = row.get("review_category", "")
        notes = row.get("notes", "")

        if term_name or review_category:
            result = gpt_classify(brand, term_name, review_category, notes)
            if result and result.get("indications"):
                indications = result["indications"]
                enrichment_method = result.get("enrichment_method", "gpt_inferred")
                enrichment_confidence = result.get("enrichment_confidence", "medium")
                indications_text = "; ".join(
                    f"{ind['name']} [{ind.get('confidence', 'medium')}]"
                    for ind in indications
                )
                indications_source = f"PMDA Term: {term_name} | Category: {review_category}"

        # Get or create device
        device_id = row.get("matched_device_id")
        if device_id:
            matched_devices += 1
        else:
            # Create new device
            device_id = str(uuid.uuid4())
            device_row = {
                "id": device_id,
                "name": brand,
                "manufacturer": row.get("manufacturer") or "Unknown",
                "category": guess_category(review_category, term_name),
                "description": notes[:500] if notes else None,
                "is_active": True,
                "cleared_date": approval_date,
                "enrichment_method": enrichment_method,
                "enrichment_confidence": enrichment_confidence,
                "indications_text": indications_text,
                "indications_source": indications_source,
            }
            if not rest_post("deviceatlas_devices", [device_row]):
                track(source_ref, "error", notes=f"device insert failed: {brand[:80]}")
                continue
            new_devices += 1

        # Resolve disease states and insert approvals
        approval_rows = []
        if indications:
            for ind in indications:
                ds_id = get_or_create_disease_state(ind["name"])
                if ds_id:
                    approval_rows.append({
                        "device_id": device_id,
                        "disease_state_id": ds_id,
                        "country": "JP",
                        "status": "Approved" if row.get("approval_type", "").lower() != "change" else "Approved",
                        "approval_date": approval_date,
                        "source_ref": source_ref,
                        "is_active": True,
                    })
        else:
            # Insert one approval row with no disease state
            approval_rows.append({
                "device_id": device_id,
                "disease_state_id": None,
                "country": "JP",
                "status": "Approved",
                "approval_date": approval_date,
                "source_ref": source_ref,
                "is_active": True,
            })

        if approval_rows:
            rest_post("deviceatlas_approvals", approval_rows, upsert=False)
            approvals_inserted += len(approval_rows)

        # Write tracking
        track(source_ref, "imported", device_id=device_id, source_url=source_url,
              notes=f"match_score={row.get('match_score', 0):.2f}|term={term_name[:60]}")

    flush_tracking(force=True)
    return matched_devices, new_devices, approvals_inserted, skipped


def main():
    print("=" * 70)
    print("DeviceAtlas — Japan PMDA Medical Device Import")
    print("=" * 70)

    # Step 1: Load already-tracked PMDA refs (for re-run skip logic)
    already_tracked = load_tracked_pmda_refs()

    # Step 2: Download PDF
    download_pdf()

    # Step 3: Parse PDF into device rows
    raw_rows = parse_pdf_to_rows()
    if not raw_rows:
        print("ERROR: No device rows parsed from PDF. Check PDF structure.")
        return
    rows = clean_rows(raw_rows)

    # Step 4: Filter out already-tracked
    new_rows = [r for r in rows if make_source_ref(r["brand_name"], r["approval_date"]) not in already_tracked]
    print(f"\nNew PMDA records to process: {len(new_rows)} (skipping {len(rows) - len(new_rows)} already tracked)")

    if not new_rows:
        print("All PMDA records already tracked. Nothing to do.")
        return

    # Step 5: Scrape review report URLs
    review_urls = scrape_review_urls()

    # Step 6: Match to existing DB devices
    db_devices = load_db_devices()
    new_rows = match_to_db(new_rows, db_devices)

    # Step 7: Process and insert
    print(f"\nProcessing {len(new_rows)} PMDA devices (GPT-4o classify + DB insert)...")
    matched, created, approvals, skipped = process_and_insert(new_rows, review_urls, already_tracked)

    # Final summary
    stats = mgmt_query(
        "SELECT "
        "(SELECT COUNT(*) FROM deviceatlas_approvals WHERE country='JP') as jp_approvals, "
        "(SELECT COUNT(*) FROM deviceatlas_import_tracking WHERE source='pmda') as tracked_pmda;"
    )
    print("\n" + "=" * 70)
    print("DONE — Japan PMDA Import Summary")
    print("=" * 70)
    print(f"  PMDA records processed : {len(new_rows)}")
    print(f"  Matched to existing    : {matched}")
    print(f"  New devices created    : {created}")
    print(f"  JP approvals inserted  : {approvals}")
    print(f"  Skipped (re-run)       : {skipped}")
    if stats:
        print(f"  Total JP approvals DB  : {stats[0].get('jp_approvals', '?')}")
        print(f"  Total PMDA tracked     : {stats[0].get('tracked_pmda', '?')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
