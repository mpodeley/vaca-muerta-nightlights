#!/usr/bin/env python
"""Sentinel-2 (10 m) change-detection PRE→POST sobre el core de actividad: muestra el DESPEJE DE PAD
(brillo↑, NDVI↓) que VIIRS (500 m) no resuelve. Composite de verano (mediana, enmascarando nubes)
para PRE (2019-21) y POST (2024-25). Salidas:
  data/_data/s2_change_bright.tif   (POST−PRE brillo, 10 m)
  docs/assets/s2_change.png         (overlay coloreado para el dashboard)
  data/_data/s2_pad.csv             (magnitud de despeje por pozo activo en el bbox)

    ~/miniforge3/bin/mamba run -n insar python data/fetch_s2.py
"""
from __future__ import annotations
import csv, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C

# lecturas de COG remotos resilientes a baches de red de Planetary Computer
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
os.environ.setdefault("GDAL_HTTP_TIMEOUT", "120")
os.environ.setdefault("VSI_CACHE", "TRUE")

# core denso (Bandurria / Loma Campana / Añelo); ~ -68.95..-68.45 , -38.45..-38.08
BBOX = (-68.98, -38.46, -68.42, -38.06)
PRE = ("2019-12-01", "2021-03-31")
POST = ("2024-12-01", "2025-03-31")
RES = 10
RES_DEG = 10 / 111320   # ~10 m en grados; crs+resolution FIJOS → PRE y POST en la MISMA grilla 4326


def composite(cat, t0, t1, max_scenes=80):
    import odc.stac, numpy as np, dask
    items = list(cat.search(collections=["sentinel-2-l2a"], bbox=BBOX, datetime=f"{t0}/{t1}",
                            query={"eo:cloud_cover": {"lt": 30}}).items())
    # cap a las menos nubladas: acota la memoria del median temporal sin perder calidad
    items = sorted(items, key=lambda it: it.properties.get("eo:cloud_cover", 100))[:max_scenes]
    ds = odc.stac.load(items, bands=["B02", "B03", "B04", "B08", "SCL"], bbox=BBOX,
                       crs="EPSG:4326", resolution=RES_DEG,   # grilla fija → PRE y POST alinean
                       chunks={"x": 1024, "y": 1024}, groupby="solar_day",
                       fail_on_error=False)   # un COG flaky → nodata, no aborta toda la mediana
    clear = ~ds.SCL.isin([3, 8, 9, 10])
    # baseline ≥04.00 (post 2022-01-25) trae offset +1000 DN en reflectancia → harmonizar al viejo
    off = 1000.0 if t0 >= "2022-01-25" else 0.0
    md = lambda b: (ds[b].where(clear) - off).clip(min=0).median("time")
    b2, b3, b4, b8 = md("B02"), md("B03"), md("B04"), md("B08")
    bright = ((b2 + b3 + b4) / 3.0).astype("float32")
    ndvi = ((b8 - b4) / (b8 + b4 + 1e-6)).astype("float32")
    with dask.config.set(scheduler="threads", num_workers=2):
        return bright.compute(), ndvi.compute(), len(items)


def main():
    import planetary_computer as pc, pystac_client, numpy as np, rasterio
    from rasterio.transform import from_bounds
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=pc.sign_inplace)
    print("PRE…"); preB, preV, n0 = composite(cat, *PRE)
    print(f"  {n0} escenas"); print("POST…"); postB, postV, n1 = composite(cat, *POST)
    print(f"  {n1} escenas")
    dB = (postB - preB)                      # despeje de pad: brillo sube
    H, W = dB.shape
    tr = from_bounds(BBOX[0], BBOX[1], BBOX[2], BBOX[3], W, H)
    arr = dB.values
    with rasterio.open(C.RAW / "s2_change_bright.tif", "w", driver="GTiff", height=H, width=W,
                       count=1, dtype="float32", crs="EPSG:4326", transform=tr,
                       compress="deflate") as o:
        o.write(arr, 1)
    # PNG overlay: solo aumentos de brillo (pads nuevos) en rojo-amarillo, transparente lo demás.
    # Decimar a ~2000 px de lado para que el asset web no pese (full-res 10m = ~47 MB).
    step = max(1, round(max(W, H) / 2000))
    sub = arr[::step, ::step]
    vmax = float(np.nanpercentile(sub[np.isfinite(sub)], 99)) or 500
    norm = np.clip(sub / vmax, 0, 1)
    cmap = matplotlib.colormaps["inferno"]
    rgba = cmap(norm); rgba[..., 3] = np.clip((norm - 0.15) * 1.5, 0, 0.9)  # transparente si poco cambio
    plt.imsave(C.SITE_ASSETS / "s2_change.png", rgba)
    # muestreo por pozo activo dentro del bbox
    inv = ~tr
    rows = []
    for r in csv.DictReader(open(C.RAW / "wells.csv")):
        lon, lat = float(r["lon"]), float(r["lat"])
        if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]):
            continue
        c, rr = inv * (lon, lat); c, rr = int(c), int(rr)
        if 0 <= rr < H and 0 <= c < W:
            v = float(np.nanmean(arr[max(rr-1,0):rr+2, max(c-1,0):c+2]))
            rows.append({"idpozo": r["idpozo"], "lon": round(lon,6), "lat": round(lat,6),
                         "empresa": r["empresa"], "perf_ini": r["perf_ini"],
                         "s2_pad_bright": round(v, 1)})
    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_csv(C.RAW / "s2_pad.csv", index=False)
    # auto-validación: tras harmonizar, el FONDO debe dar ~0 y los pads despejados ENTRE épocas
    # (drillados 2022-2024, aparecen recién en POST) deben dar ΔBrillo fuerte positivo.
    fin = int(np.isfinite(arr).sum())
    bg = float(np.nanmedian(arr))
    df["yr"] = pd.to_datetime(df["perf_ini"], errors="coerce").dt.year
    btw = df[df.yr.between(2022, 2024)].s2_pad_bright       # pad nuevo entre PRE y POST
    pre = df[df.yr <= 2018].s2_pad_bright                   # pad ya existía en PRE → sin cambio
    print(f"raster {W}x{H} @10m | finitos={fin}/{arr.size} | pozos muestreados: {len(rows)}")
    print(f"ΔBrillo: fondo(raster)={bg:+.0f} | pad drillado 2022-24={btw.mean():+.0f} (n={btw.notna().sum()}) "
          f"| pad pre-2019={pre.mean():+.0f} (n={pre.notna().sum()})")
    print(f"  s2_change_bright.tif, s2_change.png, s2_pad.csv")


if __name__ == "__main__":
    main()
