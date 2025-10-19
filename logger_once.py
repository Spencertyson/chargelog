# logger_once.py
# Scrute la page Chargemap de "Allego - Carrefour Thionville" une seule fois
# et ajoute une ligne au CSV avec la dispo des prises TYPE 2 (22 kW).
# - Timestamp en Europe/Paris si possible, sinon UTC (fallback).
# - Fichier CSV créé automatiquement dans data/occupancy_allego_22kW.csv

from playwright.sync_api import sync_playwright
import csv
from datetime import datetime, timezone
import os

URL = "https://fr.chargemap.com/carrefour-thionville.html"
CSV_FILE = "data/occupancy_allego_22kW.csv"

def ensure_csv_header():
    """Crée le dossier/data et le CSV avec en-tête si besoin."""
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            f.write("timestamp,available,total\n")

def extract_type2_counts(text: str):
    """
    Dans le texte visible de la page, chaque prise est listée comme :
        TYPE 2
        Disponible / Occupé
        22kW / AC ...
    On compte les blocs 'TYPE 2' et combien sont 'Disponible'.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    total = 0
    available = 0
    for i, ln in enumerate(lines):
        if ln.upper() == "TYPE 2":
            total += 1
            if i + 1 < len(lines) and "disponible" in lines[i + 1].lower():
                available += 1
    if total == 0:
        raise RuntimeError("Aucun connecteur TYPE 2 détecté dans la page rendue.")
    return available, total

def now_iso_paris_or_utc():
    """Timestamp ISO en Europe/Paris si possible, sinon UTC."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Paris")).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()

def main():
    ensure_csv_header()
    ts = now_iso_paris_or_utc()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print(f"[INFO] Surveillance 22 kW sur {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2500)  # laisse le JS charger

        # Essaie d'ouvrir l'onglet "Connecteurs" si présent (sans planter sinon)
        for tab in ("Connecteur", "Connecteurs", "Infos", "Information"):
            try:
                page.get_by_role("tab", name=tab, exact=False).click(timeout=800)
                page.wait_for_timeout(300)
            except Exception:
                pass

        full_text = page.locator("body").inner_text()

        try:
            a, t = extract_type2_counts(full_text)
            print(f"[{ts}] TYPE 2 dispo : {a}/{t}")
            with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([ts, a, t])
        except Exception as e:
            print(f"[ERREUR] {e}")

        browser.close()

if __name__ == "__main__":
    main()
