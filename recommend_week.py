# recommend_week.py
# Résume, pour chaque jour (lun→sam) et entre 9h–17h, les créneaux où
# la probabilité d'avoir >= 1 prise libre dépasse un seuil (par défaut 90%).
# Affiche chaque créneau fusionné avec : heure début–fin (XX %) [n=échantillons].

import csv
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict

CSV_FILE = "data/occupancy_allego_22kW.csv"
TZ = ZoneInfo("Europe/Paris")

# --- Paramètres ajustables ---
START_LOCAL   = time(9, 0)
END_LOCAL     = time(17, 0)
BIN_MINUTES   = 10          # doit correspondre à ta fréquence de log
THRESHOLD     = 0.90        # 90%
MIN_RUN_BINS  = 2           # au moins 20 min (2 bacs de 10 min)
MIN_SAMPLES_PER_BIN = 3     # fiabilité minimale par bac

jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]

def fmt_hm(h, m): return f"{h:02d}:{m:02d}"

# 1) Lecture et filtrage 9–17h (heure locale)
records = []
with open(CSV_FILE, newline="", encoding="utf-8") as f:
    r = csv.DictReader(f)
    for row in r:
        ts = datetime.fromisoformat(row["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_local = ts.astimezone(TZ)

        a = int(row["available"])
        t = int(row["total"])
        if t <= 0: 
            continue
        if not (START_LOCAL <= ts_local.time() < END_LOCAL):
            continue

        # arrondi au pas BIN_MINUTES
        minute_bin = (ts_local.minute // BIN_MINUTES) * BIN_MINUTES
        binned_dt = ts_local.replace(minute=minute_bin, second=0, microsecond=0)
        records.append((ts_local.weekday(), binned_dt.hour, binned_dt.minute, a))

if not records:
    print("Aucune donnée à analyser.")
    raise SystemExit

# 2) Agrégation par jour et bac (compte total + succès >=1 prise libre)
#    bins_data[wd][(h,m)] = {"n": N, "ok": OK}
bins_data = defaultdict(lambda: defaultdict(lambda: {"n":0, "ok":0}))
for wd, h, m, a in records:
    d = bins_data[wd][(h, m)]
    d["n"]  += 1
    d["ok"] += 1 if a >= 1 else 0

def merge_and_score(day_bins):
    """
    day_bins: dict {(h,m): {"n": N, "ok": OK}}
    Retourne une liste de créneaux fusionnés:
      [( (h1,m1), (h2,m2), avg_prob, total_samples )]
    où avg_prob est la moyenne P pondérée par N de chaque bac.
    """
    # 2.1 sélectionne les bacs « sûrs » (p >= THRESHOLD et n >= MIN_SAMPLES_PER_BIN)
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

    # 2.2 fusionne les bacs contigus (pas = BIN_MINUTES)
    safe_keys.sort()
    step = BIN_MINUTES
    runs = []
    run = [safe_keys[0]]
    def minutes(h,m): return h*60 + m

    for cur in safe_keys[1:]:
        ph, pm = run[-1]
        if minutes(*cur) - minutes(ph, pm) == step:
            run.append(cur)
        else:
            runs.append(run)
            run = [cur]
    runs.append(run)

    # 2.3 garde les runs d’au moins MIN_RUN_BINS et calcule score pondéré
    merged = []
    for run in runs:
        if len(run) < MIN_RUN_BINS:
            continue
        start, end = run[0], run[-1]
        # moyenne pondérée par n
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
        print(f"{jours[wd]:<10}: aucun créneau sûr ({sum(d['n'] for d in day_bins.values())} mesures)")
        continue
    parts = []
    for (h1,m1),(h2,m2),p,tot in merged:
        parts.append(f"{fmt_hm(h1,m1)}–{fmt_hm(h2,m2)} ({round(p*100):d} %) [n={tot}]")
    print(f"{jours[wd]:<10}: " + ", ".join(parts))
