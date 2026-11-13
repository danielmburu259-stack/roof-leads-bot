# Roof Leads Bot v3 - All USA Roofing Permits, Balanced Filter
import os, requests, re
from datetime import datetime, timedelta

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_IDS = [os.getenv("TELEGRAM_CHAT_ID"), os.getenv("TELEGRAM_CHANNEL_ID")]
CHAT_IDS = [c for c in CHAT_IDS if c]
SHEET_URL = os.getenv("SHEET_URL")

# Quality but NOT strict: roof keywords, last 7 days, any value
ROOF_WORDS = ["roof", "reroof", "re-roof", "roofing", "shingle", "rooftop", "roof deck"]
BAD_WORDS = ["demolition", "demo only", "sign", "fence", "plumbing only"]

# All cities with free open permit APIs - if one fails, others still work
CITIES = [
    {"name": "Chicago", "url": "https://data.cityofchicago.org/resource/ydr8-5enu.json", "desc": "work_description", "addr": "address", "date": "issue_date", "id": "permit_", "value": "estimated_cost"},
    {"name": "Austin", "url": "https://data.austintexas.gov/resource/3syk-w9eu.json", "desc": "description", "addr": "original_address1", "date": "issued_date", "id": "permit_number", "value": "total_valuation"},
    {"name": "NYC", "url": "https://data.cityofnewyork.us/resource/ipu4-2q9a.json", "desc": "job_description", "addr": "house_no", "date": "issuance_date", "id": "job_filing_number", "value": "estimated_job_costs"},
    {"name": "Denver", "url": "https://denvergov.org/opendata/dataset/0d8c9e5e-9f2c-4e6d-8b9a-9a1e5e5e5e5e", "desc": "description", "addr": "address", "date": "issued_date", "id": "permit_number", "value": "valuation"},
]

def is_roof(text):
    t = (text or "").lower()
    if any(b in t for b in BAD_WORDS):
        return False
    return any(w in t for w in ROOF_WORDS)

def fetch_city(city):
    try:
        # Last 7 days to get volume, not just 24h
        r = requests.get(city["url"], params={"$limit": 500, "$order": f"{city['date']} DESC"}, timeout=30)
        if r.status_code != 200:
            print(f"{city['name']} API {r.status_code}")
            return []
        leads = []
        for row in r.json():
            desc = row.get(city["desc"], "")
            if not is_roof(desc):
                continue
            leads.append({
                "city": city["name"],
                "id": str(row.get(city["id"], "")),
                "address": row.get(city["addr"], "") or row.get("address", "") or row.get("street_address", ""),
                "desc": desc[:120],
                "date": str(row.get(city["date"], ""))[:10],
                "value": row.get(city["value"], "N/A"),
            })
            if len(leads) >= 30:
                break
        print(f"{city['name']}: {len(leads)} roof leads")
        return leads
    except Exception as e:
        print(f"{city['name']} error: {e}")
        return []

def send_telegram(text):
    for cid in CHAT_IDS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                data={"chat_id": cid, "text": text, "parse_mode": "HTML"}, timeout=20)
        except Exception as e:
            print(f"Telegram to {cid} failed: {e}")

def send_to_sheet(leads):
    if not SHEET_URL:
        return
    try:
        requests.post(SHEET_URL, json={"leads": leads}, timeout=20)
        print(f"Sheet: sent {len(leads)}")
    except Exception as e:
        print(f"Sheet failed: {e}")

def main():
    all_leads = []
    for c in CITIES:
        all_leads.extend(fetch_city(c))
    # De-dupe by city + permit id + address
    seen = set()
    uniq = []
    for l in all_leads:
        k = (l["city"], l["id"], l["address"])
        if k not in seen:
            seen.add(k)
            uniq.append(l)
    print(f"TOTAL: {len(uniq)} unique roof leads")
    if not uniq:
        send_telegram("✅ <b>Bot Finished</b>\nSent 0 leads (found 0)\nNo new roofing permits in last 7 days from checked cities. Will retry tomorrow.")
        return
    send_to_sheet(uniq)
    # Send in batches of 10 so Telegram does not block
    for i in range(0, len(uniq), 10):
        batch = uniq[i:i+10]
        msg = f"🏠 <b>ROOFING LEADS - {len(uniq)} Found</b>\n📅 {datetime.now().strftime('%Y-%m-%d')}\n\n"
        for j, l in enumerate(batch, start=i+1):
            msg += f"<b>{j}. {l['city']} - {l['address']}</b>\n📝 {l['desc']}\n💰 Value: {l['value']} | 📅 {l['date']}\n🆔 {l['id']}\n\n"
        send_telegram(msg)
    send_telegram(f"✅ <b>Bot Finished</b>\nSent {len(uniq)} leads to Sheet + Telegram (DM + Channel)")

if __name__ == "__main__":
    main()
