# recommend_week.py
# Analyse les logs de disponibilité (data/occupancy_allego_22kW.csv)
# et génère un rapport clair des meilleurs créneaux 9h–17h (Europe/Paris)
# avec probabilité moyenne, nombre d'échantillons et date de génération.

import csv
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict

CSV_FILE = "data/occupancy_allego_22kW.csv"
TZ = ZoneInfo("Europe/Paris")

# --- Paramètres d'analyse ---
START_LOCAL   = time(9, 0)
END_LOCAL     = time(17, 0)
BIN_MINUTES   = 10
THRESHOLD     = 0.90
MIN_RUN_BINS  = 2
MIN_SAMPLES_PER_BIN = 3

jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
def fmt_hm(h, m): return f"{h:02d}:{m:02d}"

# --- Lecture robuste du CSV ---
def get_ts_from_row(row):
    """Tolère les fichiers ayant timestamp / timestamp_utc / BOM."""
    norm = {k.lstrip("\ufeff").strip().lower(): k for k in row.keys()}
    for ck in ("timestamp", "timestamp_utc"):
        if ck in norm:
            return row[norm[ck]]
    first_key = next(iter(row))
    return row[first_key]

records = []
with open(CSV_FILE, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        ts_str = get_ts_from_row(row)
        if not ts_str:
            continue
        ts_str = ts_str.replace("Z", "+00:00")
        try:
            ts = datetime.fromisoformat(ts_str)
        except Exception:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_local = ts.astimezone(TZ)

        try:
            a = int(row.get("available", "0").strip())
            t = int(row.get("total", "0").strip())
        except Exception:
            continue
        if t <= 0 or not (START_LOCAL <= ts_local.time() < END_LOCAL):
            continue

        minute_bin = (ts_local.minute // BIN_MINUTES) * BIN_MINUTES
        binned_dt = ts_local.replace(minute=minute_bin, second=0, microsecond=0)
        records.append((ts_local.weekday(), binned_dt.hour, binned_dt.minute, a))

if not records:
    print("Aucune donnée à analyser.")
    raise SystemExit

# --- Agrégation ---
bins_data = defaultdict(lambda: defaultdict(lambda: {"n":0, "ok":0}))
for wd, h, m, a in records:
    d = bins_data[wd][(h, m)]
    d["n"]  += 1
    d["ok"] += 1 if a >= 1 else 0

def merge_and_score(day_bins):
    safe_keys, probs = [], {}
    for (h,m), d in day_bins.items():
        n, ok = d["n"], d["ok"]
        if n == 0: continue
        p = ok / n
        probs[(h,m)] = (p, n)
        if p >= THRESHOLD and n >= MIN_SAMPLES_PER_BIN:
            safe_keys.append((h,m))
    if not safe_keys: return []

    safe_keys.sort()
    step = BIN_MINUTES
    runs, run = [], [safe_keys[0]]
    to_min = lambda h,m: h*60+m

    for cur in safe_keys[1:]:
        if to_min(*cur) - to_min(*run[-1]) == step:
            run.append(cur)
        else:
            runs.append(run); run = [cur]
    runs.append(run)

    merged = []
    for run in runs:
        if len(run) < MIN_RUN_BINS: continue
        start, end = run[0], run[-1]
        total_n = sum(probs[k][1] for k in run)
        weighted_p = sum(probs[k][0]*probs[k][1] for k in run) / total_n
        merged.append((start, end, weighted_p, total_n))
    return merged

# --- Génération du rapport ---
now_local = datetime.now(TZ)
print("📅 Meilleurs créneaux 22 kW (≥ 90 % de chance d’avoir une prise libre, 9h–17h)\n")
print(f"🕓 Rapport généré le {now_local.strftime('%d/%m/%Y à %H:%M (%Z)')}\n")

for wd in range(6):  # lundi à samedi
    day_bins = bins_data[wd]
    merged = merge_and_score(day_bins)
    if not merged:
        total_measures = sum(d["n"] for d in day_bins.values())
        print(f"{jours[wd]:<10}: aucun créneau sûr ({total_measures} mesures)")
        continue
    parts = [
        f"{fmt_hm(s[0],s[1])}–{fmt_hm(e[0],e[1])} ({round(p*100)} %) [n={n}]"
        for (s,e,p,n) in merged
    ]
    print(f"{jours[wd]:<10}: " + ", ".join(parts))
