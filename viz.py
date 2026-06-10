#!/usr/bin/env python
"""Dashboard de actividad: mapa Leaflet + slider mensual + ranking por operador.

Funciones:
- Overlay del DATO CRUDO de luz nocturna (VIIRS) por timestep, toggleable (cambia con el slider).
- Conteo SEPARADO por tipo (perforación / fractura / terminación / flaring / producción).
- Leyenda CLICKEABLE: prende/apaga cada signature en el mapa.

Genera los PNG de raster nocturno en docs/assets/vnl/<ym>.png y el dashboard en
docs/assets/demo_actividad.html (lo que publica el sitio MkDocs).

    ~/miniforge3/bin/mamba run -n insar python viz.py
"""
from __future__ import annotations
import csv, json, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

COLORS = {"PERF": "#ff7f0e", "FRAC": "#d62728", "TERM": "#1f77b4",
          "FLAR": "#ffd400", "PROD": "#2ca02c", "PUEB": "#9e9e9e", "NOWC": "#e000e0"}
NAME = {"PERF": "Perforación", "FRAC": "Fractura", "TERM": "Terminación",
        "FLAR": "Flaring", "PROD": "Producción", "PUEB": "Pueblo/ciudad",
        "NOWC": "Nowcast (predicción)"}
TRANSIENT = ["PERF", "FRAC", "TERM"]
ORDER = ["PERF", "FRAC", "TERM", "FLAR", "PROD", "PUEB", "NOWC"]
VNL_DIR = C.RAW / "vnl"
ASSETS = C.SITE_ASSETS
OUT = ASSETS / "demo_actividad.html"


def render_rasters():
    """Renderiza cada vnl/<ym>.tif a docs/assets/vnl/<ym>.png (log, transparente en lo oscuro).
    Devuelve (bounds [[S,W],[N,E]], lista de ym disponibles)."""
    import numpy as np, rasterio
    from matplotlib import colormaps
    tifs = sorted(VNL_DIR.glob("*.tif"))
    if not tifs:
        return None, []
    outdir = ASSETS / "vnl"; outdir.mkdir(parents=True, exist_ok=True)
    # vmax global estable
    vmax = 1.0; bounds = None
    for t in tifs:
        with rasterio.open(t) as s:
            a = s.read(1)
            b = s.bounds
        bounds = [[b.bottom, b.left], [b.top, b.right]]
        pos = a[np.isfinite(a) & (a > 0)]
        if pos.size:
            vmax = max(vmax, float(np.log1p(np.percentile(pos, 99.5))))
    cmap = colormaps["inferno"]
    import matplotlib.pyplot as plt
    for t in tifs:
        ym = t.stem
        png = outdir / f"{ym}.png"
        if png.exists():
            continue
        with rasterio.open(t) as s:
            a = s.read(1).astype("float32")
        a = np.where(np.isfinite(a), a, 0.0)
        norm = np.clip(np.log1p(np.clip(a, 0, None)) / vmax, 0, 1)
        rgba = cmap(norm)
        rgba[..., 3] = np.clip(norm * 1.6, 0, 0.92)   # transparente en lo oscuro
        rgba[a <= 1.0, 3] = 0.0
        plt.imsave(png, rgba)
    return bounds, [t.stem for t in tifs]


