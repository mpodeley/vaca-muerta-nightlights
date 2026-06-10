#!/usr/bin/env python
"""Tabla de features por POZO × MES para el nowcaster (predecir perforación/fractura del mes con
señal satelital, antes del Cap IV). Universo: pozos con actividad >= 2018 (los modernos de VM).

Features (todas disponibles al instante, sin usar las fechas-label):
  dnb (radiancia VIIRS del mes en la celda del pozo), dnb_base (mediana 12 m previos),
  dnb_anom (cambio = actividad nueva), dnb_prev, dnb_delta, neigh (vecindad 3x3),
  persist12 (meses iluminada en el último año), vnf (flare VIIRS ese año en el radio),
  mes (estacional), operador, area (categóricas).
Labels: y_perf, y_frac (1 si el mes cae en la ventana de perforación/fractura del pozo).

Salida: data/_data/features.csv.gz

    ~/miniforge3/bin/mamba run -n insar python features.py
"""
from __future__ import annotations
import csv, sys, math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
csv.field_size_limit(1 << 24)

VNL = C.RAW / "vnl"
THR = 5.0  # nW para "iluminada" (persistencia)


def ymrange(months):
    return months


def main():
    import numpy as np, rasterio, pandas as pd
    # 1) stack mensual de radiancia
    tifs = sorted(VNL.glob("*.tif"))
    months = [t.stem for t in tifs]
    idx = {m: i for i, m in enumerate(months)}
    with rasterio.open(tifs[0]) as s0:
        tr = s0.transform; H, W = s0.height, s0.width
    stack = np.full((len(tifs), H, W), np.nan, "float32")
    for i, t in enumerate(tifs):
        with rasterio.open(t) as s:
            stack[i] = s.read(1)
    stack = np.where(np.isfinite(stack), stack, 0.0)

    # 2) pozos activos + fractura
    wells = [r for r in csv.DictReader(open(C.RAW / "wells.csv"))
             if r["perf_ini"][:7] >= "2018-01" or r["term_ini"][:7] >= "2018-01"
             or r["perf_fin"][:7] >= "2018-01"]
    frac = {}
    for r in csv.DictReader(open(C.RAW / "frac.csv")):
        frac.setdefault(r["idpozo"], []).append((r["frac_ini"], r["frac_fin"]))

    # 3) VNF por año (puntos)
    vnf_pts = []
    if (C.RAW / "vnf.csv").exists():
        for r in csv.DictReader(open(C.RAW / "vnf.csv")):
            vnf_pts.append((float(r["lon"]), float(r["lat"]), int(float(r["year"]))))

    def vnf_year_set(lon, lat):
        ys = set()
        for vlon, vlat, y in vnf_pts:
            if abs(vlon - lon) < 0.02 and abs(vlat - lat) < 0.02:
                if _hav(lon, lat, vlon, vlat) <= C.MATCH_RADIUS_M:
                    ys.add(y)
        return ys

    def rc(lon, lat):
        c, r = ~tr * (lon, lat)
        return int(r), int(c)

    def in_win(ym, d0, d1):
        if not d0:
            return 0
        d1 = d1 or d0
        return 1 if d0[:7] <= ym <= d1[:7] else 0

    rows = []
    inv = rasterio.transform.rowcol
    for w in wells:
        lon, lat = float(w["lon"]), float(w["lat"])
        r, c = rc(lon, lat)
        if not (0 <= r < H and 0 <= c < W):
            continue
        vy = vnf_year_set(lon, lat)
        series = stack[:, r, c]
        neigh = stack[:, max(r-1, 0):r+2, max(c-1, 0):c+2].mean(axis=(1, 2))
        fr = frac.get(w["idpozo"], [])
        for ym, t in idx.items():
            base = series[max(0, t-12):t]
            base_med = float(np.median(base)) if base.size else 0.0
            persist = int((base > THR).sum())
            dnb = float(series[t]); prev = float(series[t-1]) if t > 0 else 0.0
            yperf = in_win(ym, w["perf_ini"], w["perf_fin"])
            yterm = in_win(ym, w["term_ini"], w["term_fin"])
            yfrac = max((in_win(ym, a, b) for a, b in fr), default=0)
            rows.append({
                "idpozo": w["idpozo"], "ym": ym, "lon": lon, "lat": lat,
                "empresa": w["empresa"], "area": w["area"],
                "dnb": round(dnb, 2), "dnb_base": round(base_med, 2),
                "dnb_anom": round(dnb - base_med, 2), "dnb_prev": round(prev, 2),
                "dnb_delta": round(dnb - prev, 2), "neigh": round(float(neigh[t]), 2),
                "persist12": persist, "vnf": 1 if int(ym[:4]) in vy else 0,
                "mes": int(ym[5:7]), "y_perf": yperf, "y_frac": yfrac, "y_term": yterm})
    df = pd.DataFrame(rows)
    out = C.RAW / "features.csv.gz"
    df.to_csv(out, index=False, compression="gzip")
    print(f"features: {len(df)} filas (pozos {df.idpozo.nunique()}, meses {df.ym.nunique()})")
    print(f"  positivos perf: {df.y_perf.sum()} ({100*df.y_perf.mean():.1f}%)  "
          f"frac: {df.y_frac.sum()} ({100*df.y_frac.mean():.1f}%)  "
          f"term: {df.y_term.sum()} ({100*df.y_term.mean():.1f}%)")
    print(f"persistido: {out}")


def _hav(lo1, la1, lo2, la2):
    R = 6371000.0; p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2-la1); dl = math.radians(lo2-lo1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))


if __name__ == "__main__":
    main()
