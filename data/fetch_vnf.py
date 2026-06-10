#!/usr/bin/env python
"""VIIRS Nightfire (VNF) — survey anual global de flares de EOG (eogdata.mines.edu, descarga pública,
distinta de la ruta nighttime_light que pide login). Detección de combustión calibrada: lat/lon,
temperatura (K), volumen flared (BCM/año), frecuencia. Filtra al AOI → data/_data/vnf.csv.

detect.py ya consume vnf.csv (rama detect_vnf): cada flare anual se replica a los 12 meses del año
(flaring persistente) con vnf_flag=1, temp y rhi(=BCM).

    ~/miniforge3/bin/mamba run -n insar python data/fetch_vnf.py
"""
from __future__ import annotations
import io, re, sys
from pathlib import Path
import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C

PAGE = "https://eogdata.mines.edu/products/vnf/global_gas_flare.html"
H = {"User-Agent": "Mozilla/5.0"}
YEARS = range(2019, 2026)   # 2025/2026 si están publicados; se saltean si no


def year_urls() -> dict:
    html = requests.get(PAGE, headers=H, timeout=60).text
    urls = re.findall(r"https://eogdata\.mines\.edu/global_flare_data/[^\"' ]*\.xlsx", html)
    out = {}
    for u in urls:
        m = re.search(r"_((?:19|20)\d{2})_", u) or re.search(r"_((?:19|20)\d{2})", u)
        if m:
            out.setdefault(int(m.group(1)), u)
    return out


def pick(cols, *keys):
    for c in cols:
        cl = c.lower()
        if all(k in cl for k in keys):
            return c
    return None


def main() -> None:
    urls = year_urls()
    rows = []
    for y in YEARS:
        if y not in urls:
            print(f"  {y}: sin archivo publicado")
            continue
        r = requests.get(urls[y], headers=H, timeout=300)
        if r.status_code != 200 or "sheet" not in r.headers.get("content-type", ""):
            print(f"  {y}: descarga falló ({r.status_code})")
            continue
        df = pd.read_excel(io.BytesIO(r.content))
        lo, la = pick(df.columns, "lon"), pick(df.columns, "lat")
        bcm = pick(df.columns, "bcm"); tmp = pick(df.columns, "temp"); freq = pick(df.columns, "detection")
        typ = pick(df.columns, "type")
        if not (lo and la):
            print(f"  {y}: sin lat/lon"); continue
        m = df[(df[lo] >= C.WEST) & (df[lo] <= C.EAST) & (df[la] >= C.SOUTH) & (df[la] <= C.NORTH)].copy()
        for _, x in m.iterrows():
            rows.append({"lon": round(float(x[lo]), 6), "lat": round(float(x[la]), 6), "year": y,
                         "temp_bb": round(float(x[tmp]), 1) if tmp and pd.notna(x[tmp]) else "",
                         "rhi": round(float(x[bcm]), 6) if bcm and pd.notna(x[bcm]) else "",
                         "bcm": round(float(x[bcm]), 6) if bcm and pd.notna(x[bcm]) else "",
                         "type": (str(x[typ]) if typ and pd.notna(x[typ]) else "")})
        print(f"  {y}: {len(m)} flares en AOI")
    if not rows:
        sys.exit("0 flares — revisar acceso a EOG global_flare_data.")
    out = pd.DataFrame(rows, columns=["lon", "lat", "year", "temp_bb", "rhi", "bcm", "type"])
    out.to_csv(C.RAW / "vnf.csv", index=False)
    print(f"persistido: {C.RAW/'vnf.csv'}  ({len(out)} flares-año, {out.year.nunique()} años)")


if __name__ == "__main__":
    main()
