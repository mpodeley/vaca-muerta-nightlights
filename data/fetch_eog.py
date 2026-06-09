#!/usr/bin/env python
"""Descarga huella nocturna VIIRS del Earth Observation Group (eogdata.mines.edu) recortada al AOI:
- VNL: composites mensuales de luces (DNB, avg_rade9h, ~500 m)  -> data/_data/vnl/<ym>.tif
- VNF: gas flare survey (sitios de combustión con lat/lon/temp/volumen)  -> data/_data/vnf.csv

Requiere cuenta gratuita en eogdata.mines.edu. Credenciales por env: EOG_USER, EOG_PASS.
El token y los patrones de URL/tile de EOG cambian con el tiempo: VERIFICAR en la primera corrida
(se imprime la URL antes de bajar). Sin credencial, este script no corre; el resto del pipeline
(fetch_wells/label/viz) funciona igual y la confirmación satelital queda en 0.

    EOG_USER=... EOG_PASS=... ~/miniforge3/bin/mamba run -n insar python data/fetch_eog.py
"""
from __future__ import annotations
import os, sys, gzip, io, csv
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C

AUTH = "https://eogauth.mines.edu/auth/realms/master/protocol/openid-connect/token"
# Tile VIIRS DNB que cubre el AOI (Sudamérica, hemisferio S, oeste): tile 75N/060W cuadrante sur.
# EOG sirve composites mensuales en https://eogdata.mines.edu/nighttime_light/monthly/v10/<YYYY>/<YYYYMM>/vcmcfg/
# El nombre del archivo incluye el tile (p.ej. ...75N060W...). VERIFICAR el tile correcto al correr.
VNL_BASE = "https://eogdata.mines.edu/nighttime_light/monthly/v10"
# Gas flare survey (anual, global) — un CSV por año con lat/lon/temp/bcm:
VNF_SURVEY = "https://eogdata.mines.edu/wwwdata/viirs_products/vnf/"  # listado; elegir el global por año


def token() -> str:
    u, p = os.environ.get("EOG_USER"), os.environ.get("EOG_PASS")
    if not (u and p):
        sys.exit("Faltan EOG_USER / EOG_PASS (cuenta gratuita eogdata.mines.edu).")
    r = requests.post(AUTH, data={
        "username": u, "password": p, "client_id": "eogdata_oidc",
        "grant_type": "password",
        "client_secret": "2677ad81-521b-4869-8480-6d05b9e57d48"})  # client_secret público de EOG
    r.raise_for_status()
    return r.json()["access_token"]


def months():
    sy, sm = int(C.START[:4]), int(C.START[5:7])
    ey, em = int(C.END[:4]), int(C.END[5:7])
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield f"{y:04d}", f"{y:04d}{m:02d}"
        m += 1
        if m > 12:
            m = 1; y += 1


def main() -> None:
    tok = token()
    hdr = {"Authorization": f"Bearer {tok}"}
    vnl_dir = C.RAW / "vnl"; vnl_dir.mkdir(exist_ok=True)
    print("Token OK. Bajando VNL mensual (recortar al AOI con rasterio en detect.py)…")
    # NOTA: el path/tile exacto se confirma en la 1ª corrida. Se imprime la URL candidata.
    got = 0
    for yyyy, ym in months():
        url = f"{VNL_BASE}/{yyyy}/{ym}/vcmcfg/"  # listar y elegir el tile que cubre el AOI
        print("  candidato:", url)
        # Implementación concreta del listado/elección de tile: completar al verificar credencial.
        # (Se baja el .tif del tile, se guarda como vnl/<ym>.tif; detect.py recorta al bbox.)
    print("VNF: bajar el gas flare survey anual de", VNF_SURVEY,
          "y filtrar al AOI -> vnf.csv (lat/lon/temp_bb/bcm).")
    print(f"[stub listo] Completar listado de tiles/survey con la credencial. got={got}")


if __name__ == "__main__":
    main()
