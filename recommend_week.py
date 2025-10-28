# recommend_week.py
# Analyse data/occupancy_allego_22kW.csv et produit un rapport 9h–17h.
# - Si des créneaux atteignent le seuil (par défaut 80 %), on les affiche.
# - Sinon, on affiche les 3 meilleurs créneaux observés (plan B), avec % pondéré et n.

import csv
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict

CSV_FILE = "data/occupancy_allego_22kW.csv"
TZ = ZoneInfo("Europe/Paris")

# --- Paramètres d'analyse (tu peux ajuster) ---
START_LOCAL   = time(9, 0)
END_LOCAL     = time(17, 0)
BIN_MINUTES   = 15           # lissage plus large que 10 min
THRESHOLD     = 0.80         # 80 % au lieu de 90 %
MIN_RUN_BINS  = 2            # au moins 30 minutes contiguës (2 x 15)
MIN_SAMPLES_PER_BIN = 1      # le temps d'amorcer l'historique
TOP_K         = 3            # nb de créneaux proposés si < seuil

jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
fmt_hm = lambda h, m: f"{h:02d}:{m:02d}"

def safe_norm_key(k):
    if k is None: return None
    return str(k).lstrip("\ufeff").strip().lower()

def get_ts_from_row(row: dict):
    """Accepte timestamp/timestamp_utc/BOM; sinon 1re colonne non-None."""
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

# 1) Lecture & filtrage (9–17h Europe/Paris)
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
    now_local = datetime.now(TZ)
    print(f"📅 Meilleurs créneaux 22 kW (seuil {int(THRESHOLD*100)} %, {START_LOCAL.strftime('%H:%M')}–{END_LOCAL.strftime('%H:%M')})\n")
    print(f"🕓 Rapport généré le {now_local.strftime('%d/%m/%Y à %H:%M (%Z)')}\n")
    print("Aucune donnée à analyser (vérifie le CSV et/ou la fenêtre horaire).")
    raise SystemExit

# 2) Agrégation par jour & bac
bins_data = defaultdict(lambda: defaultdict(lambda: {"n":0, "ok":0}))
for wd, h, m, a in records:
    d = bins_data[wd][(h, m)]
    d["n"]  += 1
    d["ok"] += 1 if a >= 1 else 0

def merge_and_score(day_bins):
    """Retourne les créneaux contigus >= seuil: [(start,end,p_pond,n_total)]."""
    safe_keys, probs = [], {}
    for (h,m), d in day_bins.items():
        n, ok = d["n"], d["ok"]
        if n == 0: continue
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
    for r in runs:
        if len(r) < MIN_RUN_BINS: continue
        start, end = r[0], r[-1]
        total_n = sum(probs[k][1] for k in r)
        if total_n == 0: continue
        weighted_p = sum(probs[k][0]*probs[k][1] for k in r) / total_n
        merged.append((start, end, weighted_p, total_n))
    return merged

def top_k_runs(day_bins, k=3):
    """Meilleurs créneaux même < seuil, classés par proba pondérée puis n."""
    probs = {}
    for (h,m), d in day_bins.items():
        n = d["n"]
        if n == 0: continue
        p = d["ok"] / n
        probs[(h,m)] = (p, n)
    if not probs:
        return []

    keys = sorted(probs.keys())
    step = BIN_MINUTES
    to_min = lambda hm: hm[0]*60 + hm[1]

    runs, run = [], [keys[0]]
    for cur in keys[1:]:
        if to_min(cur) - to_min(run[-1]) == step:
            run.append(cur)
        else:
            runs.append(run); run = [cur]
    runs.append(run)

    scored = []
    for r in runs:
        if len(r) < MIN_RUN_BINS: continue
        start, end = r[0], r[-1]
        tot = sum(probs[k][1] for k in r)
        if tot == 0: continue
        wp = sum(probs[k][0]*probs[k][1] for k in r) / tot
        scored.append((start, end, wp, tot))

    scored.sort(key=lambda x: (x[2], x[3]), reverse=True)
    return scored[:k]

# 3) Rapport
now_local = datetime.now(TZ)
print(f"📅 Meilleurs créneaux 22 kW (seuil {int(THRESHOLD*100)} %, {START_LOCAL.strftime('%H:%M')}–{END_LOCAL.strftime('%H:%M')})\n")
print(f"🕓 Rapport généré le {now_local.strftime('%d/%m/%Y à %H:%M (%Z)')}\n")

for wd in range(6):  # lundi → samedi
    day_bins = bins_data[wd]
    merged = merge_and_score(day_bins)

    if merged:
        parts = [
            f"{fmt_hm(s[0],s[1])}–{fmt_hm(e[0],e[1])} ({round(p*100)} %) [n={n}]"
            for (s,e,p,n) in merged
        ]
        print(f"{jours[wd]:<10}: " + ", ".join(parts))
    else:
        alt = top_k_runs(day_bins, k=TOP_K)
        if alt:
            parts = [
                f"{fmt_hm(s[0],s[1])}–{fmt_hm(e[0],e[1])} ({round(p*100)} %) [n={n}]"
                for (s,e,p,n) in alt
            ]
            print(f"{jours[wd]:<10}: (meilleurs observés) " + ", ".join(parts))
        else:
            total_measures = sum(d["n"] for d in day_bins.values())
            print(f"{jours[wd]:<10}: aucun créneau exploitable ({total_measures} mesures)")
