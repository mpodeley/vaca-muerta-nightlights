#!/usr/bin/env python
"""Nowcaster: predice PERFORACIÓN / FRACTURA / TERMINACIÓN del mes con señal satelital, antes del Cap IV.

- Cascade de fallback por frescura: T1 (con VNF, ≤2024) / T2 (sin VNF, 2025-26); cada mes usa el tier
  más alto disponible.
- Probabilidades CALIBRADAS (isotónica) → la suma de probabilidades = volumen esperado, consistente con
  el conteo histórico del Cap IV (los labels ARE el registro oficial). Se reporta volumen predicho vs real.
- Holdout temporal (≤2023 train, 2024+ test).

Salida: nowcast.csv (toda la cola laggeada NOWCAST_START..último, prob calibrada + tier) y
        nowcast_report.txt (skill + consistencia de volumen).
    ~/miniforge3/bin/mamba run -n insar python nowcast.py
"""
from __future__ import annotations
import csv, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

SPLIT = "2024-01"
COMPLETE_END = "2025-01"   # meses < esto = ya reportados sin lag → miden el sesgo de volumen del modelo
NOWCAST_START = "2025-01"  # desde acá scoreamos cada mes para suplir la cola laggeada del Cap IV
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
    # sesgo de volumen medido SOLO en meses completos (sin lag) → evita circularidad con la cola
    te2 = te.assign(p=p)
    comp = te2[te2.ym < COMPLETE_END]
    ratio = (comp.p.sum() / max(comp[target].sum(), 1))
    log.append(f"  [{tier}] {target}: ROC-AUC {auc:.3f} | PR-AUC {ap:.3f} | "
               f"Σpred/Σreal(completos) {ratio:.2f}")
    return clf, ratio


def main():
    import pandas as pd
    df = pd.read_csv(C.RAW / "features.csv.gz")
    vy = vnf_years()
    log = ["=== Skill + consistencia de volumen (holdout 2024+) ==="]
    models = {}; ratios = {}
    for tgt in TARGETS:
        models[("T1", tgt)], ratios[("T1", tgt)] = fit(df, tgt, NUM_T1, "T1", log)
        models[("T2", tgt)], ratios[("T2", tgt)] = fit(df, tgt, NUM_T2, "T2", log)
    print("\n".join(log))

    # scoreamos CADA mes de la cola (NOWCAST_START..last): el Cap IV de esos meses está incompleto
    # por el lag, y el satélite ya los ve → el nowcast los suple. Volumen de-sesgado con el ratio de
    # meses completos para que el suplemento no herede el sobre/sub-pronóstico del modelo.
    tail = sorted(m for m in df.ym.unique() if m >= NOWCAST_START)
    out_rows = []; vol_last = {}
    for m in tail:
        year = int(m[:4]); tier = "T1" if year in vy else "T2"
        num = NUM_T1 if tier == "T1" else NUM_T2
        cur = df[df.ym == m].copy()
        X = cur[num + CAT].copy()
        for c in CAT:
            X[c] = X[c].astype("category")
        for tgt in TARGETS:
            tipo = tgt.replace("y_", "")
            prob = models[(tier, tgt)].predict_proba(X)[:, 1]
            k = int(round(float(prob.sum()) / max(ratios[(tier, tgt)], 1e-6)))  # volumen de-sesgado
            cc = cur.assign(p=prob).sort_values("p", ascending=False).head(max(k, 0))
            if m == tail[-1]:
                vol_last[tipo] = k
            for _, r in cc.iterrows():
                out_rows.append({"ym": r.ym, "idpozo": int(r.idpozo), "lon": r.lon, "lat": r.lat,
                                 "empresa": r.empresa, "tipo": tipo, "prob": round(float(r.p), 3),
                                 "tier": tier})
    nc = pd.DataFrame(out_rows).sort_values(["ym", "prob"], ascending=[True, False])
    nc.to_csv(C.ROOT / "nowcast.csv", index=False)
    last = tail[-1]; ltier = "T1" if int(last[:4]) in vy else "T2"
    vstr = ", ".join(f"{k} {v}" for k, v in vol_last.items())
    print(f"\nnowcast {tail[0]}..{last}: {len(nc)} filas en {len(tail)} meses | "
          f"último mes {last} (tier {ltier}) volumen de-sesgado: {vstr}")
    with open(C.ROOT / "nowcast_report.txt", "w") as f:
        f.write("\n".join(log) + f"\n\nVNF años: {sorted(vy)}\ncola scoreada: {tail[0]}..{last} "
                f"({len(tail)} meses, {len(nc)} filas)\núltimo mes {last} tier {ltier} "
                f"volumen de-sesgado: {vstr}\n")
    print("reporte: nowcast_report.txt")


if __name__ == "__main__":
    main()
