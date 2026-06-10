#!/usr/bin/env python
"""Valida la huella nocturna contra el ground-truth público (fechas de pozo):
- RECALL por tipo de actividad: ¿de los eventos conocidos (PERFORACIÓN/FRACTURA/TERMINACIÓN), cuántos
  tienen una detección nocturna en el mismo mes y dentro de MATCH_RADIUS_M?
- PRECISIÓN: de las detecciones, ¿cuántas caen sobre algún evento conocido (vs ruido/otras luces)?
Sirve para calibrar radio/umbral y para reportar la credibilidad de la confirmación satelital.

    ~/miniforge3/bin/mamba run -n insar python validate.py
"""
from __future__ import annotations
import csv, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
from label import haversine_m


def load(path):
    if not Path(path).exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    # validar SOLO contra eventos reales de pozo (perf/frac/term), no contra filas derivadas de detección
    acts = [a for a in load(C.ROOT / "activity.csv") if a.get("fuente") == "pozo"]
    dets = load(C.RAW / "detections.csv")
    if not acts:
        sys.exit("Falta activity.csv — corré label.py.")
    if not dets:
        print("0 detecciones nocturnas — no se puede validar todavía (corré fetch_eog + detect con EOG).")
        return
    det_by_month = defaultdict(list)
    for d in dets:
        d["lon"] = float(d["lon"]); d["lat"] = float(d["lat"])
        det_by_month[d["ym"]].append(d)

    # RECALL por tipo
    hit, tot = Counter(), Counter()
    for a in acts:
        act = a["actividad"]; tot[act] += 1
        lon, lat = float(a["lon"]), float(a["lat"])
        found = any(haversine_m(lon, lat, d["lon"], d["lat"]) <= C.MATCH_RADIUS_M
                    for d in det_by_month.get(a["ym"], []))
        if found:
            hit[act] += 1
    print(f"=== RECALL (radio {C.MATCH_RADIUS_M:.0f} m, mismo mes) ===")
    for act in tot:
        print(f"  {act:12s}  {hit[act]}/{tot[act]}  = {100*hit[act]/tot[act]:.0f}%")

    # PRECISIÓN: detecciones cerca de algún evento
    act_by_month = defaultdict(list)
    for a in acts:
        act_by_month[a["ym"]].append((float(a["lon"]), float(a["lat"])))
    near = 0
    for d in dets:
        if any(haversine_m(d["lon"], d["lat"], lo, la) <= C.MATCH_RADIUS_M
               for lo, la in act_by_month.get(d["ym"], [])):
            near += 1
    print(f"=== PRECISIÓN ===\n  detecciones sobre evento conocido: {near}/{len(dets)} = {100*near/len(dets):.0f}%")
    print("  (el resto = flaring/luces de producción o facilidades sin evento perf/frac/term ese mes)")


if __name__ == "__main__":
    main()
