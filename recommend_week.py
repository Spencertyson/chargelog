# recommend_week.py
# Résume, pour chaque jour (lun→sam) entre 9h–17h, les créneaux où
# P(>=1 prise libre) ≥ 90 %, avec % pondéré et nombre d'échantillons.
# Tolère en-têtes irréguliers (BOM, colonnes None, timestamp/timestamp_utc).

import csv
from datetime import datetime, time, timezone
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
fmt_hm = lambda h, m: f"{h:02d}:{m:02d}"

def safe_norm_key(k):
    if k is None:
        return None
    return str(k).lstrip("\ufeff").strip().lower()

def get_ts_from_row(row: dict) -> str | None:
    """Retourne la valeur de timestamp (timestamp/timestamp_utc), sinon 1re colonne non None."""
    # map normalisée -> clé réelle
    norm = {}
    for k in row.keys():
        nk = safe_norm_key(k)
        if nk is not None:
            norm[nk] = k
    for ck in ("timestamp", "timestamp_utc"):
        if ck in norm:
            return row.get(norm[ck])
    # fallback: première clé non None
    first_key = next((k for k in row.keys() if k is not None), None)
    return row.get(first_key) if first_key is not None else None

def to_int_or_zero(v) -> int:
    if v is None:
        return 0
    try:
        return int(str(v).strip() or "0")
    except Exception:
        return 0

# 1) Lecture & filtrage
records = []
with open(CSV_FILE, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
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

        a = to_int_or_zero(row.get("available"))
        t = to_int_or_zero(row.get("total"))
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

# 2) Agrégation par jour et bac
bins_data = defaultdict(lambda: defaultdict(lambda: {"n":0, "ok":0}))
for wd, h, m, a in records:
    d = bins_data[wd][(h, m)]
    d["n"]  += 1
    d["ok"] += 1 if a >= 1 else 0

def merge_and_score(day_bins):
    """Fusionne bacs contigus ≥ seuil, renvoie [(start,end,prob,n_total)]."""
    safe_keys, probs = [], {}
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
    to_min = lambda hm: hm[0]*60 + hm[1]
    runs, run = [], [safe_keys[0]]
    for cur in safe_keys[1:]:
        if to_min(cur) - to_min(run[-1]) == step:
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

# 3) Rapport
now_local = datetime.now(TZ)
print("📅 Meilleurs créneaux 22 kW (≥ 90 % de chance d’avoir une prise libre, 9h–17h)\n")
print(f"🕓 Rapport généré le {now_local.strftime('%d/%m/%Y à %H:%M (%Z)')}\n")

for wd in range(6):  # lundi → samedi
    day_bins = bins_data[wd]
    merged = merge_and_score(day_bins)
    if not merged:
        total_measures = sum(d["n"] for d in day_bins.values())
        print(f"{jours[wd]:<10}: aucun créneau sûr ({total_measures} mesures)")
        continue
    parts = [
        f"{fmt_hm(s[0],s[1])}–{fmt_hm(e[0],e[1])} ({round(p*100)} %) [n={n}]"
        for (s, e, p, n) in merged
    ]
    print(f"{jours[wd]:<10}: " + ", ".join(parts))
