#!/usr/bin/env python
"""Dashboard de actividad: mapa Leaflet + slider mensual + ranking por operador.

- Filtro ÚNICO por tipo: al elegir un tipo se ven juntos el dato oficial (Cap IV, relleno) y la
  predicción del modelo (nowcast, anillo punteado del MISMO color).
- Toggle maestro "Predicción" para mostrar/ocultar los anillos del nowcast.
- Conteos y ranking por operador abiertos en OFICIAL (+PREDICHO) — clave en meses puente con Cap IV
  incompleto.
- Overlay del dato crudo de luz nocturna (VIIRS) por timestep, toggleable.

    ~/miniforge3/bin/mamba run -n insar python viz.py
"""
from __future__ import annotations
import csv, json, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

COLORS = {"PERF": "#ff7f0e", "FRAC": "#d62728", "TERM": "#1f77b4",
          "FLAR": "#ffd400", "PROD": "#2ca02c", "PUEB": "#9e9e9e"}
NAME = {"PERF": "Perforación", "FRAC": "Fractura", "TERM": "Terminación",
        "FLAR": "Flaring", "PROD": "Producción", "PUEB": "Pueblo/ciudad"}
TRANSIENT = ["PERF", "FRAC", "TERM"]
ORDER = ["PERF", "FRAC", "TERM", "FLAR", "PROD", "PUEB"]
VNL_DIR = C.RAW / "vnl"
ASSETS = C.SITE_ASSETS
OUT = ASSETS / "demo_actividad.html"


def render_rasters():
    import numpy as np, rasterio
    from matplotlib import colormaps
    import matplotlib.pyplot as plt
    tifs = sorted(VNL_DIR.glob("*.tif"))
    if not tifs:
        return None, []
    outdir = ASSETS / "vnl"; outdir.mkdir(parents=True, exist_ok=True)
    vmax = 1.0; bounds = None
    for t in tifs:
        with rasterio.open(t) as s:
            a = s.read(1); b = s.bounds
        bounds = [[b.bottom, b.left], [b.top, b.right]]
        pos = a[np.isfinite(a) & (a > 0)]
        if pos.size:
            vmax = max(vmax, float(np.log1p(np.percentile(pos, 99.5))))
    cmap = colormaps["inferno"]
    for t in tifs:
        png = outdir / f"{t.stem}.png"
        if png.exists():
            continue
        with rasterio.open(t) as s:
            a = s.read(1).astype("float32")
        a = np.where(np.isfinite(a), a, 0.0)
        norm = np.clip(np.log1p(np.clip(a, 0, None)) / vmax, 0, 1)
        rgba = cmap(norm); rgba[..., 3] = np.clip(norm * 1.6, 0, 0.92); rgba[a <= 1.0, 3] = 0.0
        plt.imsave(png, rgba)
    return bounds, [t.stem for t in tifs]


