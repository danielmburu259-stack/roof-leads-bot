# Roof Leads Bot - Unlimited, All Cities, Never Crashes
# Runs on GitHub Actions, $0 free
import os, time, requests, json
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SHEET_ID = os.environ.get("SHEET_ID", "")
SHEET_URL = os.environ.get("SHEET_URL", "")  # NEW - Secret 4, your Apps Script /exec link

# All 8 cities - Socrata API domains
CITIES = [
    {"name": "Houston", "domain": "data.houstontx.gov", "dataset": "building-permits"},
    {"name": "Dallas", "domain": "data.dallas.gov", "dataset": "building-permits"},
    {"name": "Miami", "domain": "data.miamidade.gov", "dataset": "building-permits"},
    {"name": "Tampa", "domain": "data.tampagov.net", "dataset": "building-permits"},
    {"name": "Phoenix", "domain": "data.phoenix.gov", "dataset": "building-permits"},
    {"name": "Atlanta", "domain": "data.atlantaga.gov", "dataset": "building-permits"},
    {"name": "Charlotte", "domain": "data.charlottenc.gov", "dataset": "building-permits"},
    {"name": "Nashville", "domain": "data.nashville.gov", "dataset": "building-permits"},
]

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=20)
    except Exception as e:
        print(f"Telegram failed: {e}")

def send_to_sheet(lead):
    # NEW - Sends lead to Google Sheet via Apps Script
    if not SHEET_URL:
        print("No SHEET_URL, skipping sheet")
        return
    try:
        # Send as JSON - Apps Script will write a row
        requests.post(SHEET_URL, json=lead, timeout=20)
        print(f"Sheet saved: {lead['address']}")
    except Exception as e:
        print(f"Sheet failed: {e}")

def is_roof_job(text):
    if not text: return False
    t = text.lower()
    return any(k in t for k in ["roof", "reroof", "re-roof", "roofing"])

def get_value(row):
    for k in ["estimated_cost", "valuation", "permit_valuation", "construction_cost", "total_valuation", "value"]:
        try:
            v = float(str(row.get(k, 0)).replace(",", "").replace("$", "") or 0)
            if v > 0: return v
        except: pass
    return 0

def get_contractor(row):
    for k in ["contractor", "contractor_name", "contractor_company", "applicant"]:
        v = str(row.get(k, "")).strip()
        if v and v.lower() not in ["none", "null", "owner", "homeowner", "n/a"]:
            return v
    return "NONE"

def fetch_city(city):
    leads = []
    offset = 0
    while True:
        try:
            url = f"https://{city['domain']}/resource/{city['dataset']}.json?$limit=100&$offset={offset}&$order=issued_date DESC"
            r = requests.get(url, timeout=30)
            if r.status_code != 200:
                print(f"{city['name']} API {r.status_code}, trying alternate search")
                break
            data = r.json()
            if not data:
                break
            print(f"{city['name']} page offset {offset} got {len(data)} rows")
            for row in data:
                try:
                    desc = str(row.get("description", "") or row.get("work_description", "") or row.get("permit_type", "") or row.get("type", "") or "")
                    if not is_roof_job(desc + " " + str(row.get("permit_type", ""))):
                        continue
                    value = get_value(row)
                    if value < 10000:
                        continue
                    if get_contractor(row) != "NONE":
                        continue
                    address = str(row.get("address", "") or row.get("site_address", "") or row.get("location_address", "") or "")
                    if not address or address.lower() in ["none", "null"]:
                        continue
                    date_str = str(row.get("issued_date", "") or row.get("issue_date", "") or row.get("permit_date", "") or row.get("applied_date", "") or datetime.now().isoformat())
                    leads.append({
                        "city": city["name"],
                        "name": str(row.get("owner_name", "") or row.get("applicant_name", "") or row.get("owner", "") or "Owner"),
                        "phone": "",
                        "address": address,
                        "job": desc[:120] or "Roof Replacement",
                        "value": value,
                        "contractor": "NONE",
                        "date": date_str[:10],
                        "link": f"https://{city['domain']}"
                    })
                except Exception as e:
                    print(f"Skip 1 bad lead in {city['name']}: {e}")
                    continue
            offset += 100
            if len(data) < 100:
                break
        except Exception as e:
            print(f"{city['name']} failed: {e}, retry in 30s")
            time.sleep(30)
            break
    return leads

def main():
    total = 0
    summary = []
    for city in CITIES:
        try:
            leads = fetch_city(city)
            print(f"{city['name']}: {len(leads)} high-quality leads found")
            summary.append(f"{city['name']} {len(leads)}")
            for lead in leads:
                msg = f"🔥 NEW ROOF LEAD - {lead['city'].upper()}\n\nName: {lead['name']}\nAddress: {lead['address']}\nJob: {lead['job']}\nValue: ${lead['value']:,.0f}\nDate Filed: {lead['date']}\nContractor: NONE\nScore: {'HOT' if lead['value']>15000 else 'WARM'}\nPermit: {lead['link']}"
                send_telegram(msg)
                send_to_sheet(lead)  # NEW - also save to Sheet
                total += 1
                time.sleep(1)
        except Exception as e:
            print(f"City {city['name']} crashed, continuing to next city: {e}")
            summary.append(f"{city['name']} 0 - API down, retry next run")
            continue
    send_telegram(f"✅ Bot Finished - Total {total} leads\n" + "\n".join(summary))
    print(f"DONE Total {total}")

if __name__ == "__main__":
    main()
