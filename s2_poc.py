#!/usr/bin/env python
"""POC Sentinel-2: ¿se detecta el pad a 10 m en estepa árida? Para N pozos perforados en 2023-2024,
compara composite PRE (verano 2020-21) vs POST (verano 2024-25) y mide, en el pozo vs un anillo de
fondo (~1 km), el cambio de: NDVI, brillo (B02+B03+B04), MNDWI (B03,B11=agua/piletas), BSI (suelo).
Si el pad despeja vegetación/compacta, post-pre en el pozo difiere del fondo.

    ~/miniforge3/bin/mamba run -n insar python s2_poc.py
"""
from __future__ import annotations
import csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

N = 25


def comp(cat, bbox, t0, t1):
    import odc.stac, numpy as np
    s = cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=f"{t0}/{t1}",
                   query={"eo:cloud_cover": {"lt": 25}})
    items = list(s.items())
    if not items:
        return None
    ds = odc.stac.load(items, bands=["B02", "B03", "B04", "B08", "B11", "SCL"], bbox=bbox,
                       resolution=10, chunks={})
    clear = ~ds.SCL.isin([3, 8, 9, 10])
    md = lambda b: (ds[b].where(clear)).median("time")
    b2, b3, b4, b8, b11 = [md(b).astype("float32") for b in ["B02", "B03", "B04", "B08", "B11"]]
    ndvi = (b8 - b4) / (b8 + b4 + 1e-6)
    bright = (b2 + b3 + b4) / 3.0
    mndwi = (b3 - b11) / (b3 + b11 + 1e-6)
    bsi = ((b11 + b4) - (b8 + b2)) / ((b11 + b4) + (b8 + b2) + 1e-6)
    return {"ndvi": ndvi, "bright": bright, "mndwi": mndwi, "bsi": bsi}


def main():
    import planetary_computer as pc, pystac_client, numpy as np
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=pc.sign_inplace)
    fr = {r["idpozo"]: r for r in csv.DictReader(open(C.RAW / "frac.csv"))}
    wells = [r for r in csv.DictReader(open(C.RAW / "wells.csv"))
             if r["perf_ini"][:4] in ("2023", "2024") and "BANDURRIA" in r["area"]][:N]
    print(f"probando {len(wells)} pozos (perf 2023-24, Bandurria)\n")
    agg = {k: [] for k in ["ndvi", "bright", "mndwi", "bsi"]}
    for w in wells:
        lon, lat = float(w["lon"]), float(w["lat"]); d = 0.01
        bbox = [lon-d, lat-d, lon+d, lat+d]
        pre = comp(cat, bbox, "2020-12-01", "2021-03-15")
        post = comp(cat, bbox, "2024-12-01", "2025-03-15")
        if not pre or not post:
            continue
        # pixel del pozo (centro) vs fondo (mediana del chip)
        def at_center(da):
            yc, xc = da.shape[0] // 2, da.shape[1] // 2
            return float(da[yc-1:yc+2, xc-1:xc+2].mean())
        row = {}
        for k in agg:
            dpad = at_center(post[k].values) - at_center(pre[k].values)
            dbg = float(np.nanmedian(post[k].values) - np.nanmedian(pre[k].values))
            row[k] = dpad - dbg  # cambio en el pad relativo al fondo
            agg[k].append(row[k])
        print(f"{w['sigla'][:22]:22s}  dNDVI {row['ndvi']:+.3f}  dBrillo {row['bright']:+.0f}  "
              f"dMNDWI {row['mndwi']:+.3f}  dBSI {row['bsi']:+.3f}")
    print("\n=== MEDIANA del cambio pad-vs-fondo (post−pre) ===")
    for k, v in agg.items():
        if v:
            v = np.array(v)
            print(f"  {k:7s}  mediana {np.median(v):+.3f}  | |·|>ruido en {(np.abs(v)>(0.03 if k!='bright' else 200)).mean()*100:.0f}% pozos")


if __name__ == "__main__":
    main()
