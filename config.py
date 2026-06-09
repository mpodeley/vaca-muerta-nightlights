"""Config central — Monitor de actividad nocturna en Vaca Muerta.

AOI heredado del trabajo InSAR (track 18, Añelo). Todo en WGS84 (EPSG:4326).
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "_data"
RAW.mkdir(parents=True, exist_ok=True)

# --- AOI (lon/lat) — igual que subsidencia-vaca-muerta/t18_f1050/aoi.py ---
WEST, SOUTH, EAST, NORTH = -70.6, -39.2, -68.2, -37.3
ANELO = (-38.35, -68.79)  # (lat, lon)

# --- Ventana temporal del monitoreo ---
START, END = "2019-01", "2026-06"   # YYYY-MM

# --- Parámetros de matching (label.py) ---
MATCH_RADIUS_M = 1200.0   # radio detección↔pozo (~footprint VIIRS 500-750m + margen)
PERSIST_MONTHS = 4        # ≥ esto = "persistente" (facilidad/producción); menos = transitorio (operación)

# --- Fuentes ---
CONCESIONES = DATA / "concesiones_neuquina.geojson"
# Catálogo de pozos (Cap IV) y fractura (Adjunto IV): se reusan los CSV ya descargados por el
# repo madre (escala_pozo/_data). fetch_wells.py recorta al AOI y persiste el subset acá.
# (Si esos CSV no estuvieran, bajarlos del portal datos.energia.gob.ar — datasets Cap IV pozos y
# Datos de Fractura Adjunto IV — y apuntar SRC_DATA a su carpeta.)
SRC_DATA = Path("/var/home/matias/Projects/subsidencia-vaca-muerta/exploraciones/escala_pozo/_data")
SRC_POZOS = SRC_DATA / "capitulo_iv_pozos.csv"
SRC_FRACTURA = SRC_DATA / "fractura_adjiv.csv"

BBOX = (WEST, SOUTH, EAST, NORTH)


def in_aoi(lon: float, lat: float) -> bool:
    return WEST <= lon <= EAST and SOUTH <= lat <= NORTH
