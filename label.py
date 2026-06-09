#!/usr/bin/env python
"""Construye el calendario de ACTIVIDAD por pozo a partir del ciclo de vida público
(PERFORACIÓN / FRACTURA / TERMINACIÓN), expandido a meses y atribuido a operador + concesión.

Este es el núcleo del producto de monitoreo y corre sin datos satelitales. Si existen detecciones
nocturnas (data/_data/detections.csv de detect.py), marca cada evento como confirmado por satélite
(VNF=flaring, VNL=luces) dentro de config.MATCH_RADIUS_M y del mismo mes.

Salida: activity.csv  (ym, idpozo, sigla, empresa, area, lon, lat, actividad, sat_conf, sat_tipo)

    ~/miniforge3/bin/mamba run -n insar python label.py
"""
from __future__ import annotations
import csv, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

csv.field_size_limit(1 << 24)


def months_between(d0: str, d1: str) -> list[str]:
    """Lista de 'YYYY-MM' entre dos fechas YYYY-MM-DD inclusive (clip a ventana config)."""
    if not d0:
        return []
    d1 = d1 or d0
    y0, m0 = int(d0[:4]), int(d0[5:7])
    y1, m1 = int(d1[:4]), int(d1[5:7])
    sy, sm = int(C.START[:4]), int(C.START[5:7])
    ey, em = int(C.END[:4]), int(C.END[5:7])
    out = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        if (sy, sm) <= (y, m) <= (ey, em):
            out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1; y += 1
        if y > y1 + 1:
            break
    return out


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_detections() -> list[dict]:
    rows = load_csv(C.RAW / "detections.csv")
    for r in rows:
        r["lon"] = float(r["lon"]); r["lat"] = float(r["lat"])
    return rows


def haversine_m(lon1, lat1, lon2, lat2) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def sat_confirm(ym, lon, lat, det_by_month) -> tuple[int, str]:
    """¿Hay detección nocturna en el mismo mes y dentro del radio? Devuelve (0/1, tipo)."""
    best = ("", 1e18)
    for d in det_by_month.get(ym, []):
        dist = haversine_m(lon, lat, d["lon"], d["lat"])
        if dist <= C.MATCH_RADIUS_M and dist < best[1]:
            tipo = "VNF" if str(d.get("vnf_flag", "")).strip() in ("1", "True", "true") else "VNL"
            best = (tipo, dist)
    return (1, best[0]) if best[0] else (0, "")


def main() -> None:
    wells = load_csv(C.RAW / "wells.csv")
    frac = {r["idpozo"]: r for r in load_csv(C.RAW / "frac.csv")}
    if not wells:
        sys.exit("Falta data/_data/wells.csv — corré data/fetch_wells.py primero.")
    dets = load_detections()
    det_by_month: dict[str, list] = {}
    for d in dets:
        det_by_month.setdefault(d["ym"], []).append(d)

    rows = []
    for w in wells:
        lon, lat = float(w["lon"]), float(w["lat"])
        spans = [("PERFORACION", w["perf_ini"], w["perf_fin"]),
                 ("TERMINACION", w["term_ini"], w["term_fin"])]
        fr = frac.get(w["idpozo"])
        if fr:
            spans.append(("FRACTURA", fr["frac_ini"], fr["frac_fin"]))
        for act, d0, d1 in spans:
            for ym in months_between(d0, d1):
                conf, tipo = sat_confirm(ym, lon, lat, det_by_month) if dets else (0, "")
                rows.append({"ym": ym, "idpozo": w["idpozo"], "sigla": w["sigla"],
                             "empresa": w["empresa"], "area": w["area"],
                             "lon": lon, "lat": lat, "actividad": act,
                             "sat_conf": conf, "sat_tipo": tipo})
    rows.sort(key=lambda r: (r["ym"], r["actividad"]))
    cols = ["ym", "idpozo", "sigla", "empresa", "area", "lon", "lat", "actividad", "sat_conf", "sat_tipo"]
    with open(C.ROOT / "activity.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=cols); wr.writeheader(); wr.writerows(rows)

    from collections import Counter
    by_act = Counter(r["actividad"] for r in rows)
    print(f"eventos pozo-mes: {len(rows)}  | por tipo: {dict(by_act)}")
    if dets:
        conf = sum(r["sat_conf"] for r in rows)
        print(f"confirmados por satélite: {conf} ({100*conf/len(rows):.0f}%)")
    else:
        print("sin detecciones nocturnas (corré detect.py cuando haya EOG); actividad = solo ciclo de vida")
    print(f"persistido: {C.ROOT/'activity.csv'}")


if __name__ == "__main__":
    main()
