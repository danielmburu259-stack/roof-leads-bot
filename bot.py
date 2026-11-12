# Roof Leads Bot v2 - Professional
# Source: Government Open Data Portals
# Chicago: data.cityofchicago.org / ydr8-5enu
# Austin: data.austintexas.gov / 3syk-w9eu
# Buyers: Roofing companies. Lead = Fresh permit, verifiable, no contractor yet
import os, requests, json, re
from datetime import datetime, timedelta, timezone

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
SHEET_URL = os.environ.get("SHEET_URL", "").strip()

if not TELEGRAM_TOKEN or not CHAT_ID:
    raise SystemExit("MISSING TELEGRAM_TOKEN or TELEGRAM_CHAT_ID secret")

DAYS_BACK = 14
MAX_PER_CITY = 200
MAX_TOTAL = 30
MIN_VALUE = 3000

ROOF_WORDS = ["roof", "reroof", "re-roof", "re roof", "roofing", "shingle", "tpo", "tear off", "tear-off", "flat roof", "roof replacement", "roof repair"]

CITIES = [
    {
        "name": "Chicago", "domain": "data.cityofchicago.org", "dataset": "ydr8-5enu",
        "date_field": "issue_date",
        "desc_field": "work_description",
        "addr_field": "street_address",
        "value_field": "reported_cost",
        "id_field": "permit_",
        "contact_field": "contact_1_name",
        "contractor_field": "contact_1_type",
    },
    {
        "name": "Austin", "domain": "data.austintexas.gov", "dataset": "3syk-w9eu",
        "date_field": "issueddate",
        "desc_field": "descriptionofwork",
        "addr_field": "originaladdress1",
        "value_field": "valuation",
        "id_field": "permitnumber",
        "contact_field": "applicant",
        "contractor_field": "contractor",
    },
]

def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def is_roof(text):
    t = clean(text).lower()
    return any(w in t for w in ROOF_WORDS)

def parse_value(v):
    try:
        if v is None or str(v).strip() == "":
            return 0
        return float(str(v).replace("$", "").replace(",", "").strip())
    except:
        return 0

def send_telegram(text):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
            timeout=20
        )
        print(f"Telegram: {r.status_code} {r.text[:200]}")
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram EXCEPTION: {e}")
        return False

def send_to_sheet(lead):
    if not SHEET_URL:
        print("No SHEET_URL - skipping sheet")
        return False
    try:
        r = requests.post(SHEET_URL, json=lead, timeout=20)
        print(f"Sheet: {r.status_code} for {lead.get('permit_number')}")
        return r.status_code == 200
    except Exception as e:
        print(f"Sheet EXCEPTION: {e}")
        return False

def fetch_city(city):
    since = (datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")
    where = f"{city['date_field']} >= '{since}'"
    url = f"https://{city['domain']}/resource/{city['dataset']}.json"
    params = {"$where": where, "$order": f"{city['date_field']} DESC", "$limit": MAX_PER_CITY}
    print(f"Fetching {city['name']}: {url} ? {where}")
    try:
        r = requests.get(url, params=params, timeout=30)
        print(f"{city['name']} API status: {r.status_code}")
        if r.status_code != 200:
            print(f"{city['name']} API error body: {r.text[:500]}")
            return []
        data = r.json()
        print(f"{city['name']} got {len(data)} recent permits (last {DAYS_BACK} days)")
    except Exception as e:
        print(f"{city['name']} fetch failed: {e}")
        return []

    leads = []
    seen = set()
    for row in data:
        desc = clean(row.get(city["desc_field"], ""))
        if not desc:
            desc = clean(row.get("permit_type_description", "") or row.get("permit_type", "") or row.get("workclass", ""))
        if not is_roof(desc):
            continue

        value = parse_value(row.get(city["value_field"]))
        if 0 < value < MIN_VALUE:
            continue

        permit_no = clean(row.get(city["id_field"], "")) or clean(row.get("permit_number", "")) or clean(row.get("id", ""))
        if permit_no in seen:
            continue
        seen.add(permit_no)

        address = clean(row.get(city["addr_field"], ""))
        if not address:
            continue

        contractor = clean(row.get(city["contractor_field"], ""))
        has_contractor = bool(contractor) and contractor.lower() not in ["none", "null", "n/a", "owner", "homeowner", "applicant"]
        date_str = clean(row.get(city["date_field"], ""))[:10]
        contact = clean(row.get(city["contact_field"], ""))

        score = 50
        if not has_contractor:
            score += 30
        if value >= 15000:
            score += 20
        elif value >= 8000:
            score += 10
        label = "HOT" if score >= 80 else "WARM" if score >= 60 else "COOL"

        leads.append({
            "city": city["name"],
            "permit_number": permit_no,
            "name": contact if contact else "Not in public record",
            "phone": "Not in public record - lookup by address",
            "address": address,
            "job": desc[:150] or "Roof Work",
            "value": value,
            "contractor": contractor if contractor else "NONE / Unknown",
            "date": date_str,
            "score": label,
            "link": f"https://{city['domain']}/d/{city['dataset']}",
            "source": "Government Open Data - City Permit Portal",
        })
    leads.sort(key=lambda x: (x["score"] != "HOT", x["score"] != "WARM"))
    return leads

def main():
    all_leads = []
    summary = []
    for city in CITIES:
        leads = fetch_city(city)
        summary.append(f"{city['name']}: {len(leads)} roof leads")
        print(f"{city['name']}: {len(leads)} roof leads after filters")
        all_leads.extend(leads)

    to_send = all_leads[:MAX_TOTAL]
    print(f"TOTAL to send: {len(to_send)} / found {len(all_leads)}")

    for lead in to_send:
        value_txt = f"${lead['value']:,.0f}" if lead["value"] > 0 else "Not listed"
        msg = (
            f"🔥 NEW ROOF LEAD - {lead['city'].upper()} - {lead['score']}\n\n"
            f"Permit: {lead['permit_number']}\n"
            f"Name / Applicant: {lead['name']}\n"
            f"Phone: {lead['phone']}\n"
            f"Address: {lead['address']}, {lead['city']}\n"
            f"Job: {lead['job']}\n"
            f"Value: {value_txt}\n"
            f"Date Filed: {lead['date']}\n"
            f"Contractor: {lead['contractor']}\n"
            f"Verify: {lead['link']}\n"
            f"Source: Government Open Data"
        )
        send_telegram(msg)
        send_to_sheet(lead)

    summary_msg = f"✅ Bot Finished - Sent {len(to_send)} leads (found {len(all_leads)})\n" + "\n".join(summary)
    send_telegram(summary_msg)
    print(f"DONE Sent {len(to_send)}")

if __name__ == "__main__":
    main()
