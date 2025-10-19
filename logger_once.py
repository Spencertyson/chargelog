# logger_once.py
# Scrute la borne Allego - Carrefour Thionville et enregistre la disponibilité des prises 22 kW
# Compatible avec fuseau "Europe/Paris" (fallback UTC si tzdata absent)

from playwright.sync_api import sync_playwright
import csv
from datetime import datetime, timezone
import os

# ---- Paramètres ----
URL = "https://fr.chargemap.com/carrefour-thionville.html"
CSV_FILE = "data/occupancy_allego_22kW.csv"

# ---- Création du CSV si inexistant ----
def ensure_csv_header():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            f.write("timestamp,available,total\n")

# ---- Extraction du nombre de prises TYPE 2 ----
def extract_type2_counts(text: str):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    total = 0
    available = 0
    for i, ln in enumerate(lines):
        if ln.upper() == "TYPE 2":
            total += 1
            if i + 1 < len(lines) and "disponible" in lines[i + 1].lower():
                available += 1
    if total == 0:
        raise RuntimeError("Aucun connecteur TYPE 2 détecté.")
    return available, total

# ---- Fonction principale ----
def main():
    ensure_csv_header()

    # Génération du timestamp : Europe/Paris si dispo, sinon UTC
    try:
        from zoneinfo import ZoneInfo
        ts = datetime.now(ZoneInfo("Europe/Paris")).isoformat()
    except Exception:
        ts = datetime.now(timezone.utc).isoformat()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print(f"[INFO] Surveillance 22 k
