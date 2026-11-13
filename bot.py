# V8.1 FINAL - FREE FIXES ONLY - No Paid APIs, No Risky Scraping
import os, requests, html, time, sys
from datetime import datetime, timedelta, timezone

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_IDS = [c for c in [os.getenv("TELEGRAM_CHAT_ID"), os.getenv("TELEGRAM_CHANNEL_ID")] if c]
SHEET_URL = os.getenv("SHEET_URL")

if not TOKEN or not CHAT_IDS:
    print("ERROR: Missing TELEGRAM_TOKEN or CHAT_ID / CHANNEL_ID. Check GitHub Secrets names exactly.")
    sys.exit(1)
print(f"Bot started. Destinations: {len(CHAT_IDS)} | Sheet URL set: {bool(SHEET_URL)}")

HEADERS = {"User-Agent": "Roof-Leads-Bot/8.1 (Contact: lead-seller)"}

# --- FREE FIX P2: Skip paperwork that is NOT a job ---
SKIP_IF_CONTAINS = [
    "DOES NOT AUTHORIZE",
    "DOES NOT AUTHORIZE ANY CONSTRUCTION",
    "APPROVAL OF NEW PLAN FOR",
    "PLAN REVIEW ONLY",
    "NO CONSTRUCTION WORK",
]

def get_niche(desc):
    t = (desc or "").upper()
    if not t:
        return None
    # P2: Junk filter - free, safe, no API call
    if any(s in t for s in SKIP_IF_CONTAINS):
        return None

    if "SOLAR" in t or "PHOTOVOLTAIC" in t:
        return "SOLAR"
    # P1 FIX: ROOFING only on real roofing words.
    # "HIP ROOF", "ROOF HEIGHT", "ROOF LINE" alone = NOT roofing.
    # Check GARAGE first, because "GARAGE... HIP ROOF" is a garage.
    if "GARAGE" in t:
        return "GARAGE"
    if "ROOF REPLACEMENT" in t or "REROOF" in t or "RE-ROOF" in t or "ROOF REPAIR" in t or "ROOFING" in t or "REPLACE ROOF" in t or "NEW ROOF" in t or "ROOF COVERING" in t:
        return "ROOFING"
    if "KITCHEN" in t:
        return "KITCHEN REMODEL"
    if "BATH" in t:
        return "BATHROOM REMODEL"
    if "ELECTRICAL" in t or "ELECTRIC" in t or "FIRE ALARM" in t:
        return "ELECTRICAL"
    if "PLUMBING" in t or "PLUMB" in t:
        return "PLUMBING"
    if "HVAC" in t or "FURNACE" in t or "AIR CONDITION" in t:
        return "HVAC"
    if "FENCE" in t:
        return "FENCE"
    if "DECK" in t or "PORCH" in t:
        return "DECK / PORCH"
    if "WINDOW" in t or "DOOR" in t:
        return "WINDOWS / DOORS"
    if "FOUNDATION" in t or "CONCRETE" in t:
        return "FOUNDATION / CONCRETE"
    if "SIGN" in t:
        return "SIGN"
    if "DEMOLITION" in t or "DEMO" in t:
        return "DEMOLITION"
    if "ADDITION" in t:
        return "ADDITION"
    if "RENOVATION" in t or "REMODEL" in t or "ALTERATION" in t:
        return "RENOVATION"
    if "NEW CONSTRUCTION" in t or "NEW SINGLE" in t or "NEW DETACHED" in t or "NEW BUILD" in t:
        return "NEW CONSTRUCTION"
    return "GENERAL BUILDING"

def clean(v):
    return html.escape(str(v or "").strip())

def get_existing_ids():
    if not SHEET_URL:
        print("WARNING: SHEET_URL missing, dedup disabled")
        return set()
    try:
        r = requests.get(SHEET_URL, headers=HEADERS, timeout=25)
        if r.status_code == 200:
            ids = set(str(x) for x in r.json().get("ids", []))
            print(f"Existing IDs in Sheet: {len(ids)}")
            return ids
    except Exception as e:
        print(f"Sheet read failed, continuing safely: {e}")
    return set()

def build_address(city_name, row):
    try:
        if city_name == "Chicago":
            parts = [row.get("street_number",""), row.get("street_direction",""), row.get("street_name",""), row.get("suffix","")]
            addr = " ".join([str(p).strip() for p in parts if str(p).strip()])
            return f"{addr}, Chicago, IL" if addr else ""
        if city_name == "NYC":
            return f"{row.get('house_no','')} {row.get('street_name','')}, {row.get('borough','')}, NY".strip()
        if city_name == "Austin":
            return f"{row.get('original_address1','')}, Austin, TX".strip()
        if city_name == "San Francisco":
            addr = f"{row.get('street_number','')} {row.get('street_name','')} {row.get('street_suffix','')}".strip()
            return f"{addr}, San Francisco, CA" if addr else ""
        if city_name == "Seattle":
            return f"{row.get('address','')}, Seattle, WA".strip()
    except Exception:
        return ""
    return ""

