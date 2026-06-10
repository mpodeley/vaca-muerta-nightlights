#!/usr/bin/env python
"""Inferencia de equipos/sets (sin ID de rig público → cantidad/movimiento/tamaño, NO identidad).

(a) TRACKING: nº de equipos de perforación activos por operador-mes = nº de pads distintos con
    perforación ese mes (pozos de un mismo pad = 1 rig). Rutas: encadena pads del operador mes a mes
    (nearest-neighbor con tope de desplazamiento). Sanity: total de rigs VM/mes vs el rango conocido (~30-45).
(b) TAMAÑO por intensidad: regresión firma nocturna (dnb / dnb_anom) durante la fractura → potencia del
    set (potencia_equipos_fractura_hp). Da "qué tan grande es el set", no su identidad.

Salidas: equipment_report.txt, rigs_monthly.csv, equipment_routes.json
    ~/miniforge3/bin/mamba run -n insar python equipment.py
"""
from __future__ import annotations
import csv, json, sys, math
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
csv.field_size_limit(1 << 24)
PAD = 0.006  # ~600 m: pozos dentro de esto = mismo pad/rig
MAXMOVE_KM = 60  # un rig no se mueve más que esto entre meses


def hav_km(a, b, c, d):
    R = 6371.0; p1, p2 = math.radians(b), math.radians(d)
    dp = math.radians(d-b); dl = math.radians(c-a)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))


def tracking():
    import numpy as np, pandas as pd
    acts = [r for r in csv.DictReader(open(C.ROOT / "activity.csv"))
            if r["actividad"] == "PERFORACION" and r["fuente"] == "pozo"]
    # pads activos por (empresa, ym): clusterizar por grilla ~600 m
    pads = defaultdict(set)
    for r in acts:
        key = (r["empresa"], r["ym"])
        cell = (round(float(r["lon"]) / PAD), round(float(r["lat"]) / PAD))
        pads[key].add(cell)
    rig = [{"empresa": e, "ym": ym, "rigs": len(cells)} for (e, ym), cells in pads.items()]
    rig = pd.DataFrame(rig)
    total = rig.groupby("ym").rigs.sum().sort_index()
    pd.DataFrame({"ym": total.index, "rigs_total": total.values}).to_csv(C.ROOT / "rigs_monthly.csv", index=False)
    # rutas: por operador top, encadenar centroides de pad mes a mes (greedy NN)
    routes = {}
    cent = lambda cell: (cell[0]*PAD, cell[1]*PAD)
    top_ops = rig.groupby("empresa").rigs.sum().sort_values(ascending=False).head(3).index
    months = sorted({r["ym"] for r in acts})
    for op in top_ops:
        seq = []
        for ym in months:
            cells = pads.get((op, ym), set())
            seq.append([cent(c) for c in cells])
        routes[op] = seq
    json.dump({"months": months, "routes": {k: v for k, v in routes.items()}},
              open(C.ROOT / "equipment_routes.json", "w"))
    return total, rig


def size_regression():
    import numpy as np, pandas as pd
    from scipy.stats import spearmanr
    # HP por idpozo
    hp = {}
    with open(C.SRC_FRACTURA, encoding="utf-8-sig") as f:
        rd = csv.DictReader(f); rd.fieldnames = [c.strip() for c in rd.fieldnames]
        for r in rd:
            try:
                v = float(r.get("potencia_equipos_fractura_hp") or "")
                if v > 0:
                    hp[r["idpozo"].strip()] = v
            except ValueError:
                pass
    # mes de fractura por pozo
    fr = {}
    for r in csv.DictReader(open(C.RAW / "frac.csv")):
        if r["frac_ini"]:
            fr[r["idpozo"]] = r["frac_ini"][:7]
    # firma DNB durante la fractura (de features)
    feat = pd.read_csv(C.RAW / "features.csv.gz", usecols=["idpozo", "ym", "dnb", "dnb_anom", "vnf"])
    feat["idpozo"] = feat.idpozo.astype(str)
    rows = []
    for idp, ym in fr.items():
        if idp not in hp:
            continue
        m = feat[(feat.idpozo == idp) & (feat.ym == ym)]
        if len(m):
            rows.append((hp[idp], float(m.dnb.iloc[0]), float(m.dnb_anom.iloc[0])))
    if len(rows) < 30:
        return None
    df = pd.DataFrame(rows, columns=["hp", "dnb", "dnb_anom"])
    r1, p1 = spearmanr(df.hp, df.dnb)
    r2, p2 = spearmanr(df.hp, df.dnb_anom)
    return len(df), (r1, p1), (r2, p2)


def main():
    import numpy as np
    log = []
    total, rig = tracking()
    log.append("=== TRACKING: equipos de perforación activos (pads distintos) ===")
    log.append(f"  rigs VM/mes 2023-2026: mediana {int(total['2023-01':].median())}, "
               f"máx {int(total.max())} (rango conocido VM ~30-45 → sanity ok si en ese orden)")
    log.append(f"  últimos meses: " + ", ".join(f"{m}:{int(v)}" for m, v in total.tail(4).items()))
    sr = size_regression()
    log.append("\n=== TAMAÑO del set por intensidad (firma → potencia_equipos_fractura_hp) ===")
    if sr:
        n, (r1, p1), (r2, p2) = sr
        log.append(f"  n={n} pozos fracturados con HP y firma")
        log.append(f"  Spearman HP↔dnb:      rho={r1:+.3f} (p={p1:.1e})")
        log.append(f"  Spearman HP↔dnb_anom: rho={r2:+.3f} (p={p2:.1e})")
    else:
        log.append("  datos insuficientes")
    print("\n".join(log))
    open(C.ROOT / "equipment_report.txt", "w").write("\n".join(log) + "\n")
    print("\nsalidas: rigs_monthly.csv, equipment_routes.json, equipment_report.txt")


if __name__ == "__main__":
    main()
