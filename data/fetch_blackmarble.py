#!/usr/bin/env python
"""Capa satelital de luz nocturna vía NASA Black Marble (VIIRS VNP46A3, mensual ~500 m), usando
credenciales Earthdata (~/.netrc) — alternativa robusta a EOG (cuyo auth migró a flujo de código).

Por cada mes de la ventana: busca VNP46A3 sobre el AOI, baja los tiles, extrae la radiancia DNB
mensual corregida (NearNadir_Composite_Snow_Free), mosaica, recorta al bbox → data/_data/vnl/<ym>.tif
(nW/cm²/sr). detect.py lo consume tal cual.

    ~/miniforge3/bin/mamba run -n insar python data/fetch_blackmarble.py [--start YYYY-MM --end YYYY-MM]
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C

SUBDS = "NearNadir_Composite_Snow_Free"     # radiancia DNB mensual; alterna AllAngle_Composite_Snow_Free
GRID = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields"
DL = C.RAW / "bm"
VNL = C.RAW / "vnl"


def months(s, e):
    y, m = int(s[:4]), int(s[5:7]); ey, em = int(e[:4]), int(e[5:7])
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m > 12:
            m = 1; y += 1


def tile_transform(h, v):
    import rasterio
    west = h * 10 - 180; north = 90 - v * 10
    return rasterio.transform.from_origin(west, north, 10/2400, 10/2400)


def read_tile(fn):
    """Devuelve (array nW, transform) de un VNP46A3 .h5."""
    import h5py, numpy as np, re
    m = re.search(r"\.h(\d{2})v(\d{2})\.", fn.name)
    h, v = int(m.group(1)), int(m.group(2))
    def _scalar(x, d):
        try:
            return float(np.ravel(x)[0])
        except Exception:
            return float(d)
    with h5py.File(fn, "r") as f:
        ds = f[f"{GRID}/{SUBDS}"]
        arr = ds[:].astype("float32")
        scale = _scalar(ds.attrs.get("scale_factor", 0.1), 0.1)
        fill = _scalar(ds.attrs.get("_FillValue", 65535), 65535)
        off = _scalar(ds.attrs.get("add_offset", 0.0), 0.0)
    arr[arr == fill] = np.nan
    arr = arr * scale + off
    return arr, tile_transform(h, v)


def main():
    import earthaccess, numpy as np, rasterio
    from rasterio.merge import merge
    from rasterio.windows import from_bounds
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=C.START); ap.add_argument("--end", default=C.END)
    args = ap.parse_args()
    earthaccess.login(strategy="netrc")
    DL.mkdir(exist_ok=True); VNL.mkdir(exist_ok=True)

    done = 0
    for ym in months(args.start, args.end):
        out = VNL / f"{ym}.tif"
        if out.exists():
            done += 1; continue
        y, mo = ym.split("-")
        res = earthaccess.search_data(short_name="VNP46A3", bounding_box=C.BBOX,
                                      temporal=(f"{ym}-01", f"{ym}-28"))
        if not res:
            print(f"  {ym}: sin granules"); continue
        files = earthaccess.download(res, str(DL))
        srcs = []
        for fn in files:
            fn = Path(fn)
            if fn.suffix != ".h5":
                continue
            # quedarse solo con el granule mensual cuyo DOY cae en este mes
            import re as _re, datetime as _dt
            mm = _re.search(r"\.A(\d{4})(\d{3})\.", fn.name)
            if mm:
                d = _dt.date(int(mm.group(1)), 1, 1) + _dt.timedelta(days=int(mm.group(2)) - 1)
                if f"{d.year:04d}-{d.month:02d}" != ym:
                    continue
            try:
                arr, tr = read_tile(fn)
            except Exception as ex:
                print(f"    skip {fn.name}: {repr(ex)[:80]}"); continue
            memfile = rasterio.io.MemoryFile()
            ds = memfile.open(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                              dtype="float32", crs="EPSG:4326", transform=tr, nodata=np.nan)
            ds.write(arr, 1); srcs.append(ds)
        if not srcs:
            print(f"  {ym}: sin tiles legibles"); continue
        mos, mtr = merge(srcs)
        # recorte al bbox
        with rasterio.io.MemoryFile() as mf:
            d = mf.open(driver="GTiff", height=mos.shape[1], width=mos.shape[2], count=1,
                        dtype="float32", crs="EPSG:4326", transform=mtr, nodata=np.nan)
            d.write(mos[0], 1)
            win = from_bounds(C.WEST, C.SOUTH, C.EAST, C.NORTH, d.transform)
            clip = d.read(1, window=win); ctr = d.window_transform(win)
        with rasterio.open(out, "w", driver="GTiff", height=clip.shape[0], width=clip.shape[1],
                           count=1, dtype="float32", crs="EPSG:4326", transform=ctr, nodata=np.nan,
                           compress="deflate") as o:
            o.write(clip, 1)
        for s in srcs:
            s.close()
        done += 1
        print(f"  {ym}: ok ({clip.shape[1]}x{clip.shape[0]} px)")
    print(f"listo: {done} meses en {VNL}")


if __name__ == "__main__":
    main()
