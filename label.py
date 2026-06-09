#!/usr/bin/env python
"""Etiqueta la actividad O&G mes a mes combinando dos fuentes:

(A) Ciclo de vida público de pozos → eventos PERFORACIÓN / FRACTURA / TERMINACIÓN (transitorios),
    confirmados o no por luz nocturna (sat_conf).
(B) Detecciones de luz nocturna (Black Marble) que NO corresponden a un evento transitorio:
    cerca de un pozo ya terminado → FLARING (muy brillante, ≥FLARE_NW) o PRODUCCION (luces);
    persistente y sin pozo cerca → PUEBLO (se excluye de la actividad O&G).

Salida: activity.csv (ym, idpozo, sigla, empresa, area, lon, lat, actividad, fuente, sat_conf, brillo)

    ~/miniforge3/bin/mamba run -n insar python label.py
"""
from __future__ import annotations
import csv, math, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

csv.field_size_limit(1 << 24)


def months_between(d0, d1):
    if not d0:
        return []
    d1 = d1 or d0
    y, m = int(d0[:4]), int(d0[5:7]); y1, m1 = int(d1[:4]), int(d1[5:7])
    sy, sm = int(C.START[:4]), int(C.START[5:7]); ey, em = int(C.END[:4]), int(C.END[5:7])
    out = []
    while (y, m) <= (y1, m1):
        if (sy, sm) <= (y, m) <= (ey, em):
            out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1; y += 1
        if y > y1 + 1:
            break
    return out


def load(path):
    p = Path(path)
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def haversine_m(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def ym_le(a, b):  # 'YYYY-MM' <= 'YYYY-MM'
    return a <= b


def main() -> None:
    wells = load(C.RAW / "wells.csv")
    if not wells:
        sys.exit("Falta data/_data/wells.csv — corré data/fetch_wells.py.")
    frac = {r["idpozo"]: r for r in load(C.RAW / "frac.csv")}
    dets = load(C.RAW / "detections.csv")
    for d in dets:
        d["lon"] = float(d["lon"]); d["lat"] = float(d["lat"])
        d["b"] = float(d["vnl_brillo"]) if d["vnl_brillo"] else 0.0
    det_by_month = defaultdict(list)
    for d in dets:
        det_by_month[d["ym"]].append(d)

    # persistencia de cada celda (~500 m) en el tiempo
    cell_months = defaultdict(set)
    for d in dets:
        key = (round(d["lon"] / C.GRID_DEG), round(d["lat"] / C.GRID_DEG))
        d["cell"] = key
        cell_months[key].add(d["ym"])
    persist = {k: len(v) for k, v in cell_months.items()}

    # índice espacial simple de pozos por celda gruesa (~ a few km) para vecindad rápida
    well_cell = defaultdict(list)
    CELL = 0.02  # ~2 km
    for w in wells:
        w["lon"] = float(w["lon"]); w["lat"] = float(w["lat"])
        well_cell[(round(w["lon"] / CELL), round(w["lat"] / CELL))].append(w)

    def nearest_well(lon, lat, radius):
        c = (round(lon / CELL), round(lat / CELL))
        best, bd = None, radius
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for w in well_cell.get((c[0] + dx, c[1] + dy), []):
                    dist = haversine_m(lon, lat, w["lon"], w["lat"])
                    if dist <= bd:
                        best, bd = w, dist
        return best, bd

    rows = []

    # (A) eventos transitorios del ciclo de vida
    event_pts_by_month = defaultdict(list)   # para marcar qué detecciones ya están "usadas"
    for w in wells:
        spans = [("PERFORACION", w["perf_ini"], w["perf_fin"]),
                 ("TERMINACION", w["term_ini"], w["term_fin"])]
        fr = frac.get(w["idpozo"])
        if fr:
            spans.append(("FRACTURA", fr["frac_ini"], fr["frac_fin"]))
        for act, d0, d1 in spans:
            for ym in months_between(d0, d1):
                # confirmación satelital
                conf, brillo = 0, 0.0
                for d in det_by_month.get(ym, []):
                    if haversine_m(w["lon"], w["lat"], d["lon"], d["lat"]) <= C.MATCH_RADIUS_M:
                        conf = 1; brillo = max(brillo, d["b"])
                event_pts_by_month[ym].append((w["lon"], w["lat"]))
                rows.append({"ym": ym, "idpozo": w["idpozo"], "sigla": w["sigla"],
                             "empresa": w["empresa"], "area": w["area"],
                             "lon": w["lon"], "lat": w["lat"], "actividad": act,
                             "fuente": "pozo", "sat_conf": conf, "brillo": round(brillo, 1)})

    # (B) detecciones nocturnas que no son evento transitorio → flaring/producción o pueblo
    for d in dets:
        ym, lon, lat = d["ym"], d["lon"], d["lat"]
        # ¿ya cubierta por un evento transitorio cercano ese mes?
        if any(haversine_m(lon, lat, lo, la) <= C.MATCH_RADIUS_M
               for lo, la in event_pts_by_month.get(ym, [])):
            continue
        w, dist = nearest_well(lon, lat, C.MATCH_RADIUS_M)
        if w is not None:
            # ¿el pozo ya está terminado/perforado a esta fecha? → productor
            done = w["term_fin"] or w["perf_fin"]
            if done and ym_le(done[:7], ym):
                act = "FLARING" if d["b"] >= C.FLARE_NW else "PRODUCCION"
                rows.append({"ym": ym, "idpozo": w["idpozo"], "sigla": w["sigla"],
                             "empresa": w["empresa"], "area": w["area"],
                             "lon": lon, "lat": lat, "actividad": act, "fuente": "satelite",
                             "sat_conf": 1, "brillo": round(d["b"], 1)})
            # si el pozo aún no está terminado, la luz puede ser obra previa: lo dejamos sin fila
        else:
            # sin pozo en el radio: ¿pueblo? (persistente y sin pozo en TOWN_RADIUS)
            if persist.get(d["cell"], 0) >= C.PERSIST_TOWN and nearest_well(lon, lat, C.TOWN_RADIUS_M)[0] is None:
                rows.append({"ym": ym, "idpozo": "", "sigla": "", "empresa": "", "area": "",
                             "lon": lon, "lat": lat, "actividad": "PUEBLO", "fuente": "satelite",
                             "sat_conf": 1, "brillo": round(d["b"], 1)})
            # else: luz aislada no persistente sin pozo → ruido, se descarta

    rows.sort(key=lambda r: (r["ym"], r["actividad"]))
    cols = ["ym", "idpozo", "sigla", "empresa", "area", "lon", "lat", "actividad", "fuente",
            "sat_conf", "brillo"]
    with open(C.ROOT / "activity.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=cols); wr.writeheader(); wr.writerows(rows)

    from collections import Counter
    by = Counter(r["actividad"] for r in rows)
    print(f"filas actividad: {len(rows)}  | por tipo: {dict(by)}")
    if dets:
        ev = [r for r in rows if r["fuente"] == "pozo"]
        conf = sum(r["sat_conf"] for r in ev)
        print(f"eventos de pozo: {len(ev)}  | confirmados por luz: {conf} ({100*conf/max(len(ev),1):.0f}%)")
    print(f"persistido: {C.ROOT/'activity.csv'}")


if __name__ == "__main__":
    main()
