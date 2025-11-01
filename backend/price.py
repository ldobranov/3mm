import os
import sys
import json
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

JSON_FILE = os.path.join(os.path.dirname(__file__), "prices.json")
EUR_TO_BGN = 1


def fetch_dam_json():
    """Взима JSON директно от fetch_dam.php през Playwright"""
    url = "https://ibex.bg/Ext/IDM_Homepage/fetch_dam.php?lang=bg"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # първо отваряме сайта, за да инициализираме сесията
        page.goto("https://ibex.bg/")
        page.wait_for_timeout(3000)

        data = page.evaluate(f"""
            async () => {{
                const resp = await fetch("{url}");
                return await resp.json();
            }}
        """)

        browser.close()
        return data


def transform(data, target_date):
    """Трансформира JSON-а от IBEX в нашия формат (BGN + volume)"""
    date_str = target_date.strftime("%Y-%m-%d")
    date_disp = target_date.strftime("%d.%m.%Y")

    records = []
    for entry in data:
        # в JSON има поле "date": "2025-10-05 00:00:00"
        try:
            dt = datetime.strptime(entry["date"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue

        if dt.date() != target_date.date():
            continue

        time_str = dt.strftime("%H:%M:%S")
        price_eur = float(entry.get("price", 0))
        price_bgn = round(price_eur * EUR_TO_BGN, 2)
        volume = float(entry.get("volume", 0))

        rec = {
            "date": date_str,
            "time": time_str,
            "date display": date_disp,
            "price": price_bgn,
            "volume": volume,
        }
        records.append(rec)

    return {date_str: records}


def load_existing_data():
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r") as f:
            return json.load(f)
    return {}


def save_new_rows(transformed):
    existing = load_existing_data()
    for date, rows in transformed.items():
        if not rows:
            print(f"⚠️ Data for {date} not yet available")
            return
        if date not in existing:
            existing[date] = rows
            print(f"✅ Saved {len(rows)} rows for {date}")
        else:
            print(f"✅ Data for {date} already exists")
    with open(JSON_FILE, "w") as f:
        json.dump(existing, f, indent=4, ensure_ascii=False)


def main():
    # по подразбиране взимаме утре
    use_today = "--today" in sys.argv
    target_date = datetime.now() if use_today else datetime.now() + timedelta(days=1)

    print(f"ℹ️ Fetching {'TODAY' if use_today else 'TOMORROW'} prices...")

    raw = fetch_dam_json()
    transformed = transform(raw, target_date)
    save_new_rows(transformed)


if __name__ == "__main__":
    main()


