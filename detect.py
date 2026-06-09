#!/usr/bin/env python
"""Convierte la huella nocturna VIIRS en detecciones mensuales puntuales.

VNL (data/_data/vnl/<ym>.tif): umbral por anomalía sobre el fondo rural -> clusters -> centroides.
VNF (data/_data/vnf.csv): sitios de combustión (flares) -> puntos con temperatura; si el survey es
anual, se replica a los meses de ese año.

Salida: data/_data/detections.csv  (ym, lon, lat, vnl_brillo, vnf_flag, vnf_temp, vnf_rhi)
Corre aunque falten datos (avisa y produce 0 filas) — el resto del pipeline lo tolera.

    ~/miniforge3/bin/mamba run -n insar python detect.py
"""
from __future__ import annotations
import csv, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

VNL_DIR = C.RAW / "vnl"
VNF_CSV = C.RAW / "vnf.csv"
OUT = C.RAW / "detections.csv"
# Umbral VNL: nW/cm²/sr por encima del fondo rural (calibrar con validate.py)
VNL_THRESH = 5.0


def detect_vnl() -> list[dict]:
    rows = []
    if not VNL_DIR.exists() or not list(VNL_DIR.glob("*.tif")):
        return rows
    import numpy as np, rasterio
    from rasterio.windows import from_bounds
    from scipy import ndimage
    for tif in sorted(VNL_DIR.glob("*.tif")):
        ym = tif.stem
        with rasterio.open(tif) as src:
            try:
                win = from_bounds(C.WEST, C.SOUTH, C.EAST, C.NORTH, src.transform)
                a = src.read(1, window=win)
                tr = src.window_transform(win)
            except Exception:
                a = src.read(1); tr = src.transform
        a = np.where(np.isfinite(a), a, 0.0)
        base = np.nanmedian(a[a > 0]) if (a > 0).any() else 0.0
        mask = a > (base + VNL_THRESH)
        lab, n = ndimage.label(mask)
        if not n:
            continue
        coms = ndimage.center_of_mass(a, lab, range(1, n + 1))
        peaks = ndimage.maximum(a, lab, range(1, n + 1))
        for (r, c), pk in zip(coms, peaks):
            lon, lat = tr * (c + 0.5, r + 0.5)
            if C.in_aoi(lon, lat):
                rows.append({"ym": ym, "lon": round(lon, 6), "lat": round(lat, 6),
                             "vnl_brillo": round(float(pk), 2), "vnf_flag": 0,
                             "vnf_temp": "", "vnf_rhi": ""})
    return rows


def detect_vnf() -> list[dict]:
    rows = []
    if not VNF_CSV.exists():
        return rows
    with open(VNF_CSV, newline="") as f:
        for r in csv.DictReader(f):
            try:
                lon = float(r.get("lon") or r.get("Longitude") or r.get("longitude"))
                lat = float(r.get("lat") or r.get("Latitude") or r.get("latitude"))
            except (TypeError, ValueError):
                continue
            if not C.in_aoi(lon, lat):
                continue
            ym = (r.get("ym") or "").strip()
            temp = r.get("temp_bb") or r.get("Temp_BB") or ""
            rhi = r.get("rhi") or r.get("RHI") or ""
            yms = [ym] if ym else _year_months(r.get("year") or r.get("Year") or "")
            for y in yms:
                rows.append({"ym": y, "lon": round(lon, 6), "lat": round(lat, 6),
                             "vnl_brillo": "", "vnf_flag": 1, "vnf_temp": temp, "vnf_rhi": rhi})
    return rows


def _year_months(year: str) -> list[str]:
    try:
        y = int(str(year)[:4])
    except ValueError:
        return []
    return [f"{y:04d}-{m:02d}" for m in range(1, 13)]


def main() -> None:
    rows = detect_vnl() + detect_vnf()
    cols = ["ym", "lon", "lat", "vnl_brillo", "vnf_flag", "vnf_temp", "vnf_rhi"]
    with open(OUT, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=cols); wr.writeheader(); wr.writerows(rows)
    if not rows:
        print("0 detecciones — faltan datos VIIRS (corré data/fetch_eog.py con credencial EOG).")
    else:
        nv = sum(r["vnf_flag"] for r in rows)
        print(f"detecciones: {len(rows)}  (VNF/flares: {nv}, VNL/luces: {len(rows)-nv})")
    print(f"persistido: {OUT}")


if __name__ == "__main__":
    main()
