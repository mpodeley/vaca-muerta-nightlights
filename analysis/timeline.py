#!/usr/bin/env python
"""Timeline de actividad O&G: conteo oficial (Cap IV, relleno) + nowcast supliendo la cola laggeada
(rayado). El Cap IV se publica con ~13,5 meses de lag, así que los últimos meses están incompletos y
"caen" artificialmente; el nowcast estima lo que el satélite ya ve y rellena el faltante.

oficial[ym][tipo]   = Σ labels y_<tipo> de features.csv.gz (mismo registro Cap IV/Adjunto IV que entrena
                      el nowcast → misma escala que la predicción).
pred[ym][tipo]      = nº de pozos marcados por nowcast.csv (top-K de volumen de-sesgado) ese mes.
suplemento          = max(0, pred − oficial): lo que el satélite ve y el Cap IV todavía no reportó.

Salidas: docs/assets/timeline.png  +  data/_data/timeline.csv
    ~/miniforge3/bin/mamba run -n insar python analysis/timeline.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as C

TIPOS = [("perf", "Perforación", "#e8820c"),
         ("frac", "Fractura", "#d12f2f"),
         ("term", "Terminación", "#2f6fd1")]


def main():
    import pandas as pd, numpy as np
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    f = pd.read_csv(C.RAW / "features.csv.gz")
    oficial = f.groupby("ym")[["y_perf", "y_frac", "y_term"]].sum()
    oficial.columns = ["perf", "frac", "term"]

    nc = pd.read_csv(C.ROOT / "nowcast.csv")
    pred = nc.groupby(["ym", "tipo"]).size().unstack(fill_value=0)

    months = sorted(oficial.index)
    idx = {m: i for i, m in enumerate(months)}
    x = np.arange(len(months))
    lag_start = nc.ym.min()            # primer mes scoreado por el nowcast (inicio de la cola)
    lag_x = idx[lag_start] - 0.5

    fig, axes = plt.subplots(3, 1, figsize=(11, 7.2), sharex=True)
    for ax, (key, label, col) in zip(axes, TIPOS):
        of = oficial[key].reindex(months).fillna(0).values
        pr = pred[key].reindex(months).fillna(0).values if key in pred else np.zeros(len(months))
        sup = np.clip(pr - of, 0, None)               # suplemento = lo no reportado aún
        ax.axvspan(lag_x, x[-1] + 0.5, color="#f2f2f2", zorder=0)
        ax.bar(x, of, width=0.9, color=col, label="Cap IV (oficial)", zorder=2)
        ax.bar(x, sup, width=0.9, bottom=of, facecolor="none", edgecolor=col,
               hatch="////", linewidth=0.0, zorder=2, label="nowcast (lag)")
        ax.set_ylabel(label, fontsize=9)
        ax.grid(axis="y", lw=0.3, color="#ddd", zorder=0)
        ax.margins(x=0.005)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)

    # ticks anuales
    yr_ticks = [i for i, m in enumerate(months) if m.endswith("-01")]
    axes[-1].set_xticks(yr_ticks)
    axes[-1].set_xticklabels([months[i][:4] for i in yr_ticks])
    axes[0].annotate("Cap IV incompleto (lag de publicación)",
                     xy=(idx.get(lag_start, lag_x) + 9, axes[0].get_ylim()[1] * 0.90),
                     fontsize=8, color="#999", ha="left")
    handles = [Patch(facecolor="#777", label="Cap IV (registro oficial)"),
               Patch(facecolor="none", edgecolor="#777", hatch="////", label="Nowcast (suple el lag)")]
    fig.legend(handles=handles, loc="upper center", fontsize=8.5, frameon=False, ncol=2,
               bbox_to_anchor=(0.5, 0.945))
    fig.suptitle("Actividad O&G en Vaca Muerta — pozos·mes por fase (2019–2026)",
                 fontsize=12, x=0.5, y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    out = C.SITE_ASSETS / "timeline.png"
    fig.savefig(out, dpi=130)
    print(f"escrito {out}")

    # CSV de respaldo
    tab = oficial.copy()
    for key, *_ in TIPOS:
        tab[f"{key}_nowcast"] = (pred[key].reindex(months).fillna(0) if key in pred else 0)
    tab.to_csv(C.RAW / "timeline.csv")
    print(f"escrito {C.RAW / 'timeline.csv'}")


if __name__ == "__main__":
    main()
