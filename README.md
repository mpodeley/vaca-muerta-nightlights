# Monitor de actividad nocturna — Vaca Muerta

Detecta y **etiqueta actividad de oil & gas** (perforación / fractura / terminación / flaring-producción)
cruzando la **huella lumínica nocturna** satelital (VIIRS) con las **concesiones** y el **ciclo de vida
de cada pozo** (fechas públicas). Producto: **mapa + slider temporal + ranking por operador**. Todo con
datos públicos/gratuitos. Derivado del trabajo InSAR (`subsidencia-vaca-muerta`), repo aparte.

## Idea

Las perforadoras y los *frac spreads* están **iluminados de noche** y la producción/terminación suele
**quemar gas (flaring)**. VIIRS **Nightfire (VNF)** detecta la combustión; VIIRS **Nightlights (VNL)**,
las luces. Con las **ventanas temporales de cada pozo** (perf/frac/term del Cap IV + Adjunto IV) como
ground-truth, una detección nocturna en el lugar y mes correctos se etiqueta con confianza.

## Pipeline

```
config.py            AOI (lon −70.6…−68.2, lat −39.2…−37.3), ventana, radios de match
data/fetch_wells.py  Cap IV pozos + fractura → wells.csv / frac.csv (coords + fechas perf/frac/term)   [CORRE]
data/fetch_eog.py    VIIRS VNL mensual + VNF (eogdata.mines.edu, token EOG)                              [necesita credencial]
detect.py            VNL/VNF → detections.csv (detecciones nocturnas mensuales)                          [CORRE; 0 sin EOG]
label.py             ciclo de vida → activity.csv (actividad+operador+concesión, + sat_conf si hay EOG)  [CORRE]
validate.py          recall/precisión de la luz nocturna vs eventos conocidos                            [necesita EOG]
viz.py               demo_actividad.html (mapa + slider + ranking por operador)                          [CORRE]
```

**Estado:** el producto de monitoreo **ya funciona con dato público** (20.178 eventos pozo-mes
2019–2026; top operadores YPF, Shell, Vista, Pluspetrol, Tecpetrol, PAE). La **capa de confirmación
satelital** (VIIRS) se enchufa al tener credencial EOG: `fetch_eog → detect` llena `detections.csv`,
y `label`/`validate` la incorporan automáticamente.

## Correr

```bash
M="~/miniforge3/bin/mamba run -n insar python"   # env con rasterio/shapely/folium/scipy
$M data/fetch_wells.py        # wells.csv + frac.csv (lee CSV del repo madre; ver config.SRC_DATA)
$M label.py                   # activity.csv
$M viz.py                     # demo_actividad.html  ← abrir en navegador
# capa satelital (con cuenta gratuita eogdata.mines.edu):
EOG_USER=... EOG_PASS=... $M data/fetch_eog.py
$M detect.py && $M label.py && $M validate.py && $M viz.py
```

## Caveats

- **Resolución VIIRS ~500–750 m** → etiqueta a nivel **pad-cluster**, no por-pad; en el core denso de
  Añelo se funden pads vecinos.
- **VNL = luces genéricas**; **VNF** desambigua combustión (flaring). Luz sin flare es ambigua.
- **Muestreo mensual**: jobs de fractura cortos (días) pueden promediarse/perderse; perforación (semanas)
  es más detectable. VNF nightly ayuda.
- **Atribución, no causalidad**; hay operaciones no detectables (sin flare, breves, nubladas).
- `fetch_eog.py`: los patrones de URL/tile de EOG cambian; se imprime la URL candidata para verificar en
  la primera corrida con token.

## Fuentes

- VIIRS VNL/VNF — Earth Observation Group, Colorado School of Mines (`eogdata.mines.edu`, registro gratis).
- Pozos (Cap IV) y fractura (Adjunto IV) — Secretaría de Energía (`datos.energia.gob.ar`).
- Concesiones — `estado-del-sistema` (operador por bloque).
