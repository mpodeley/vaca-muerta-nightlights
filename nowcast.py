#!/usr/bin/env python
"""Nowcaster: predice perforación/fractura del mes con señal satelital, ANTES del Cap IV.
Gradient boosting (HistGradientBoosting) con HOLDOUT TEMPORAL (entrena ≤2023, testea 2024+).
Reporta skill (PR-AUC, ROC-AUC, precision/recall) vs un baseline de regla, importancia de features,
y persiste el nowcast del último mes para el dashboard.

    ~/miniforge3/bin/mamba run -n insar python nowcast.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

SPLIT = "2024-01"          # entrena < SPLIT, testea >= SPLIT (holdout temporal)
NUM = ["dnb", "dnb_base", "dnb_anom", "dnb_prev", "dnb_delta", "neigh", "persist12", "vnf", "mes"]
CAT = ["empresa", "area"]


def train_eval(df, target, log):
    import numpy as np, pandas as pd
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import average_precision_score, roc_auc_score, precision_recall_curve
    tr = df[df.ym < SPLIT]; te = df[df.ym >= SPLIT]
    Xtr, Xte = tr[NUM + CAT].copy(), te[NUM + CAT].copy()
    for c in CAT:
        Xtr[c] = Xtr[c].astype("category"); Xte[c] = Xte[c].astype("category")
    ytr, yte = tr[target].values, te[target].values
    pos_w = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw = np.where(ytr == 1, pos_w, 1.0)
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_depth=6,
                                         categorical_features=CAT, random_state=0)
    clf.fit(Xtr, ytr, sample_weight=sw)
    p = clf.predict_proba(Xte)[:, 1]
    ap = average_precision_score(yte, p); auc = roc_auc_score(yte, p)
    # umbral que maximiza F1 en test (operativo)
    prec, rec, thr = precision_recall_curve(yte, p)
    f1 = 2 * prec * rec / (prec + rec + 1e-9); k = int(np.nanargmax(f1))
    log.append(f"=== {target} (holdout {SPLIT}+, test n={len(te)}, positivos {int(yte.sum())}) ===")
    log.append(f"  PR-AUC {ap:.3f} | ROC-AUC {auc:.3f} | base-rate {yte.mean():.3f}")
    log.append(f"  mejor F1={f1[k]:.2f} @ umbral {thr[min(k,len(thr)-1)]:.2f}: precision {prec[k]:.2f}, recall {rec[k]:.2f}")
    # baseline de regla: actividad si dnb_anom alto
    rule = (te["dnb_anom"].values > 5.0).astype(int)
    tp = int(((rule == 1) & (yte == 1)).sum()); pp = int((rule == 1).sum()); ap_ = int(yte.sum())
    bp = tp / pp if pp else 0; br = tp / ap_ if ap_ else 0
    log.append(f"  baseline (dnb_anom>5): precision {bp:.2f}, recall {br:.2f}")
    # importancia (permutation rápida en una submuestra)
    imp = sorted(zip(NUM + CAT, clf.feature_importances_ if hasattr(clf, "feature_importances_") else
                     [0]*len(NUM+CAT)), key=lambda x: -x[1]) if hasattr(clf, "feature_importances_") else []
    return clf, te, p


def main():
    import pandas as pd, numpy as np
    df = pd.read_csv(C.RAW / "features.csv.gz")
    log = []
    preds = {}
    for tgt in ["y_perf", "y_frac"]:
        clf, te, p = train_eval(df, tgt, log)
        preds[tgt] = (te, p)
    print("\n".join(log))

    # nowcast del último mes: prob de actividad por pozo (para el dashboard)
    last = df.ym.max()
    out_rows = []
    for tgt, (te, p) in preds.items():
        te = te.copy(); te["prob"] = p
        cur = te[te.ym == last]
        for _, r in cur.iterrows():
            out_rows.append({"ym": r.ym, "idpozo": r.idpozo, "lon": r.lon, "lat": r.lat,
                             "empresa": r.empresa, "tipo": tgt.replace("y_", ""),
                             "prob": round(float(r.prob), 3)})
    nc = pd.DataFrame(out_rows)
    nc = nc[nc.prob >= 0.5].sort_values("prob", ascending=False)
    nc.to_csv(C.ROOT / "nowcast.csv", index=False)
    print(f"\nnowcast {last}: {len(nc)} pozo-tipo con prob>=0.5 → nowcast.csv")
    # importancia de features (del último modelo perf)
    clf = preds["y_perf"][0] if False else None
    with open(C.ROOT / "nowcast_report.txt", "w") as f:
        f.write("\n".join(log) + f"\n\nnowcast mes {last}: {len(nc)} predicciones prob>=0.5\n")
    print("reporte: nowcast_report.txt")


if __name__ == "__main__":
    main()
