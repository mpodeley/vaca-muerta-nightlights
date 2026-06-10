#!/usr/bin/env python
"""Cuantifica el LAG de reporte del Cap IV / Adjunto IV: cuánto tarda un evento (fractura) en
aparecer en el dato público (fecha_data − fecha_fin_fractura). Define la ventana de nowcasting:
los meses recientes donde hay satélite pero el dato oficial todavía no salió.

    ~/miniforge3/bin/mamba run -n insar python analysis/lag.py
"""
from __future__ import annotations
import csv, sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C
csv.field_size_limit(1 << 24)


def pdate(s):
    s = (s or "").strip()[:10]
    try:
        return date(int(s[:4]), int(s[5:7]), int(s[8:10]))
    except Exception:
        return None


def main():
    import numpy as np
    lags = []
    with open(C.SRC_FRACTURA, encoding="utf-8-sig") as f:
        rd = csv.DictReader(f); rd.fieldnames = [c.strip() for c in rd.fieldnames]
        for r in rd:
            ff = pdate(r.get("fecha_fin_fractura")); fd = pdate(r.get("fecha_data"))
            if ff and fd and fd >= ff:
                lags.append((fd - ff).days)
    if not lags:
        sys.exit("sin lags computables")
    a = np.array(lags)
    print(f"fracturas con fechas: {len(a)}")
    print("lag fecha_data − fin_fractura (días):")
    for p in (10, 25, 50, 75, 90):
        print(f"  p{p}: {np.percentile(a,p):.0f} d  (~{np.percentile(a,p)/30:.1f} meses)")
    med_m = np.median(a) / 30
    print(f"\nVentana de nowcasting ~ últimos {max(1,round(med_m))}–{max(2,round(np.percentile(a,90)/30))} meses "
          f"(mediana {med_m:.1f} m): ahí el satélite puede adelantar al Cap IV.")


if __name__ == "__main__":
    main()
