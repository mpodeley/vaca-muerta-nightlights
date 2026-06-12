#!/usr/bin/env python
"""Mapa para slide PPT: heatmap de actividad de FRACTURA 2025 (Adjunto IV oficial + estimación nowcast)
sobre imagen satelital Esri, concesiones sombreadas por operadora, los bloques de Pluspetrol
(Bajo del Choique y La Calera) remarcados, y el marcador de la estación de GNC a granel propuesta sobre
Ruta 7 / TGS Tratayén — para ver cómo queda ubicada respecto de la actividad.

    ~/miniforge3/bin/mamba run -n insar python analysis/frac_heatmap_gnc.py

Trabaja en Web Mercator (EPSG:3857, metros) → aspecto correcto y basemap directo.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C

# ───────────────────── constantes editables ─────────────────────
YEAR = 2025
STATION_LONLAT = (-68.58684918312807, -38.45955215414465)   # ubicación real (Ruta 7 / TGS Tratayén)
PLUS_BLOQUES = ["BAJO DEL CHOIQUE - LA INVERNADA", "LA CALERA"]   # nombres exactos en el geojson
TOP_OPERADORAS = 10                      # cuántas operadoras reciben color de relleno (resto = gris)
TOP_BLOQUES_LABEL = 14                    # cuántos bloques se etiquetan (los de más actividad) + el de la estación
FORCE_OPS = ["SHELL", "PAMPA", "PAN AMERICAN"]   # operadoras siempre rotuladas (en el encuadre), aunque no estén en el top
# encuadre ajustado: cubre Bajo del Choique (NO), La Calera + actividad (S), y la estación (E).
# El aspecto sigue a los datos (no se fuerza 16:9 → sin desierto lateral). Poner None para auto-encuadre.
BBOX = (-69.55, -38.82, -68.10, -37.40)  # (W,S,E,N) en lon/lat
PAD = 0.06                               # margen del auto-encuadre
WEIGHT = "pozos"                         # "pozos" (densidad) | "etapas" (cantidad_fracturas)
OUT = C.ROOT / "exports" / f"frac_heatmap_gnc_{YEAR}.png"
SRC_FRAC = C.SRC_DATA / "fractura_adjiv.csv"
PLUS_EDGE = "#00e5ff"                     # color de remarcado Pluspetrol


OP_ABBR = {"PLUSPETROL": "Pluspetrol", "YPF": "YPF", "VISTA": "Vista", "SHELL": "Shell",
           "PAN AMERICAN": "PAE", "TECPETROL": "Tecpetrol", "PAMPA": "Pampa", "CHEVRON": "Chevron",
           "TOTAL": "TotalEnergies", "PHOENIX": "Phoenix", "WINTERSHALL": "Wintershall", "CGC": "CGC",
           "EXXON": "ExxonMobil", "FLXS": "FLXS", "PETRONAS": "Petronas", "GYP": "G&P"}


def abbr_op(op):
    u = (op or "").upper()
    for k, v in OP_ABBR.items():
        if k in u:
            return v
    return op.split()[0].title() if op else "—"


def rings_of(geom):
    """Devuelve lista de anillos exteriores (cada uno lista de [lon,lat]) para Polygon/MultiPolygon."""
    t, c = geom["type"], geom["coordinates"]
    if t == "Polygon":
        return [c[0]]
    if t == "MultiPolygon":
        return [poly[0] for poly in c]
    return []


def main():
    import numpy as np, pandas as pd
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPoly, FancyBboxPatch
    from matplotlib.collections import PatchCollection
    from matplotlib.path import Path as MplPath
    from matplotlib.colors import Normalize
    from matplotlib.lines import Line2D
    from scipy.ndimage import gaussian_filter
    from pyproj import Transformer
    import contextily as ctx

    T = Transformer.from_crs(4326, 3857, always_xy=True)
    to3857 = lambda lon, lat: T.transform(lon, lat)

    # ── datos de fractura 2025 ──
    wells = pd.read_csv(C.RAW / "wells.csv")[["idpozo", "lon", "lat"]].dropna()
    wxy = wells.drop_duplicates("idpozo").set_index("idpozo")
    fr = pd.read_csv(SRC_FRAC)
    off = fr[fr.anio_if == YEAR][["idpozo", "cantidad_fracturas"]].drop_duplicates("idpozo")
    nc = pd.read_csv(C.ROOT / "nowcast.csv")
    est = nc[(nc.tipo == "frac") & (nc.ym.str[:4] == str(YEAR))][["idpozo"]].drop_duplicates()
    ids = pd.Index(off.idpozo).union(pd.Index(est.idpozo))
    pts = wxy.reindex(ids).dropna()
    if WEIGHT == "etapas":
        wt = off.set_index("idpozo").cantidad_fracturas.reindex(pts.index).fillna(1).clip(lower=1).values
    else:
        wt = np.ones(len(pts))
    print(f"fractura {YEAR}: oficial(AdjIV)={len(off)} | nowcast={len(est)} | unión c/coords={len(pts)}")

    px, py = to3857(pts.lon.values, pts.lat.values)
    px, py = np.array(px), np.array(py)
    stx, sty = to3857(*STATION_LONLAT)

    # ── concesiones: parsear y reproyectar ──
    gj = json.load(open(C.CONCESIONES))
    concs = []  # (nombre, operador, [poly3857 (N,2) ...])
    for f in gj["features"]:
        if not f.get("geometry"):
            continue
        polys = []
        for ring in rings_of(f["geometry"]):
            lons = [c[0] for c in ring]; lats = [c[1] for c in ring]
            xx, yy = to3857(lons, lats)
            polys.append(np.column_stack([xx, yy]))
        if polys:
            pr = f["properties"]
            concs.append((str(pr.get("nombre", "")), str(pr.get("operador", "")).strip(), polys))

    # operadora por nº de pozos fracturados dentro de sus polígonos (point-in-polygon)
    XY = np.column_stack([px, py])
    op_count = {}
    blk_count = []
    for nombre, op, polys in concs:
        cnt = 0
        for poly in polys:
            if len(poly) >= 3:
                cnt += int(MplPath(poly).contains_points(XY).sum())
        op_count[op] = op_count.get(op, 0) + cnt
        blk_count.append(cnt)
    top_ops = [op for op, _ in sorted(op_count.items(), key=lambda kv: -kv[1]) if op][:TOP_OPERADORAS]
    cmap_q = plt.colormaps["tab20"]
    op_color = {op: cmap_q(i % 20) for i, op in enumerate(top_ops)}

    # ── extent (3857) — el aspecto sigue a los datos, sin forzar 16:9 ──
    if BBOX:
        (W, S, E, N) = BBOX
        (xmin, ymin) = to3857(W, S); (xmax, ymax) = to3857(E, N)
    else:  # auto robusto: percentiles de los pozos (ignora outliers) + estación + bloques Pluspetrol
        plus_xy = [p for nombre, op, polys in concs if nombre in PLUS_BLOQUES for poly in polys for p in poly]
        allx = np.concatenate([np.percentile(px, [1, 99]), [stx], [q[0] for q in plus_xy]])
        ally = np.concatenate([np.percentile(py, [1, 99]), [sty], [q[1] for q in plus_xy]])
        xmin, xmax, ymin, ymax = allx.min(), allx.max(), ally.min(), ally.max()
        dx, dy = (xmax - xmin) * PAD, (ymax - ymin) * PAD
        xmin -= dx; xmax += dx; ymin -= dy; ymax += dy
    ext_w, ext_h = xmax - xmin, ymax - ymin

    # ── heatmap (histograma 2D suavizado) — celdas ~cuadradas ──
    nx = 700; ny = max(1, int(nx * ext_h / ext_w))
    H, xe, ye = np.histogram2d(px, py, bins=[nx, ny], range=[[xmin, xmax], [ymin, ymax]], weights=wt)
    H = gaussian_filter(H.T, sigma=6)     # .T → (row=y, col=x)
    vmax = np.percentile(H[H > 0], 99) if (H > 0).any() else 1.0
    norm = np.clip(H / vmax, 0, 1)
    cmap_h = plt.colormaps["inferno"].copy()       # cálido (no choca con el cian de Pluspetrol)
    rgba = cmap_h(norm)
    rgba[..., 3] = np.clip(norm * 1.9, 0, 0.82)    # rampa de alpha: transparente en densidad baja

    # ── figura ──
    fig_w = 14.0
    fig, ax = plt.subplots(figsize=(fig_w, fig_w * ext_h / ext_w), dpi=200)
    ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.set_aspect("equal"); ax.axis("off")
    ctx.add_basemap(ax, source=ctx.providers.Esri.WorldImagery, crs="EPSG:3857", attribution=False)

    # concesiones coloreadas por operadora
    patches, colors = [], []
    for nombre, op, polys in concs:
        col = op_color.get(op, (0.6, 0.6, 0.6, 1))
        for poly in polys:
            patches.append(MplPoly(poly, closed=True))
            colors.append(col)
    pc = PatchCollection(patches, facecolor=colors, edgecolor="white", linewidths=0.3, alpha=0.22, zorder=2)
    ax.add_collection(pc)

    # heatmap encima
    ax.imshow(rgba, extent=[xmin, xmax, ymin, ymax], origin="lower", zorder=3, interpolation="bilinear")

    stroke = lambda lw: [plt.matplotlib.patheffects.withStroke(linewidth=lw, foreground="black")]

    # etiquetas por bloque: nombre del bloque (blanco) + operadora abreviada (color de la operadora).
    # Solo bloques relevantes del encuadre: con actividad de fractura, o el de la estación, o Pluspetrol.
    def poly_area_km2(polys):
        a = 0.0
        for p in polys:
            x, y = p[:, 0], p[:, 1]
            a += abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))) / 2
        return a / 1e6
    stxy = np.array([[stx, sty]])
    st_block = next((i for i, (n, o, ps) in enumerate(concs)
                     if any(MplPath(p).contains_points(stxy)[0] for p in ps if len(p) >= 3)), None)
    # bloques a etiquetar: top por actividad (en el encuadre) + el de la estación
    in_ext = [i for i, (n, o, ps) in enumerate(concs)
              if (xmin <= ps[int(np.argmax([len(p) for p in ps]))].mean(0)[0] <= xmax)
              and (ymin <= ps[int(np.argmax([len(p) for p in ps]))].mean(0)[1] <= ymax)]
    top_blk = sorted([i for i in in_ext if blk_count[i] > 0], key=lambda i: -blk_count[i])[:TOP_BLOQUES_LABEL]
    force_blk = [i for i in in_ext if any(k in concs[i][1].upper() for k in FORCE_OPS)]
    label_idx = set(top_blk) | set(force_blk) | ({st_block} if st_block is not None else set())
    for i in label_idx:
        nombre, op, polys = concs[i]
        if nombre in PLUS_BLOQUES or poly_area_km2(polys) < 3:
            continue  # Pluspetrol se etiqueta aparte (cian)
        cxy = polys[int(np.argmax([len(p) for p in polys]))].mean(axis=0)
        col = op_color.get(op, (0.85, 0.85, 0.85, 1))
        ax.text(cxy[0], cxy[1], nombre.title(), ha="center", va="bottom", fontsize=9.5, color="white",
                fontweight="bold", zorder=7, path_effects=stroke(2.4))
        ax.text(cxy[0], cxy[1], abbr_op(op), ha="center", va="top", fontsize=8.5, color=col,
                fontweight="bold", zorder=7, path_effects=stroke(2.4))

    # bloques Pluspetrol remarcados + etiqueta (cian, con operadora)
    for nombre, op, polys in concs:
        if nombre in PLUS_BLOQUES:
            for poly in polys:
                ax.add_patch(MplPoly(poly, closed=True, fill=False, edgecolor=PLUS_EDGE, linewidth=2.6, zorder=5))
            cxy = polys[np.argmax([len(p) for p in polys])].mean(axis=0)
            ax.annotate(nombre.title().replace(" - ", "\n") + f"\n({abbr_op(op)})", xy=cxy, color=PLUS_EDGE,
                        fontsize=8.5, fontweight="bold", ha="center", va="center", zorder=6,
                        linespacing=1.0, path_effects=stroke(2.5))

    # estación GNC
    ax.scatter([stx], [sty], marker="*", s=560, c="white", edgecolors="black", linewidths=1.4, zorder=8)
    ax.annotate("Estación GNC a granel\n(Ruta 7 · TGS Tratayén)", xy=(stx, sty),
                xytext=(stx - ext_w * 0.02, sty + ext_h * 0.055),
                color="white", fontsize=12, fontweight="bold", zorder=8, ha="center", va="bottom",
                path_effects=[plt.matplotlib.patheffects.withStroke(linewidth=3, foreground="black")],
                arrowprops=dict(arrowstyle="-", color="white", lw=1.2))

    # título + créditos
    fig.suptitle(f"Actividad de fractura {YEAR} en Vaca Muerta y la estación de GNC propuesta",
                 fontsize=18, fontweight="bold", color="white", y=0.965,
                 path_effects=[plt.matplotlib.patheffects.withStroke(linewidth=3, foreground="black")])
    ax.text(0.005, 0.01, "Fuente: Cap IV / Adjunto IV + nowcast (estimación satelital) · "
            "Imagen: Esri World Imagery · concesiones: Neuquén", transform=ax.transAxes,
            fontsize=7.5, color="white", va="bottom",
            path_effects=[plt.matplotlib.patheffects.withStroke(linewidth=2, foreground="black")])

    # leyenda chica: estación + bloques Pluspetrol (la de operadoras ya no hace falta: van rotuladas)
    leg_extra = [Line2D([0], [0], marker="*", color="none", markerfacecolor="white", markeredgecolor="black",
                        markersize=16, label="Estación GNC"),
                 plt.matplotlib.patches.Patch(facecolor="none", edgecolor=PLUS_EDGE, linewidth=2.5,
                                              label="Bloques Pluspetrol")]
    ax.legend(handles=leg_extra, loc="lower right", fontsize=10, framealpha=0.6, facecolor="black",
              labelcolor="white")

    # colorbar del heatmap
    sm = plt.cm.ScalarMappable(cmap=cmap_h, norm=Normalize(0, 1))
    cb = fig.colorbar(sm, ax=ax, fraction=0.022, pad=0.008)
    cb.set_label("Concentración de fractura 2025 (baja → alta)", color="white", fontsize=8)
    cb.ax.yaxis.set_tick_params(color="white"); cb.set_ticks([])
    cb.outline.set_edgecolor("white")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=200, bbox_inches="tight", pad_inches=0.05, facecolor="black")
    print(f"escrito {OUT}  ({nx}x{ny} grid) | operadoras coloreadas: {len(top_ops)}")
    print(f"extent lon/lat ≈ {T.transform(xmin, ymin, direction='INVERSE')[:2]} .. "
          f"{T.transform(xmax, ymax, direction='INVERSE')[:2]}")


if __name__ == "__main__":
    main()
