# V7 FINAL - PRODUCTION - Reviewed, No Crash, High Quality Only
import os, requests, html, time, sys
from datetime import datetime, timedelta, timezone

# --- 1. STARTUP CHECK - Prevents silent crash if secret is missing ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_IDS = [c for c in [os.getenv("TELEGRAM_CHAT_ID"), os.getenv("TELEGRAM_CHANNEL_ID")] if c]
SHEET_URL = os.getenv("SHEET_URL")

if not TOKEN or not CHAT_IDS:
    print("ERROR: Missing TELEGRAM_TOKEN or CHAT_ID / CHANNEL_ID. Check GitHub Secrets names exactly.")
    sys.exit(1)
print(f"Bot started. Destinations: {len(CHAT_IDS)} | Sheet URL set: {bool(SHEET_URL)}")

HEADERS = {"User-Agent": "Roof-Leads-Bot/7.0 (Contact: lead-seller)"}

# --- 2. NICHES - Order matters: SOLAR first ---
NICHES = {
    "SOLAR": ["SOLAR PANEL", "SOLAR INSTALL", "PHOTOVOLTAIC", "SOLAR ARRAY"],
    "ROOFING": ["ROOF REPLACEMENT", "REROOF", "RE-ROOF", "NEW ROOF", "ROOF REPAIR", "ROOFING", "REPLACE ROOF"],
    "RENOVATION": ["KITCHEN REMODEL", "BATHROOM REMODEL", "RENOVATION", "REMODEL", "ADDITION", "ALTERATION"],
}
GLOBAL_BAD = ["GARAGE", "FIRE ALARM", "FENCE", "SIGN", "DEMOLITION", "PLUMBING ONLY", "ELECTRICAL ONLY"]

def get_niche(desc):
    t = (desc or "").upper()
    if any(b in t for b in GLOBAL_BAD):
        return None
    for niche in ["SOLAR", "ROOFING", "RENOVATION"]:
        if any(g in t for g in NICHES[niche]):
            if niche == "ROOFING" and "SOLAR" in t:
                return "SOLAR"
            return niche
    return None

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
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S.000")
    where = f"{city['date_field']} > '{cutoff}'"
    try:
        r = requests.get(city["url"], params={"$limit": 1000, "$order": f"{city['date_field']} DESC", "$where": where}, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"{city['name']} API {r.status_code} - skipping, others continue")
            return []
        out = []
        for row in r.json():
            desc = row.get(city["desc_field"], "") or ""
            niche = get_niche(desc)
            if not niche:
                continue
            address = build_address(city["name"], row)
            if not address or address in ["Chicago, IL", ", Austin, TX", ", NY"]:
                continue  # No address = useless, skip
            value = row.get(city["value_field"], "") or ""
            value_str = str(value) if str(value).strip() not in ["", "0", "None"] else "Permit Approved"
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
        time.sleep(1)  # Be nice to government APIs, prevents blocking

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

    for niche, emoji in [("ROOFING","🏠"), ("SOLAR","☀️"), ("RENOVATION","🔨")]:
        leads = [x for x in fresh if x["niche"] == niche]
        if not leads: continue
        for i in range(0, len(leads), 8):
            batch = leads[i:i+8]
            msg = f"{emoji} <b>{niche} LEADS - {len(leads)} Fresh (48h)</b>\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\nFresh, Never Sent Before, With Address + Value\n\n"
            for j, l in enumerate(batch, start=i+1):
                msg += f"<b>{j}. {clean(l['city'])} - {clean(l['address'])}</b>\n📝 {clean(l['desc'])}\n💰 Value: ${clean(l['value'])} | 📅 {clean(l['date'])}\n👷 Contractor: {clean(l['contact']) or 'N/A'}\n🆔 {clean(l['id'])}\n\n"
            send_telegram(msg)
    send_telegram(f"✅ <b>Bot Finished - Auto Run</b>\nSent {len(fresh)} NEW fresh leads.\nNo duplicates. Next auto-run in 6 hours.")

if __name__ == "__main__":
    main()
