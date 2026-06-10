#!/usr/bin/env python
"""Nowcaster con CASCADE de fallback por frescura de dato.

El nowcast fresco (2025-26) es el más valioso pero el que menos features tiene: el survey VNF es anual
y no existe aún para esos años. Entrenamos dos tiers y, en inferencia, cada mes usa el más alto cuyas
features estén disponibles:
  T1 "completo"  = todas las features (incluye VNF)         → meses con VNF (≈≤2024)
  T2 "reciente"  = mismas features SIN vnf                  → meses con DNB pero sin VNF (2025-26)

Holdout temporal (≤2023 train, 2024+ test). Reporta skill por tier/objetivo → cuánto cuesta la frescura.
Persiste nowcast.csv (último mes) con columna tier+prob.

    ~/miniforge3/bin/mamba run -n insar python nowcast.py
"""
from __future__ import annotations
import csv, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

SPLIT = "2024-01"
CAT = ["empresa", "area"]
NUM_T1 = ["dnb", "dnb_base", "dnb_anom", "dnb_prev", "dnb_delta", "neigh", "persist12", "vnf", "mes"]
NUM_T2 = [c for c in NUM_T1 if c != "vnf"]            # tier reciente: sin VNF


def vnf_years():
    p = C.RAW / "vnf.csv"
    if not p.exists():
        return set()
    return {int(float(r["year"])) for r in csv.DictReader(open(p))}


def fit(df, target, num, log, tier):
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import average_precision_score, roc_auc_score
    tr = df[df.ym < SPLIT]; te = df[df.ym >= SPLIT]
    Xtr, Xte = tr[num + CAT].copy(), te[num + CAT].copy()
    for c in CAT:
        Xtr[c] = Xtr[c].astype("category"); Xte[c] = Xte[c].astype("category")
    ytr, yte = tr[target].values, te[target].values
    sw = np.where(ytr == 1, (len(ytr) - ytr.sum()) / max(ytr.sum(), 1), 1.0)
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_depth=6,
                                         categorical_features=CAT, random_state=0)
    clf.fit(Xtr, ytr, sample_weight=sw)
    p = clf.predict_proba(Xte)[:, 1]
    ap, auc = average_precision_score(yte, p), roc_auc_score(yte, p)
    log.append(f"  [{tier}] {target}: ROC-AUC {auc:.3f} | PR-AUC {ap:.3f} (base {yte.mean():.3f})")
    return clf, auc, ap


def main():
    import pandas as pd
    df = pd.read_csv(C.RAW / "features.csv.gz")
    vy = vnf_years()
    log = ["=== Skill por tier (holdout 2024+) — costo de la frescura ==="]
    models = {}
    skill = {}
    for tgt in ["y_perf", "y_frac"]:
        models[("T1", tgt)], a1, p1 = fit(df, tgt, NUM_T1, log, "T1 completo")
        models[("T2", tgt)], a2, p2 = fit(df, tgt, NUM_T2, log, "T2 sin-VNF")
        skill[tgt] = {"T1": (a1, p1), "T2": (a2, p2)}
        log.append(f"      → caída ROC-AUC por perder VNF: {a1-a2:+.3f}")
    print("\n".join(log))

    # inferencia cascade: cada mes usa el tier más alto disponible
    last = df.ym.max()
    cur = df[df.ym == last].copy()
    year = int(last[:4])
    tier = "T1" if year in vy else "T2"
    num = NUM_T1 if tier == "T1" else NUM_T2
    out_rows = []
    for tgt in ["y_perf", "y_frac"]:
        X = cur[num + CAT].copy()
        for c in CAT:
            X[c] = X[c].astype("category")
        cur["prob"] = models[(tier, tgt)].predict_proba(X)[:, 1]
        for _, r in cur[cur.prob >= 0.5].iterrows():
            out_rows.append({"ym": r.ym, "idpozo": int(r.idpozo), "lon": r.lon, "lat": r.lat,
                             "empresa": r.empresa, "tipo": tgt.replace("y_", ""),
                             "prob": round(float(r.prob), 3), "tier": tier})
    nc = pd.DataFrame(out_rows).sort_values("prob", ascending=False)
    nc.to_csv(C.ROOT / "nowcast.csv", index=False)
    print(f"\nnowcast {last} (tier {tier}{' — sin VNF' if tier=='T2' else ''}): "
          f"{len(nc)} pozo-tipo con prob>=0.5 → nowcast.csv")

    with open(C.ROOT / "nowcast_report.txt", "w") as f:
        f.write("\n".join(log))
        f.write(f"\n\nVNF disponible para años: {sorted(vy)}\n")
        f.write(f"nowcast del mes {last}: tier {tier}, {len(nc)} predicciones prob>=0.5\n")
    print("reporte: nowcast_report.txt")


if __name__ == "__main__":
    main()
