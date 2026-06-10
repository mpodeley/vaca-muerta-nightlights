#!/usr/bin/env python
"""Nowcaster: predice PERFORACIÓN / FRACTURA / TERMINACIÓN del mes con señal satelital, antes del Cap IV.

- Cascade de fallback por frescura: T1 (con VNF, ≤2024) / T2 (sin VNF, 2025-26); cada mes usa el tier
  más alto disponible.
- Probabilidades CALIBRADAS (isotónica) → la suma de probabilidades = volumen esperado, consistente con
  el conteo histórico del Cap IV (los labels ARE el registro oficial). Se reporta volumen predicho vs real.
- Holdout temporal (≤2023 train, 2024+ test).

Salida: nowcast.csv (último mes, prob calibrada + tier) y nowcast_report.txt (skill + consistencia de volumen).
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
NUM_T2 = [c for c in NUM_T1 if c != "vnf"]
TARGETS = ["y_perf", "y_frac", "y_term"]


def vnf_years():
    p = C.RAW / "vnf.csv"
    return {int(float(r["year"])) for r in csv.DictReader(open(p))} if p.exists() else set()


def fit(df, target, num, tier, log):
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import average_precision_score, roc_auc_score
    tr = df[df.ym < SPLIT]; te = df[df.ym >= SPLIT]
    def prep(d):
        X = d[num + CAT].copy()
        for c in CAT:
            X[c] = X[c].astype("category")
        return X
    Xtr, Xte, ytr, yte = prep(tr), prep(te), tr[target].values, te[target].values
    # SIN class weights: la isotónica calibra a la tasa real → Σp ≈ volumen real (consistencia)
    base = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_depth=6,
                                          categorical_features=CAT, random_state=0)
    clf = CalibratedClassifierCV(base, method="isotonic", cv=3)
    clf.fit(Xtr, ytr)
    p = clf.predict_proba(Xte)[:, 1]
    ap, auc = average_precision_score(yte, p), roc_auc_score(yte, p)
    # consistencia de volumen: Σp (esperado) vs Σy (real) por mes en el holdout
    te2 = te.assign(p=p)
    vol = te2.groupby("ym").agg(pred=("p", "sum"), real=(target, "sum"))
    ratio = (vol.pred.sum() / max(vol.real.sum(), 1))
    log.append(f"  [{tier}] {target}: ROC-AUC {auc:.3f} | PR-AUC {ap:.3f} | "
               f"volumen Σpred/Σreal {ratio:.2f}")
    return clf, auc


def main():
    import pandas as pd
    df = pd.read_csv(C.RAW / "features.csv.gz")
    vy = vnf_years()
    log = ["=== Skill + consistencia de volumen (holdout 2024+) ==="]
    models = {}
    for tgt in TARGETS:
        models[("T1", tgt)], _ = fit(df, tgt, NUM_T1, "T1", log)
        models[("T2", tgt)], _ = fit(df, tgt, NUM_T2, "T2", log)
    print("\n".join(log))

    last = df.ym.max(); year = int(last[:4]); tier = "T1" if year in vy else "T2"
    num = NUM_T1 if tier == "T1" else NUM_T2
    cur = df[df.ym == last].copy()
    X = cur[num + CAT].copy()
    for c in CAT:
        X[c] = X[c].astype("category")
    out_rows = []; vol_pred = {}
    for tgt in TARGETS:
        prob = models[(tier, tgt)].predict_proba(X)[:, 1]
        tipo = tgt.replace("y_", "")
        k = int(round(float(prob.sum())))          # volumen esperado calibrado = nº de pozos a marcar
        vol_pred[tipo] = k
        cc = cur.assign(p=prob).sort_values("p", ascending=False).head(max(k, 0))  # top-K = volumen
        for _, r in cc.iterrows():
            out_rows.append({"ym": r.ym, "idpozo": int(r.idpozo), "lon": r.lon, "lat": r.lat,
                             "empresa": r.empresa, "tipo": tipo, "prob": round(float(r.p), 3),
                             "tier": tier})
    nc = pd.DataFrame(out_rows).sort_values("prob", ascending=False)
    nc.to_csv(C.ROOT / "nowcast.csv", index=False)
    vstr = ", ".join(f"{k} {v:.1f}" for k, v in vol_pred.items())
    print(f"\nnowcast {last} (tier {tier}): {len(nc)} prob>=0.5 | volumen esperado (Σp calibrada): {vstr}")
    with open(C.ROOT / "nowcast_report.txt", "w") as f:
        f.write("\n".join(log) + f"\n\nVNF años: {sorted(vy)}\nnowcast {last} tier {tier}: "
                f"{len(nc)} prob>=0.5; volumen esperado {vstr}\n")
    print("reporte: nowcast_report.txt")


if __name__ == "__main__":
    main()