def fetch_city(city):
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%S.000")
    where = f"{city['date_field']} > '{cutoff}'"
    try:
        r = requests.get(city["url"], params={"$limit": 1000, "$order": f"{city['date_field']} DESC", "$where": where}, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"{city['name']} API {r.status_code} - skipping, others continue")
            return []
        data = r.json()
        print(f"{city['name']}: API returned {len(data)} rows in 72h")
        out = []
        for row in data:
            desc = row.get(city["desc_field"], "") or ""
            niche = get_niche(desc)
            if not niche:
                continue
            address = build_address(city["name"], row)
            if not address or address in ["Chicago, IL", ", Austin, TX", ", NY"]:
                continue
            # P3 FIX: Free and honest. If no cost, say Not Listed.
            # Never put "Permit Approved" in the Value column - that's status, not money.
            value = row.get(city["value_field"], "") or ""
            value_str = str(value).strip()
            if value_str in ["", "0", "None", "0.0"]:
                value_str = "Not Listed"
            contractor = ""
            if city["name"] == "Chicago":
                contractor = row.get("contractor_name","") or row.get("applicant_name","") or ""
            elif city["name"] == "NYC":
                contractor = f"{row.get('applicant_first_name','')} {row.get('applicant_last_name','')}".strip()
            elif city["name"] == "Austin":
                contractor = row.get("contractor_name","") or ""
            out.append({
                "city": city["name"], "niche": niche,
                "id": str(row.get(city["id_field"],"")),
                "address": address, "desc": desc[:160],
                "date": str(row.get(city["date_field"],""))[:10],
                "value": value_str, "contact": contractor,
                "phone": "", "email": ""
            })
            if len(out) >= 30:
                break
        print(f"{city['name']}: {len(out)} fresh clean")
        return out
    except Exception as e:
        print(f"{city['name']} error (skipped): {e}")
        return []

def send_telegram(text):
    for cid in CHAT_IDS:
        try:
            resp = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": cid, "text": text, "parse_mode": "HTML"}, headers=HEADERS, timeout=20)
            if resp.status_code == 429:
                print("Telegram rate limit, waiting 5s and retrying once")
                time.sleep(5)
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": cid, "text": text, "parse_mode": "HTML"}, headers=HEADERS, timeout=20)
        except Exception as e:
            print(f"Telegram fail to {cid}: {e}")

def main():
    existing = get_existing_ids()
    CITIES = [
        {"name": "Chicago", "url": "https://data.cityofchicago.org/resource/ydr8-5enu.json", "desc_field": "work_description", "date_field": "issue_date", "id_field": "permit_", "value_field": "estimated_cost"},
        {"name": "NYC", "url": "https://data.cityofnewyork.us/resource/ipu4-2q9a.json", "desc_field": "job_description", "date_field": "issuance_date", "id_field": "job_filing_number", "value_field": "estimated_job_costs"},
        {"name": "Austin", "url": "https://data.austintexas.gov/resource/3syk-w9eu.json", "desc_field": "description", "date_field": "issued_date", "id_field": "permit_number", "value_field": "total_valuation"},
        {"name": "San Francisco", "url": "https://data.sfgov.org/resource/i98f-2t7q.json", "desc_field": "description", "date_field": "issued_date", "id_field": "permit_number", "value_field": "estimated_cost"},
        {"name": "Seattle", "url": "https://data.seattle.gov/resource/76t5-zv3j.json", "desc_field": "description", "date_field": "issue_date", "id_field": "permit_number", "value_field": "valuation"},
    ]
    all_leads = []
    for c in CITIES:
        all_leads += fetch_city(c)
        time.sleep(1)

    seen = set(); fresh = []
    for l in all_leads:
        if not l["id"] or l["id"] in existing or l["id"] in seen:
            continue
        seen.add(l["id"]); fresh.append(l)

    print(f"FINAL: {len(fresh)} fresh, new, clean leads")
    if not fresh:
        send_telegram("✅ <b>Bot Finished - Auto Run</b>\n0 new fresh leads in last 72h.\nNo duplicates sent. Next check in 6 hours.")
        return

    if SHEET_URL:
        try:
            requests.post(SHEET_URL, json={"leads": fresh}, headers=HEADERS, timeout=25)
            print("Sheet: saved")
        except Exception as e:
            print(f"Sheet post failed, but Telegram will still send: {e}")

    niches_found = []
    for l in fresh:
        if l["niche"] not in niches_found:
            niches_found.append(l["niche"])

    emoji_map = {"ROOFING": "🏠", "SOLAR": "☀️", "GARAGE": "🚗", "KITCHEN REMODEL": "🍳", "BATHROOM REMODEL": "🛁", "ELECTRICAL": "⚡", "PLUMBING": "🔧", "HVAC": "❄️", "FENCE": "🧱", "NEW CONSTRUCTION": "🏗️"}
    for niche in niches_found:
        leads = [x for x in fresh if x["niche"] == niche]
        emoji = emoji_map.get(niche, "🔨")
        for i in range(0, len(leads), 8):
            batch = leads[i:i+8]
            msg = f"{emoji} <b>{niche} LEADS - {len(leads)} Fresh (72h)</b>\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\nFresh, Never Sent Before, With Address + Value\n\n"
            for j, l in enumerate(batch, start=i+1):
                msg += f"<b>{j}. {clean(l['city'])} - {clean(l['address'])}</b>\n📝 {clean(l['desc'])}\n💰 Value: {clean(l['value'])} | 📅 {clean(l['date'])}\n👷 Contractor: {clean(l['contact']) or 'N/A'}\n🆔 {clean(l['id'])}\n\n"
            send_telegram(msg)
    send_telegram(f"✅ <b>Bot Finished - Auto Run</b>\nSent {len(fresh)} NEW fresh leads.\nNo duplicates. Next auto-run in 6 hours.")

if __name__ == "__main__":
    main()
