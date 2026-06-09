#!/usr/bin/env python
"""Dashboard de actividad: mapa Leaflet + slider mensual + ranking por operador.
Lee activity.csv (label.py). Colorea por tipo de actividad; eventos transitorios (perf/frac/term)
resaltados, producción/flaring/pueblo como contexto. Ranking = eventos transitorios por operador
(la actividad "nueva" del mes). HTML autocontenido.

    ~/miniforge3/bin/mamba run -n insar python viz.py
"""
from __future__ import annotations
import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

# color por actividad (clave = prefijo de 4 letras que se manda al JS)
COLORS = {"PERF": "#ff7f0e", "FRAC": "#d62728", "TERM": "#1f77b4",
          "FLAR": "#ffd400", "PROD": "#2ca02c", "PUEB": "#9e9e9e"}
NAME = {"PERF": "Perforación", "FRAC": "Fractura", "TERM": "Terminación",
        "FLAR": "Flaring", "PROD": "Producción", "PUEB": "Pueblo/ciudad"}
TRANSIENT = {"PERF", "FRAC", "TERM"}
OUT = C.ROOT / "demo_actividad.html"


def main() -> None:
    if not (C.ROOT / "activity.csv").exists():
        sys.exit("Falta activity.csv — corré label.py primero.")
    rows = list(csv.DictReader(open(C.ROOT / "activity.csv")))
    by_month = defaultdict(list)
    for r in rows:
        by_month[r["ym"]].append({
            "lo": round(float(r["lon"]), 5), "la": round(float(r["lat"]), 5),
            "a": r["actividad"][:4], "e": r["empresa"] or "—", "s": r["sigla"] or "",
            "c": int(r["sat_conf"] or 0)})
    months = sorted(by_month)
    frames = [{"ym": m, "pts": by_month[m]} for m in months]

    conc = json.dumps(json.load(open(C.CONCESIONES))) if C.CONCESIONES.exists() else "null"

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<title>Actividad en Vaca Muerta desde luz nocturna</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 html,body,#map{{height:100%;margin:0}}
 .panel{{position:absolute;bottom:18px;left:50%;transform:translateX(-50%);z-index:1000;
  background:rgba(255,255,255,.95);padding:10px 16px;border-radius:8px;font:13px sans-serif;
  box-shadow:0 1px 6px rgba(0,0,0,.3);width:min(640px,92vw)}}
 #ym{{font-weight:bold}} input[type=range]{{width:100%}}
 .legend{{position:absolute;top:12px;right:12px;z-index:1000;background:rgba(255,255,255,.95);
  padding:8px 12px;border-radius:6px;font:12px sans-serif}}
 .rk{{position:absolute;top:12px;left:12px;z-index:1000;background:rgba(255,255,255,.95);
  padding:8px 12px;border-radius:6px;font:12px sans-serif;min-width:215px}}
 .sw{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:5px}}
 .bar{{height:9px;background:#ff7f0e;display:inline-block;vertical-align:middle;border-radius:2px}}
 #play{{cursor:pointer;border:none;background:#334;color:#fff;border-radius:5px;padding:2px 9px}}
 table{{border-collapse:collapse}} td{{padding:1px 4px;font-size:11px}}
</style></head><body>
<div id="map"></div>
<div class="legend"><b>Actividad O&G</b><br>
 <span class="sw" style="background:#ff7f0e"></span>Perforación<br>
 <span class="sw" style="background:#d62728"></span>Fractura<br>
 <span class="sw" style="background:#1f77b4"></span>Terminación<br>
 <span class="sw" style="background:#ffd400"></span>Flaring<br>
 <span class="sw" style="background:#2ca02c"></span>Producción<br>
 <span class="sw" style="background:#9e9e9e"></span>Pueblo/ciudad<br>
 <span style="font-size:10px;color:#555">anillo = confirmado por luz nocturna</span>
</div>
<div class="rk"><b>Perf/Frac/Term — <span id="ym2"></span></b><table id="rank"></table></div>
<div class="panel">
 <div><button id="play">▶</button> &nbsp;<b>Vaca Muerta · actividad</b> · <span id="ym"></span>
  &nbsp;<span id="cnt" style="color:#555"></span></div>
 <input type="range" id="sl" min="0" max="{len(frames)-1}" value="{len(frames)-1}" step="1">
 <div style="font-size:11px;color:#666;text-align:center">
  Ciclo de vida de pozos (Cap IV / Adjunto IV) + luz nocturna VIIRS Black Marble. Atribución, no causalidad.</div>
</div>
<script>
const FR={json.dumps(frames)}, COL={json.dumps(COLORS)}, TRANS={json.dumps(sorted(TRANSIENT))},
      NM={json.dumps({k: NAME[k] for k in NAME})};
const B=[[{C.SOUTH},{C.WEST}],[{C.NORTH},{C.EAST}]];
const map=L.map('map').fitBounds(B);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
 {{attribution:'Esri World Imagery'}}).addTo(map);
const CONC={conc};
if(CONC) L.geoJSON(CONC,{{style:{{fill:false,color:'#fff',weight:0.6,opacity:0.45}},
 onEachFeature:(f,l)=>{{const p=f.properties||{{}}; l.bindTooltip((p.nombre||'')+' — '+(p.operador||''));}}}}).addTo(map);
const g=L.layerGroup().addTo(map);
const sl=document.getElementById('sl'), ymL=document.getElementById('ym'), ym2=document.getElementById('ym2'),
      cnt=document.getElementById('cnt'), rank=document.getElementById('rank');
function radius(a){{ return TRANS.includes(a)?5 : (a==='FLAR'?5 : (a==='PROD'?2.5:2)); }}
function show(i){{
 g.clearLayers(); const fr=FR[i]; ymL.textContent=fr.ym; ym2.textContent=fr.ym;
 const byop={{}}, byact={{}};
 // dibujar contexto primero (prod/flaring/pueblo), luego transitorios encima
 const order=p=>TRANS.includes(p.a)?2:(p.a==='FLAR'?1:0);
 fr.pts.slice().sort((x,y)=>order(x)-order(y)).forEach(p=>{{
  const col=COL[p.a]||'#888', tr=TRANS.includes(p.a);
  L.circleMarker([p.la,p.lo],{{radius:radius(p.a),color:p.c?'#fff':col,weight:p.c?1.3:0.6,
    fillColor:col,fillOpacity:tr?0.95:0.6}})
   .bindPopup((p.s||'(sin pozo)')+'<br>'+(p.e)+'<br>'+(NM[p.a]||p.a)+(p.c?' · luz noct.':'')).addTo(g);
  if(tr) byop[p.e]=(byop[p.e]||0)+1;
  byact[p.a]=(byact[p.a]||0)+1;
 }});
 cnt.textContent='· '+Object.entries(byact).map(([k,v])=>(NM[k]||k).slice(0,4)+':'+v).join(' ');
 const top=Object.entries(byop).sort((a,b)=>b[1]-a[1]).slice(0,8); const mx=top.length?top[0][1]:1;
 rank.innerHTML=top.map(([o,n])=>`<tr><td>${{o.slice(0,22)}}</td><td><span class="bar" style="width:${{Math.round(58*n/mx)}}px"></span> ${{n}}</td></tr>`).join('')||'<tr><td>—</td></tr>';
}}
sl.addEventListener('input',e=>show(+e.target.value));
let t=null; document.getElementById('play').addEventListener('click',function(){{
 if(t){{clearInterval(t);t=null;this.textContent='▶';return;}} this.textContent='⏸';
 t=setInterval(()=>{{let i=(+sl.value+1)%FR.length; sl.value=i; show(i);}},650);
}});
show(FR.length-1);
</script></body></html>"""
    OUT.write_text(html, encoding="utf-8")
    nt = sum(1 for r in rows if r["actividad"][:4] in TRANSIENT)
    print(f"guardado: {OUT}  ({len(frames)} meses, {len(rows)} filas, {nt} transitorias)")


if __name__ == "__main__":
    main()
