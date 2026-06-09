#!/usr/bin/env python
"""Construye el catálogo de pozos del AOI con su ciclo de vida (ground-truth para etiquetar
actividad nocturna): coords, operador, concesión, y ventanas de PERFORACIÓN / TERMINACIÓN
(Cap IV) + FRACTURA (Adjunto IV).

Lee los CSV ya descargados por el repo madre (config.SRC_*), recorta al AOI y persiste:
  data/_data/wells.csv      idpozo, sigla, empresa, area, lon, lat, tipopozo, tipoestado,
                            perf_ini, perf_fin, term_ini, term_fin
  data/_data/frac.csv       idpozo, frac_ini, frac_fin, agua_m3, arena_tn

    ~/miniforge3/bin/mamba run -n insar python data/fetch_wells.py
"""
from __future__ import annotations
import csv, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C

csv.field_size_limit(1 << 24)


def _date(s: str) -> str:
    s = (s or "").strip()
    return s[:10] if len(s) >= 10 else ""


def wells() -> list[dict]:
    out = []
    with open(C.SRC_POZOS, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if (r.get("cuenca") or "").strip().upper() != "NEUQUINA":
                continue
            gj = r.get("geojson")
            if not gj:
                continue
            try:
                g = json.loads(gj)
                if g["type"] != "Point":
                    continue
                lon, lat = float(g["coordinates"][0]), float(g["coordinates"][1])
            except Exception:
                continue
            if not C.in_aoi(lon, lat):
                continue
            out.append({
                "idpozo": r.get("idpozo", "").strip(),
                "sigla": (r.get("sigla") or "").strip(),
                "empresa": (r.get("empresa") or "").strip(),
                "area": (r.get("area") or "").strip(),
                "lon": round(lon, 6), "lat": round(lat, 6),
                "tipopozo": (r.get("tipopozo") or "").strip(),
                "tipoestado": (r.get("tipoestado") or "").strip(),
                "perf_ini": _date(r.get("adjiv_fecha_inicio_perf")),
                "perf_fin": _date(r.get("adjiv_fecha_fin_perf")),
                "term_ini": _date(r.get("adjiv_fecha_inicio_term")),
                "term_fin": _date(r.get("adjiv_fecha_fin_term")),
            })
    return out


def frac(aoi_ids: set[str]) -> list[dict]:
    out = []
    with open(C.SRC_FRACTURA, encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        rd.fieldnames = [c.strip() for c in rd.fieldnames]
        for r in rd:
            idp = (r.get("idpozo") or "").strip()
            if idp not in aoi_ids:
                continue
            agua = r.get("agua_inyectada_m3") or ""
            arn = (r.get("arena_bombeada_nacional_tn") or "0", r.get("arena_bombeada_importada_tn") or "0")
            try:
                arena = sum(float(a) for a in arn if a)
            except ValueError:
                arena = 0.0
            out.append({
                "idpozo": idp,
                "frac_ini": _date(r.get("fecha_inicio_fractura")),
                "frac_fin": _date(r.get("fecha_fin_fractura")),
                "agua_m3": agua, "arena_tn": round(arena, 1),
            })
    return out


def main() -> None:
    for p in (C.SRC_POZOS, C.SRC_FRACTURA):
        if not p.exists():
            sys.exit(f"No existe {p}. Ver config.SRC_DATA (CSV del repo madre escala_pozo).")
    w = wells()
    ids = {x["idpozo"] for x in w}
    fr = frac(ids)
    cols_w = ["idpozo", "sigla", "empresa", "area", "lon", "lat", "tipopozo", "tipoestado",
              "perf_ini", "perf_fin", "term_ini", "term_fin"]
    with open(C.RAW / "wells.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=cols_w); wr.writeheader(); wr.writerows(w)
    with open(C.RAW / "frac.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["idpozo", "frac_ini", "frac_fin", "agua_m3", "arena_tn"])
        wr.writeheader(); wr.writerows(fr)
    n_perf = sum(1 for x in w if x["perf_ini"])
    n_frac = sum(1 for x in fr if x["frac_ini"])
    print(f"pozos AOI: {len(w)}  (con fecha perf: {n_perf})")
    print(f"fractura AOI: {len(fr)}  (con fecha frac: {n_frac})")
    print(f"persistido: {C.RAW/'wells.csv'} , {C.RAW/'frac.csv'}")


if __name__ == "__main__":
    main()