def main() -> None:
    if not (C.ROOT / "activity.csv").exists():
        sys.exit("Falta activity.csv — corré label.py primero.")
    ASSETS.mkdir(parents=True, exist_ok=True)
    bounds, vnl_months = render_rasters()
    by_month = defaultdict(list)
    for r in csv.DictReader(open(C.ROOT / "activity.csv")):
        a = r["actividad"][:4]
        by_month[r["ym"]].append({"lo": round(float(r["lon"]), 5), "la": round(float(r["lat"]), 5),
                                  "a": a, "nw": 0, "op": r["empresa"] or "—",
                                  "info": (r["sigla"] or "(sin pozo)") + " · " + (r["empresa"] or "—"),
                                  "c": int(r["sat_conf"] or 0)})
    ncp = C.ROOT / "nowcast.csv"
    if ncp.exists():
        for r in csv.DictReader(open(ncp)):
            a = r["tipo"].upper()[:4]
            by_month[r["ym"]].append({"lo": round(float(r["lon"]), 5), "la": round(float(r["lat"]), 5),
                                      "a": a, "nw": 1, "op": r["empresa"] or "—",
                                      "info": "PREDICCIÓN · " + (r["empresa"] or "—") + " · p=" + r["prob"],
                                      "c": 0})
    months = sorted(by_month)
    frames = [{"ym": m, "pts": by_month[m]} for m in months]
    vnl_set = sorted(set(vnl_months))
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
  box-shadow:0 1px 6px rgba(0,0,0,.3);width:min(680px,94vw)}}
 #ym{{font-weight:bold}} input[type=range]{{width:100%}}
 .legend{{position:absolute;top:12px;right:12px;z-index:1000;background:rgba(255,255,255,.96);
  padding:8px 12px;border-radius:6px;font:12px sans-serif;user-select:none}}
 .lg{{cursor:pointer;padding:2px 3px;border-radius:4px}} .lg:hover{{background:#eee}}
 .lg.off{{opacity:.35;text-decoration:line-through}}
 .ct{{float:right;color:#444;font-weight:bold;margin-left:10px}}
 .rk{{position:absolute;top:12px;left:12px;z-index:1000;background:rgba(255,255,255,.96);
  padding:8px 12px;border-radius:6px;font:12px sans-serif;min-width:235px}}
 .sw{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:5px}}
 .bar{{height:9px;background:#ff7f0e;display:inline-block;vertical-align:middle}}
 .barp{{height:9px;background:repeating-linear-gradient(90deg,#ff7f0e,#ff7f0e 2px,#fff 2px,#fff 4px);
  display:inline-block;vertical-align:middle;border:1px solid #ff7f0e}}
 #play{{cursor:pointer;border:none;background:#334;color:#fff;border-radius:5px;padding:2px 9px}}
 table{{border-collapse:collapse}} td{{padding:1px 4px;font-size:11px}}
 .hd{{font-size:11px;color:#666;margin-bottom:3px}}
</style></head><body>
<div id="map"></div>
<div class="legend">
 <div class="hd"><b>Actividad O&G</b> · click = on/off · <span style="color:#444">oficial (relleno) +pred (anillo)</span></div>
 {legend_rows}
 <hr style="margin:5px 0;border:none;border-top:1px solid #ddd">
 <div class="lg" data-cat="PRED"><span class="sw" style="border:2px dashed #555;background:none"></span>Predicción (nowcast)</div>
 <div class="lg" data-cat="RAW"><span class="sw" style="background:#000;border:1px solid #999"></span>Luz nocturna (cruda)</div>
 <div style="font-size:10px;color:#666">relleno blanco-borde = confirmado por luz</div>
</div>
<div class="rk"><b>Actividad por operador — <span id="ym2"></span></b>
 <div style="font-size:10px;color:#666">barra llena = Cap IV · rayada = predicho</div>
 <table id="rank"></table></div>
<div class="panel">
 <div><button id="play">▶</button> &nbsp;<b>Vaca Muerta · actividad</b> · <span id="ym"></span></div>
 <div id="cnt" style="font-size:12px;color:#333;margin:3px 0"></div>
 <input type="range" id="sl" min="0" max="{len(frames)-1}" value="{len(frames)-1}" step="1">
 <div style="font-size:11px;color:#666;text-align:center">
  Cap IV / Adjunto IV + luz nocturna VIIRS (Black Marble + Nightfire). Predicción = modelo (holdout). Atribución, no causalidad.</div>
</div>
<script>
const FR={json.dumps(frames)}, COL={json.dumps(COLORS)}, NM={json.dumps(NAME)},
      TRANS={json.dumps(TRANSIENT)}, ORD={json.dumps(ORDER)},
      VNL_B={vnl_bounds}, VNL_HAS={json.dumps(vnl_set)};
const vnlSet=new Set(VNL_HAS);
const B=[[{C.SOUTH},{C.WEST}],[{C.NORTH},{C.EAST}]];
const map=L.map('map').fitBounds(B);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
 {{attribution:'Esri World Imagery'}}).addTo(map);
const CONC={conc};
if(CONC) L.geoJSON(CONC,{{style:{{fill:false,color:'#fff',weight:0.6,opacity:0.45}},
 onEachFeature:(f,l)=>{{const p=f.properties||{{}}; l.bindTooltip((p.nombre||'')+' — '+(p.operador||''));}}}}).addTo(map);
const g=L.layerGroup().addTo(map);
let raster=null;
const vis={{PERF:true,FRAC:true,TERM:true,FLAR:true,PROD:true,PUEB:false,PRED:true,RAW:false}};
const sl=document.getElementById('sl'), ymL=document.getElementById('ym'), ym2=document.getElementById('ym2'),
      cnt=document.getElementById('cnt'), rank=document.getElementById('rank');
function radius(a){{ return TRANS.includes(a)?5 : (a==='FLAR'?5 : (a==='PROD'?2.5:2)); }}
function show(i){{
 const fr=FR[i]; ymL.textContent=fr.ym; ym2.textContent=fr.ym;
 if(vis.RAW && VNL_B && vnlSet.has(fr.ym)){{
   const url='vnl/'+fr.ym+'.png';
   if(!raster){{raster=L.imageOverlay(url,VNL_B,{{opacity:0.92}}).addTo(map);}} else {{raster.setUrl(url); if(!map.hasLayer(raster))raster.addTo(map);}}
   raster.bringToBack();
 }} else if(raster && map.hasLayer(raster)) {{ map.removeLayer(raster); }}
 g.clearLayers();
 const offT={{}}, predT={{}}, ops={{}};
 const order=p=>(p.nw?3:(TRANS.includes(p.a)?2:(p.a==='FLAR'?1:0)));
 fr.pts.slice().sort((x,y)=>order(x)-order(y)).forEach(p=>{{
  if(p.nw) predT[p.a]=(predT[p.a]||0)+1; else offT[p.a]=(offT[p.a]||0)+1;
  if(!vis[p.a]) return; if(p.nw && !vis.PRED) return;
  const col=COL[p.a]||'#888', tr=TRANS.includes(p.a);
  if(p.nw){{
    L.circleMarker([p.la,p.lo],{{radius:6,color:col,weight:2.5,fill:false,opacity:0.95,dashArray:'3 3'}})
     .bindPopup(p.info+'<br>'+(NM[p.a]||p.a)).addTo(g);
    if(tr){{ ops[p.op]=ops[p.op]||{{o:0,p:0}}; ops[p.op].p++; }}
  }} else {{
    L.circleMarker([p.la,p.lo],{{radius:radius(p.a),color:p.c?'#fff':col,weight:p.c?1.3:0.6,
      fillColor:col,fillOpacity:tr?0.95:0.6}})
     .bindPopup(p.info+'<br>'+(NM[p.a]||p.a)+(p.c?' · luz noct.':'')).addTo(g);
    if(tr){{ ops[p.op]=ops[p.op]||{{o:0,p:0}}; ops[p.op].o++; }}
  }}
 }});
 ORD.forEach(k=>{{document.getElementById('ct_'+k).textContent=(offT[k]||0)+(predT[k]?(' +'+predT[k]):'');}});
 const cell=(k,emo)=>emo+' '+(NM[k])+': <b>'+(offT[k]||0)+'</b>'+(predT[k]?' <span style="color:#a0a">+'+predT[k]+'</span>':'');
 cnt.innerHTML=cell('PERF','🛠')+' &nbsp; '+cell('FRAC','💥')+' &nbsp; '+cell('TERM','✔')+
   ' &nbsp; 🔥 '+(offT.FLAR||0)+' &nbsp; ● '+(offT.PROD||0);
 const top=Object.entries(ops).sort((a,b)=>(b[1].o+b[1].p)-(a[1].o+a[1].p)).slice(0,8);
 const mx=top.length?Math.max(...top.map(x=>x[1].o+x[1].p)):1;
 rank.innerHTML=top.map(([o,v])=>`<tr><td>${{o.slice(0,20)}}</td><td><span class="bar" style="width:${{Math.round(54*v.o/mx)}}px"></span><span class="barp" style="width:${{Math.round(54*v.p/mx)}}px"></span> ${{v.o}}${{v.p?'+'+v.p:''}}</td></tr>`).join('')||'<tr><td>—</td></tr>';
}}
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
    print(f"guardado: {OUT}  ({len(frames)} meses)")


if __name__ == "__main__":
    main()
