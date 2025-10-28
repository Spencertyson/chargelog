# recommend_week.py
# Analyse data/occupancy_allego_22kW.csv et sort, pour chaque jour (lun→sam),
# les créneaux 9h–17h où P(>=1 prise libre) ≥ 90 %, avec % et n échantillons.
# Tolère les CSV ayant "timestamp", "timestamp_utc" ou un BOM (ï»¿timestamp).

import csv
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict

CSV_FILE = "data/occupancy_allego_22kW.csv"
TZ = ZoneInfo("Europe/Paris")

# Paramètres
START_LOCAL   = time(9, 0)
END_LOCAL     = time(17, 0)
BIN_MINUTES   = 10
THRESHOLD     = 0.90
MIN_RUN_BINS  = 2
MIN_SAMPLES_PER_BIN = 3

jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
def fmt_hm(h, m): return f"{h:02d}:{m:02d}"

def get_ts_from_row(row):
    """Récupère la chaîne de timestamp, quel que soit le nom de colonne."""
    # normalise les clés (strip + lower + retire BOM éventuel)
    norm = {k.lstrip("\ufeff").strip().lower(): k for k in row.keys()}
    cand_keys = ["timestamp", "timestamp_utc"]
    for ck in cand_keys:
        if ck in norm:
            return row[norm[ck]]
    # fallback: prend la première colonne
    first_key = next(iter(row))
    return row[first_key]

records = []
with open(CSV_FILE, newline="", encoding="utf-8") as f:
    r = csv.DictReader(f)
    for row in r:
        ts_s = get_ts_from_row(row)
        if not ts_s:
            continue
        # compat ISO: remplace Z par +00:00
        ts_s = ts_s.replace("Z", "+00:00")
        try:
            ts = datetime.fromisoformat(ts_s)
        except Exception:
            # dernier recours : ignore la ligne si impardonnable
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_local = ts.astimezone(TZ)

        try:
            a = int(row.get("available", "").strip() or 0)
            t = int(row.get("total", "").strip() or 0)
        except Exception:
            continue
        if t <= 0:
            continue
        if not (START_LOCAL <= ts_local.time() < END_LOCAL):
            continue

        minute_bin = (ts_local.minute // BIN_MINUTES) * BIN_MINUTES
        binned_dt = ts_local.replace(minute=minute_bin, second=0, microsecond=0)
        records.append((ts_local.weekday(), binned_dt.hour, binned_dt.minute, a))

if not records:
    print("Aucune donnée à analyser.")
    raise SystemExit

# bins_data[wd][(h,m)] = {"n": N, "ok": OK}
bins_data = defaultdict(lambda: defaultdict(lambda: {"n":0, "ok":0}))
for wd, h, m, a in records:
    d = bins_data[wd][(h, m)]
    d["n"]  += 1
    d["ok"] += 1 if a >= 1 else 0

def merge_and_score(day_bins):
    """Fusionne les bacs contigus et calcule % pondéré et nb d’échantillons."""
    safe_keys = []
    probs = {}
    for (h,m), d in day_bins.items():
        n, ok = d["n"], d["ok"]
        if n == 0:
            continue
        p = ok / n
        probs[(h,m)] = (p, n)
        if p >= THRESHOLD and n >= MIN_SAMPLES_PER_BIN:
            safe_keys.append((h,m))
    if not safe_keys:
        return []

    safe_keys.sort()
    step = BIN_MINUTES
    runs, run = [], [safe_keys[0]]
    def minutes(h,m): return h*60 + m
    for cur in safe_keys[1:]:
        ph, pm = run[-1]
        if minutes(*cur) - minutes(ph, pm) == step:
            run.append(cur)
        else:
            runs.append(run); run = [cur]
    runs.append(run)

    merged = []
    for run in runs:
        if len(run) < MIN_RUN_BINS:
            continue
        start, end = run[0], run[-1]
        total_n = sum(probs[k][1] for k in run)
        if total_n == 0:
            continue
        weighted_p = sum(probs[k][0] * probs[k][1] for k in run) / total_n
        merged.append((start, end, weighted_p, total_n))
    return merged

print("📅 Meilleurs créneaux 22 kW (≥ 90 % de chance d’avoir une prise libre, 9h–17h)\n")

for wd in range(6):  # lundi → samedi
    day_bins = bins_data[wd]
    merged = merge_and_score(day_bins)
    if not merged:
        total_measures = sum(d["n"] for d in day_bins.values())
        print(f"{jours[wd]:<10}: aucun créneau sûr ({total_measures} mesures)")
        continue
    parts = []
    for (h1,m1),(h2,m2),p,tot in merged:
        parts.append(f"{fmt_hm(h1,m1)}–{fmt_hm(h2,m2)} ({round(p*100):d} %) [n={tot}]")
    print(f"{jours[wd]:<10}: " + ", ".join(parts))