def main() -> None:
    if not (C.ROOT / "activity.csv").exists():
        sys.exit("Falta activity.csv — corré label.py primero.")
    ASSETS.mkdir(parents=True, exist_ok=True)
    bounds, vnl_months = render_rasters()
    rows = list(csv.DictReader(open(C.ROOT / "activity.csv")))
    by_month = defaultdict(list)
    for r in rows:
        by_month[r["ym"]].append({
            "lo": round(float(r["lon"]), 5), "la": round(float(r["lat"]), 5),
            "a": r["actividad"][:4], "e": r["empresa"] or "—", "s": r["sigla"] or "",
            "c": int(r["sat_conf"] or 0)})
    # capa nowcast (predicción del último mes con dato oficial incompleto)
    ncp = C.ROOT / "nowcast.csv"
    if ncp.exists():
        for r in csv.DictReader(open(ncp)):
            by_month[r["ym"]].append({
                "lo": round(float(r["lon"]), 5), "la": round(float(r["lat"]), 5),
                "a": "NOWC", "e": (r["empresa"] or "—") + " · " + r["tipo"] + " p=" + r["prob"],
                "s": "NOWCAST " + r["tipo"], "c": 0})
    months = sorted(by_month)
    frames = [{"ym": m, "pts": by_month[m]} for m in months]
    vnl_set = set(vnl_months)
    conc = json.dumps(json.load(open(C.CONCESIONES))) if C.CONCESIONES.exists() else "null"
    vnl_bounds = json.dumps(bounds) if bounds else "null"

    legend_rows = "".join(
        f'<div class="lg" data-cat="{k}"><span class="sw" style="background:{COLORS[k]}"></span>{NAME[k]} '
        f'<span class="ct" id="ct_{k}">0</span></div>' for k in ORDER)

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<title>Actividad en Vaca Muerta desde luz nocturna</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 html,body,#map{{height:100%;margin:0}}
 .panel{{position:absolute;bottom:18px;left:50%;transform:translateX(-50%);z-index:1000;
  background:rgba(255,255,255,.96);padding:10px 16px;border-radius:8px;font:13px sans-serif;
  box-shadow:0 1px 6px rgba(0,0,0,.3);width:min(660px,94vw)}}
 #ym{{font-weight:bold}} input[type=range]{{width:100%}}
 .legend{{position:absolute;top:12px;right:12px;z-index:1000;background:rgba(255,255,255,.96);
  padding:8px 12px;border-radius:6px;font:12px sans-serif;user-select:none}}
 .lg{{cursor:pointer;padding:2px 3px;border-radius:4px}} .lg:hover{{background:#eee}}
 .lg.off{{opacity:.35;text-decoration:line-through}}
 .ct{{float:right;color:#444;font-weight:bold;margin-left:10px}}
 .rk{{position:absolute;top:12px;left:12px;z-index:1000;background:rgba(255,255,255,.96);
  padding:8px 12px;border-radius:6px;font:12px sans-serif;min-width:215px}}
 .sw{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:5px}}
 .bar{{height:9px;background:#ff7f0e;display:inline-block;vertical-align:middle;border-radius:2px}}
 #play{{cursor:pointer;border:none;background:#334;color:#fff;border-radius:5px;padding:2px 9px}}
 table{{border-collapse:collapse}} td{{padding:1px 4px;font-size:11px}}
 .hd{{font-size:11px;color:#666;margin-bottom:3px}}
</style></head><body>
<div id="map"></div>
<div class="legend">
 <div class="hd"><b>Actividad O&G</b> · click = prender/apagar</div>
 {legend_rows}
 <hr style="margin:5px 0;border:none;border-top:1px solid #ddd">
 <div class="lg" data-cat="RAW"><span class="sw" style="background:#000;border:1px solid #999"></span>Luz nocturna (cruda)</div>
 <div style="font-size:10px;color:#666">anillo = confirmado por luz</div>
</div>
<div class="rk"><b>Perf/Frac/Term — <span id="ym2"></span></b><table id="rank"></table></div>
<div class="panel">
 <div><button id="play">▶</button> &nbsp;<b>Vaca Muerta · actividad</b> · <span id="ym"></span></div>
 <div id="cnt" style="font-size:12px;color:#333;margin:3px 0"></div>
 <input type="range" id="sl" min="0" max="{len(frames)-1}" value="{len(frames)-1}" step="1">
 <div style="font-size:11px;color:#666;text-align:center">
  Ciclo de vida de pozos (Cap IV / Adjunto IV) + luz nocturna VIIRS Black Marble. Atribución, no causalidad.</div>
</div>
<script>
const FR={json.dumps(frames)}, COL={json.dumps(COLORS)}, NM={json.dumps(NAME)},
      TRANS={json.dumps(TRANSIENT)}, ORD={json.dumps(ORDER)},
      VNL_B={vnl_bounds}, VNL_HAS={json.dumps(sorted(vnl_set))};
const vnlSet=new Set(VNL_HAS);
const B=[[{C.SOUTH},{C.WEST}],[{C.NORTH},{C.EAST}]];
const map=L.map('map').fitBounds(B);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
 {{attribution:'Esri World Imagery'}}).addTo(map);
const CONC={conc};
if(CONC) L.geoJSON(CONC,{{style:{{fill:false,color:'#fff',weight:0.6,opacity:0.45}},
 onEachFeature:(f,l)=>{{const p=f.properties||{{}}; l.bindTooltip((p.nombre||'')+' — '+(p.operador||''));}}}}).addTo(map);
const g=L.layerGroup().addTo(map);
let raster=null;  // overlay de luz cruda
const vis={{PERF:true,FRAC:true,TERM:true,FLAR:true,PROD:true,PUEB:false,NOWC:true,RAW:false}};
const sl=document.getElementById('sl'), ymL=document.getElementById('ym'), ym2=document.getElementById('ym2'),
      cnt=document.getElementById('cnt'), rank=document.getElementById('rank');
function radius(a){{ return a==='NOWC'?6 : (TRANS.includes(a)?5 : (a==='FLAR'?5 : (a==='PROD'?2.5:2))); }}
function show(i){{
 const fr=FR[i]; ymL.textContent=fr.ym; ym2.textContent=fr.ym;
 // raster crudo
 if(vis.RAW && VNL_B && vnlSet.has(fr.ym)){{
   const url='vnl/'+fr.ym+'.png';   // relativo al propio HTML (que ya vive en assets/)
   if(!raster){{raster=L.imageOverlay(url,VNL_B,{{opacity:0.92}}).addTo(map);}} else {{raster.setUrl(url); if(!map.hasLayer(raster))raster.addTo(map);}}
   raster.bringToBack();
 }} else if(raster && map.hasLayer(raster)) {{ map.removeLayer(raster); }}
 // puntos
 g.clearLayers();
 const byop={{}}, byact={{}};
 const order=p=>p.a==='NOWC'?3:(TRANS.includes(p.a)?2:(p.a==='FLAR'?1:0));
 fr.pts.slice().sort((x,y)=>order(x)-order(y)).forEach(p=>{{
  byact[p.a]=(byact[p.a]||0)+1;
  if(!vis[p.a]) return;
  const col=COL[p.a]||'#888', tr=TRANS.includes(p.a), nw=p.a==='NOWC';
  L.circleMarker([p.la,p.lo],{{radius:radius(p.a),color:nw?'#e000e0':(p.c?'#fff':col),weight:nw?2:(p.c?1.3:0.6),
    fillColor:col,fillOpacity:nw?0.25:(tr?0.95:0.6),dashArray:nw?'3 2':null}})
   .bindPopup((p.s||'(sin pozo)')+'<br>'+p.e+'<br>'+(NM[p.a]||p.a)+(p.c?' · luz noct.':'')).addTo(g);
  if(tr) byop[p.e]=(byop[p.e]||0)+1;
 }});
 // conteos separados (en leyenda + panel)
 ORD.forEach(k=>{{document.getElementById('ct_'+k).textContent=byact[k]||0;}});
 cnt.innerHTML='🛠 Perforación: <b>'+(byact.PERF||0)+'</b> &nbsp; 💥 Fractura: <b>'+(byact.FRAC||0)+
   '</b> &nbsp; ✔ Terminación: <b>'+(byact.TERM||0)+'</b> &nbsp; 🔥 Flaring: '+(byact.FLAR||0)+
   ' &nbsp; ● Producción: '+(byact.PROD||0);
 const top=Object.entries(byop).sort((a,b)=>b[1]-a[1]).slice(0,8); const mx=top.length?top[0][1]:1;
 rank.innerHTML=top.map(([o,n])=>`<tr><td>${{o.slice(0,22)}}</td><td><span class="bar" style="width:${{Math.round(58*n/mx)}}px"></span> ${{n}}</td></tr>`).join('')||'<tr><td>—</td></tr>';
}}
// leyenda clickeable
document.querySelectorAll('.lg').forEach(el=>{{
  const cat=el.dataset.cat; if(!vis[cat]) el.classList.add('off');
  el.addEventListener('click',()=>{{vis[cat]=!vis[cat]; el.classList.toggle('off',!vis[cat]); show(+sl.value);}});
}});
sl.addEventListener('input',e=>show(+e.target.value));
let t=null; document.getElementById('play').addEventListener('click',function(){{
 if(t){{clearInterval(t);t=null;this.textContent='▶';return;}} this.textContent='⏸';
 t=setInterval(()=>{{let i=(+sl.value+1)%FR.length; sl.value=i; show(i);}},650);
}});
show(FR.length-1);
</script></body></html>"""
    OUT.write_text(html, encoding="utf-8")
    n_png = len(list((ASSETS / "vnl").glob("*.png"))) if (ASSETS / "vnl").exists() else 0
    print(f"guardado: {OUT}  ({len(frames)} meses, {len(rows)} filas) | rasters PNG: {n_png}")


if __name__ == "__main__":
    main()
