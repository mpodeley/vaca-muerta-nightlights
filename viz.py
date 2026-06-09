#!/usr/bin/env python
"""Dashboard de actividad nocturna/operativa: mapa Leaflet + slider mensual + ranking por operador.
Lee activity.csv (de label.py) y dibuja, mes a mes, dónde hay PERFORACIÓN/FRACTURA/TERMINACIÓN,
coloreado por tipo, con anillo si está confirmado por satélite (sat_conf), y un panel de ranking de
operadores del mes. Overlay de concesiones (operador en tooltip). HTML autocontenido.

    ~/miniforge3/bin/mamba run -n insar python viz.py
"""
from __future__ import annotations
import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

COLORS = {"PERFORACION": "#ff7f0e", "FRACTURA": "#d62728", "TERMINACION": "#1f77b4"}
OUT = C.ROOT / "demo_actividad.html"


def main() -> None:
    if not (C.ROOT / "activity.csv").exists():
        sys.exit("Falta activity.csv — corré label.py primero.")
    with open(C.ROOT / "activity.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    by_month = defaultdict(list)
    for r in rows:
        by_month[r["ym"]].append({
            "lo": round(float(r["lon"]), 5), "la": round(float(r["lat"]), 5),
            "a": r["actividad"][:4], "e": r["empresa"], "s": r["sigla"],
            "c": int(r["sat_conf"] or 0)})
    months = sorted(by_month)
    frames = [{"ym": m, "pts": by_month[m]} for m in months]
    # ranking por operador acumulado (para el panel global) y por mes (en JS)
    top_ops = [op for op, _ in Counter(r["empresa"] for r in rows).most_common(12)]

    conc = "null"
    if C.CONCESIONES.exists():
        gj = json.load(open(C.CONCESIONES))
        conc = json.dumps(gj)

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<title>Actividad en Vaca Muerta — perforación / fractura / terminación</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 html,body,#map{{height:100%;margin:0}}
 .panel{{position:absolute;bottom:18px;left:50%;transform:translateX(-50%);z-index:1000;
   background:rgba(255,255,255,.95);padding:10px 16px;border-radius:8px;font:13px sans-serif;
   box-shadow:0 1px 6px rgba(0,0,0,.3);width:min(620px,90vw)}}
 #ym{{font-weight:bold}} input[type=range]{{width:100%}}
 .legend{{position:absolute;top:12px;right:12px;z-index:1000;background:rgba(255,255,255,.95);
   padding:8px 12px;border-radius:6px;font:12px sans-serif}}
 .rk{{position:absolute;top:12px;left:12px;z-index:1000;background:rgba(255,255,255,.95);
   padding:8px 12px;border-radius:6px;font:12px sans-serif;min-width:210px}}
 .sw{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:5px}}
 .bar{{height:9px;background:#999;display:inline-block;vertical-align:middle;border-radius:2px}}
 #play{{cursor:pointer;border:none;background:#334;color:#fff;border-radius:5px;padding:2px 9px}}
 table{{border-collapse:collapse}} td{{padding:1px 4px;font-size:11px}}
</style></head><body>
<div id="map"></div>
<div class="legend"><b>Actividad (ciclo de vida público)</b><br>
 <span class="sw" style="background:#ff7f0e"></span>Perforación<br>
 <span class="sw" style="background:#d62728"></span>Fractura<br>
 <span class="sw" style="background:#1f77b4"></span>Terminación<br>
 <span style="font-size:11px;color:#555">anillo amarillo = confirmado por luz nocturna</span>
</div>
<div class="rk"><b>Operadores activos — <span id="ym2"></span></b>
 <table id="rank"></table></div>
<div class="panel">
 <div><button id="play">▶</button> &nbsp;<b>Actividad</b> · <span id="ym"></span>
   &nbsp;<span id="cnt" style="color:#555"></span></div>
 <input type="range" id="sl" min="0" max="{len(frames)-1}" value="{len(frames)-1}" step="1">
 <div style="font-size:11px;color:#666;text-align:center">
   Fuente: ciclo de vida de pozos (Cap IV / Adjunto IV, Sec. Energía). Confirmación nocturna: VIIRS (si está cargada).</div>
</div>
<script>
const FR={json.dumps(frames)}, COL={json.dumps(COLORS)};
const B=[[{C.SOUTH},{C.WEST}],[{C.NORTH},{C.EAST}]];
const map=L.map('map').fitBounds(B);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
  {{attribution:'Esri World Imagery'}}).addTo(map);
const CONC={conc};
if(CONC) L.geoJSON(CONC,{{style:{{fill:false,color:'#fff',weight:0.6,opacity:0.5}},
  onEachFeature:(f,l)=>{{const p=f.properties||{{}}; l.bindTooltip((p.nombre||'')+' — '+(p.operador||''));}}}}).addTo(map);
const ACT={{PERF:'PERFORACION',FRAC:'FRACTURA',TERM:'TERMINACION'}};
const g=L.layerGroup().addTo(map);
const sl=document.getElementById('sl'), ymL=document.getElementById('ym'),
      ym2=document.getElementById('ym2'), cnt=document.getElementById('cnt'), rank=document.getElementById('rank');
function show(i){{
  g.clearLayers(); const fr=FR[i]; ymL.textContent=fr.ym; ym2.textContent=fr.ym;
  const byop={{}}; const byact={{}};
  fr.pts.forEach(p=>{{
    const col=COL[ACT[p.a]]||'#888';
    L.circleMarker([p.la,p.lo],{{radius:p.c?6:4,color:p.c?'#f5d800':col,weight:p.c?2:1,
      fillColor:col,fillOpacity:0.85}}).bindPopup(p.s+'<br>'+p.e+'<br>'+ACT[p.a]+(p.c?' · luz noct.':'')).addTo(g);
    byop[p.e]=(byop[p.e]||0)+1; byact[p.a]=(byact[p.a]||0)+1;
  }});
  cnt.textContent='· '+fr.pts.length+' eventos ('+Object.entries(byact).map(([k,v])=>k+':'+v).join(' ')+')';
  const top=Object.entries(byop).sort((a,b)=>b[1]-a[1]).slice(0,8);
  const mx=top.length?top[0][1]:1;
  rank.innerHTML=top.map(([o,n])=>`<tr><td>${{o.slice(0,22)}}</td><td><span class="bar" style="width:${{Math.round(60*n/mx)}}px"></span> ${{n}}</td></tr>`).join('')||'<tr><td>—</td></tr>';
}}
sl.addEventListener('input',e=>show(+e.target.value));
let t=null; document.getElementById('play').addEventListener('click',function(){{
  if(t){{clearInterval(t);t=null;this.textContent='▶';return;}} this.textContent='⏸';
  t=setInterval(()=>{{let i=(+sl.value+1)%FR.length; sl.value=i; show(i);}},650);
}});
show(FR.length-1);
</script></body></html>"""
    OUT.write_text(html, encoding="utf-8")
    print(f"guardado: {OUT}  ({len(frames)} meses, {sum(len(f['pts']) for f in frames)} eventos)")
    print(f"top operadores (global): {', '.join(top_ops[:6])}")


if __name__ == "__main__":
    main()
