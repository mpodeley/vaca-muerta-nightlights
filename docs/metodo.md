# Método y validación

Pipeline 100 % reproducible con datos públicos/gratuitos. Derivado del trabajo InSAR de subsidencia.

## Fuentes

- **Luz nocturna:** NASA **Black Marble VNP46A3** (VIIRS DNB mensual, *gap-filled*, ~500 m), vía
  Earthdata (`earthaccess` + `~/.netrc`). Captura luces de equipos **y** flares como radiancia.
  *(EOG VIIRS Nightfire sería ideal para separar flaring por temperatura, pero su autenticación migró a
  un flujo no automatizable; quedó como alternativa deprecada.)*
- **Pozos:** Capítulo IV (Secretaría de Energía) — coordenadas + **fechas de perforación y terminación**.
- **Fractura:** Adjunto IV — **fechas de fractura**, agua y arena.
- **Concesiones:** polígonos con operador por bloque.

## Pasos

1. `data/fetch_wells.py` — pozos del AOI con su ciclo de vida (18.942 pozos; 3.655 fracturas).
2. `data/fetch_blackmarble.py` — descarga + mosaico + recorte de VNP46A3 → un raster mensual de
   radiancia nocturna (88 meses, 2019–2026).
3. `detect.py` — umbral por anomalía sobre el fondo rural → **detecciones puntuales** mensuales (21.950).
4. `label.py` — reglas espacio-temporales:
   - detección en la **ventana** de perforación/fractura/terminación de un pozo cercano → ese evento,
     **confirmado por satélite**;
   - detección cerca de un pozo ya **terminado** → **Flaring** (muy brillante) o **Producción**;
   - luz **persistente sin pozos** cerca → **Pueblo/ciudad** (excluida).
5. `validate.py` — *recall* y *precisión* de la luz nocturna contra los eventos conocidos.
6. `viz.py` — el dashboard (mapa + slider + ranking por operador).

## Detección mejorada (VNF) y nowcasting

**VIIRS Nightfire (VNF).** Además del DNB (luces), sumamos el survey anual de flares de EOG (combustión
por temperatura SWIR + volumen BCM). La capa **Flaring** pasa de un proxy por brillo a **combustión
real** atribuida por operador. Subió el recall de los eventos (FRAC 79→82 %, PERF 68→71 %, TERM 70→74 %).

**Nowcasting — adelantar el Cap IV.** El dato oficial llega con **lag mediano de ~13,5 meses**
(`analysis/lag.py`); el satélite lo ve al instante. Entrenamos un *gradient boosting*
(`features.py` → tabla pozo×mes con DNB + **change-detection** vs línea de base, VNF, persistencia,
vecindad, operador; `nowcast.py`) con **holdout temporal** (entrena ≤2023, testea 2024-2026):

| Objetivo | ROC-AUC (holdout) | PR-AUC | tasa base |
|---|---|---|---|
| **Perforación** | **0.85** | 0.33 | 0.033 |
| **Fractura** | **0.91** | 0.22 | 0.018 |

ROC-AUC 0.85–0.91 fuera de muestra = **skill predictivo real**; PR-AUC ~10–12× la tasa base (lift fuerte
pese al desbalance), mejorando la precisión del baseline de regla. La capa **Nowcast** del dashboard
marca, para el último mes, los pozos con probabilidad alta de perf/fractura **antes** de que el Cap IV
los publique.

## Caveats

- **Resolución VIIRS ~500 m** → actividad a nivel **pad-cluster**, no por-pad; en el core denso de Añelo
  se funden pads vecinos.
- **Sin separación física flaring/luces** (no usamos VNF por temperatura): el split Flaring/Producción es
  un **proxy por brillo**.
- **Muestreo mensual**: fracturas cortas (días) pueden perderse; la perforación (semanas) es más
  detectable — por eso el *recall* de fractura/terminación es algo mayor.
- **Atribución, no causalidad.** Hay operaciones no detectables (sin flare, breves, nubladas) y luces no
  productivas (caminos, plantas).

## Reproducir

```bash
M="mamba run -n insar python"
$M data/fetch_wells.py && $M data/fetch_blackmarble.py && $M data/fetch_vnf.py
$M detect.py && $M label.py && $M validate.py
$M analysis/lag.py && $M features.py && $M nowcast.py   # nowcasting
$M viz.py
```

Código: [github.com/mpodeley/vaca-muerta-nightlights](https://github.com/mpodeley/vaca-muerta-nightlights).
