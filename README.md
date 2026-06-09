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
config.py                 AOI (lon −70.6…−68.2, lat −39.2…−37.3), ventana, radios de match
data/fetch_wells.py       Cap IV pozos + fractura → wells.csv / frac.csv (coords + fechas)          [CORRE]
data/fetch_blackmarble.py NASA Black Marble VNP46A3 (VIIRS nightlights mensual ~500m) → vnl/<ym>.tif [CORRE, Earthdata .netrc]
detect.py                 vnl/*.tif → detections.csv (bright spots mensuales)                      [CORRE]
label.py                  ciclo de vida → activity.csv (actividad+operador, + sat_conf)            [CORRE]
validate.py               recall/precisión de la luz nocturna vs eventos conocidos                [CORRE con detecciones]
viz.py                    demo_actividad.html (mapa + slider + ranking por operador)              [CORRE]
data/fetch_eog.py         alternativa VIIRS VNF/flares (eogdata.mines.edu) — auth migró a flujo de código,
                          no scriptable sin secret de cliente; superado por Black Marble.          [DEPRECADO]
```

**Fuente de luz nocturna:** se usa **NASA Black Marble VNP46A3** (VIIRS DNB mensual, gap-filled, ~500 m)
vía Earthdata (`~/.netrc`, las mismas credenciales de ASF/HyP3). Captura luces de equipos **y** flares
como radiancia (no los separa: sin VNF no hay discriminación por temperatura; un punto muy brillante y
persistente es muy probablemente flaring). EOG VNF quedó como alternativa deprecada (su auth migró a un
flujo de código no automatizable). Sanity: en un mes de prueba, ~90 % de las detecciones tienen un pozo
a <1.5 km.

**Estado:** el producto de monitoreo **ya funciona con dato público** (20.178 eventos pozo-mes
2019–2026; top operadores YPF, Shell, Vista, Pluspetrol, Tecpetrol, PAE). La **capa de confirmación
satelital** (VIIRS) se enchufa al tener credencial EOG: `fetch_eog → detect` llena `detections.csv`,
y `label`/`validate` la incorporan automáticamente.

## Correr

```bash
M="~/miniforge3/bin/mamba run -n insar python"   # env con rasterio/shapely/folium/scipy/earthaccess
$M data/fetch_wells.py        # wells.csv + frac.csv (lee CSV del repo madre; ver config.SRC_DATA)
$M data/fetch_blackmarble.py  # vnl/<ym>.tif (VIIRS nightlights mensual; usa ~/.netrc Earthdata)
$M detect.py                  # detections.csv (bright spots)
$M label.py                   # activity.csv (con confirmación satelital)
$M validate.py                # recall/precisión vs eventos conocidos
$M viz.py                     # demo_actividad.html  ← abrir en navegador
```

## Resultados (validación luz nocturna ↔ eventos de pozo, 2019–2026)

Cruzando 21.950 detecciones nocturnas (Black Marble) con 20.178 eventos de pozo (radio 1200 m, mismo mes):

| Métrica | Valor |
|---|---|
| Eventos confirmados por satélite | **71 %** (14.286/20.178) |
| Recall FRACTURA | **79 %** |
| Recall TERMINACIÓN | **70 %** |
| Recall PERFORACIÓN | **68 %** |
| Precisión (detección sobre evento perf/frac/term) | 16 % |

La **luz nocturna detecta ~7 de cada 10 operaciones conocidas** → buena sensibilidad. La precisión baja
es esperable: la mayoría de las luces son **producción/flaring de pozos viejos, facilidades y pueblos**
(Añelo, Neuquén, Cutral-Có), no eventos transitorios de perf/frac. Top operadores por actividad: YPF,
Shell, Vista, Pluspetrol, Tecpetrol, PAE.

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
