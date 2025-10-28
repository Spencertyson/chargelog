# heatmap_week.py
# Génère une heatmap PNG (Europe/Paris) montrant, pour LUN→SAM entre 09:00–17:00,
# la probabilité d'avoir >= 1 prise TYPE 2 libre, par pas de 15 minutes.

import csv
import math
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")  # rendu hors-écran pour GitHub Actions
import matplotlib.pyplot as plt
import numpy as np
import os

CSV_FILE = "data/occupancy_allego_22kW.csv"
OUT_PNG  = "heatmap_week.png"

TZ = ZoneInfo("Europe/Paris")

# Paramètres d'analyse
START_LOCAL   = time(9, 0)
END_LOCAL     = time(17, 0)
BIN_MINUTES   = 15                     # résolution (colonnes)
SLOTS_PER_DAY = int((8*60) / BIN_MINUTES)  # 9h→17h = 8h -> 32 colonnes

jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]

def safe_norm_key(k):
    if k is None: return None
    return str(k).lstrip("\ufeff").strip().lower()

def get_ts_from_row(row: dict):
    # accepte "timestamp", "timestamp_utc" (avec BOM toléré),
    # sinon prend la première colonne non None
    norm = {}
    for k in row.keys():
        nk = safe_norm_key(k)
        if nk is not None:
            norm[nk] = k
    for ck in ("timestamp", "timestamp_utc"):
        if ck in norm:
            return row.get(norm[ck])
    first_key = next((k for k in row.keys() if k is not None), None)
    return row.get(first_key) if first_key is not None else None

def to_int_or_zero(v) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return 0

# 1) Lire & binner
# success[wd][slot] = nb de fois a>=1
# total[wd][slot]   = nb de mesures
success = [ [0]*SLOTS_PER_DAY for _ in range(7) ]
total   = [ [0]*SLOTS_PER_DAY for _ in range(7) ]

rows_total = 0
rows_parsed = 0

if not os.path.exists(CSV_FILE):
    # crée un PNG informatif
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.text(0.5, 0.5, "Aucune donnée (CSV introuvable)", ha="center", va="center")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150)
    raise SystemExit("CSV introuvable")

with open(CSV_FILE, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows_total += 1
        ts_s = get_ts_from_row(row)
        if not ts_s:
            continue
        ts_s = str(ts_s).replace("Z", "+00:00")
        try:
            ts = datetime.fromisoformat(ts_s)
        except Exception:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_local = ts.astimezone(TZ)
        rows_parsed += 1

        a = to_int_or_zero(row.get("available"))
        t = to_int_or_zero(row.get("total"))
        if t <= 0:
            continue
        # fenêtre 9–17
        if not (START_LOCAL <= ts_local.time() < END_LOCAL):
            continue

        # calcule l'index de colonne (slot de 15 min depuis 09:00)
        minutes_since_start = (ts_local.hour - 9)*60 + ts_local.minute
        slot = minutes_since_start // BIN_MINUTES
        if slot < 0 or slot >= SLOTS_PER_DAY:
            continue

        wd = ts_local.weekday()  # 0=lundi
        success[wd][slot] += 1 if a >= 1 else 0
        total[wd][slot]   += 1

# 2) Construire la matrice de probabilités (LUN→SAM, 6 lignes)
M = np.full((6, SLOTS_PER_DAY), np.nan, dtype=float)
for wd in range(6):  # lundi→samedi
    for s in range(SLOTS_PER_DAY):
        n = total[wd][s]
        ok = success[wd][s]
        if n > 0:
            M[wd, s] = ok / n

# 3) S'il n'y a rien, produire un PNG informatif
if np.all(np.isnan(M)):
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.text(0.5, 0.6, "Aucune mesure 9–17h (Europe/Paris)\nVérifie la collecte ou attends plus de données.",
            ha="center", va="center")
    ax.text(0.5, 0.3, f"CSV lignes: {rows_total} | parsées: {rows_parsed}",
            ha="center", va="center", fontsize=9)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150)
    raise SystemExit("Pas de données exploitables pour 9–17h.")

# 4) Affichage heatmap
# Masquer NaN (cases sans données)
masked = np.ma.masked_invalid(M)

fig_h = 6   # hauteur en pouces
fig_w = 14  # largeur (nombre de colonnes)
fig, ax = plt.subplots(figsize=(fig_w, fig_h))

# imshow sans préciser de cmap (palette par défaut)
im = ax.imshow(masked, aspect="auto", interpolation="nearest", vmin=0.0, vmax=1.0)

# Ticks Y (jours)
ax.set_yticks(range(6))
ax.set_yticklabels(jours[:6])

# Ticks X (toutes les heures : 09:00, 10:00, ..., 17:00)
xticks = []
xticklabels = []
for col in range(SLOTS_PER_DAY):
    minutes = col * BIN_MINUTES
    hh = 9 + minutes // 60
    mm = minutes % 60
    if mm == 0:  # on n'étiquette que les heures pleines
        xticks.append(col)
        xticklabels.append(f"{hh:02d}:00")
ax.set_xticks(xticks)
ax.set_xticklabels(xticklabels, rotation=0)

# Titres
now_local = datetime.now(TZ)
title = ("Heatmap disponibilité TYPE 2 (≥1 prise libre) — 09:00–17:00\n"
         f"Généré le {now_local.strftime('%d/%m/%Y à %H:%M (%Z)')}")
ax.set_title(title)

# Colorbar
cbar = fig.colorbar(im, ax=ax)
cbar.set_label("Probabilité d'avoir ≥ 1 prise libre")

# Légende sous-graphique
fig.text(0.01, 0.01, f"Source: {CSV_FILE} | pas={BIN_MINUTES} min | lignes CSV: {rows_total}, parsées: {rows_parsed}",
         ha="left", va="bottom", fontsize=8)

fig.tight_layout()
fig.savefig(OUT_PNG, dpi=150)

# 5) En plus : copie avec nom ISO semaine (archive)
iso = now_local.isocalendar()  # (year, week, weekday)
arch = f"heatmap_{iso[0]}-W{iso[1]:02d}.png"
try:
    import shutil
    shutil.copyfile(OUT_PNG, arch)
except Exception:
    pass
print(f"Heatmap écrite: {OUT_PNG} et {arch}")
