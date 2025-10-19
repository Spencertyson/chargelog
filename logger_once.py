from playwright.sync_api import sync_playwright
import csv
from datetime import datetime, timezone

URL = "https://fr.chargemap.com/carrefour-thionville.html"
CSV_FILE = "data/occupancy_allego_22kW.csv"

def ensure_csv_header():
    import os
    os.makedirs("data", exist_ok=True)
    try:
        with open(CSV_FILE, "x", newline="", encoding="utf-8") as f:
            f.write("timestamp_utc,available,total\n")
    except FileExistsError:
        pass

def extract_type2_counts(text: str):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    total = 0
    available = 0
    for i, ln in enumerate(lines):
        if ln.upper() == "TYPE 2":
            total += 1
            if i + 1 < len(lines) and "disponible" in lines[i+1].lower():
                available += 1
    if total == 0:
        raise RuntimeError("Aucun connecteur TYPE 2 détecté.")
    return available, total

def main():
    ensure_csv_header()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2500)
        for tab in ("Connecteur", "Connecteurs", "Infos", "Information"):
            try:
                page.get_by_role("tab", name=tab, exact=False).click(timeout=800)
                page.wait_for_timeout(300)
            except Exception:
                pass
        full_text = page.locator("body").inner_text()
        a, t = extract_type2_counts(full_text)
        from zoneinfo import ZoneInfo
     ts = datetime.now(ZoneInfo("Europe/Paris")).isoformat()
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([ts, a, t])
        print(f"[{ts}] TYPE 2 dispo : {a}/{t}")
        browser.close()

if __name__ == "__main__":
    main()
