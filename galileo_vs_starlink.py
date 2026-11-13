# %% [markdown]
# # Galileo vs Starlink · el cielo de Madrid en tiempo real
#
# Proyecto independiente basado en el *Satellite Orbit Explorer* (Space Career
# Week 2026 · GNSS Academy). Descarga los datos GP actuales de CelesTrak, elige
# dos satélites Galileo (MEO, ~23 200 km) y dos Starlink (LEO, ~480 km) y compara
# cómo se ven desde Madrid.
#
# 1. Configuración y datos en directo
# 2. Propagar las órbitas (ventana de 24 h que empieza ahora)
# 3. Visibilidad desde Madrid, gráficas y datos para la web
#
# *Modelo: órbita kepleriana de dos cuerpos (como en el taller). Los registros GP
# son elementos medios de SGP4, así que es una aproximación educativa.*

# %%
# --- Paso 1: configuración y datos GP en directo de CelesTrak ---
# Convenios: fechas en UTC (con zona horaria), distancias en km, ángulos en grados.
import json, math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# Constantes físicas
MU_EARTH_KM3_S2 = 398600.4418  # parámetro gravitacional de la Tierra (km^3/s^2)
EARTH_RADIUS_KM = 6378.137     # radio ecuatorial, usado como esfera (km)

# Observador: Madrid (Puerta del Sol)
OBSERVER = {'name': 'Madrid', 'lat_deg': 40.4168, 'lon_deg': -3.7038, 'alt_km': 0.65}
ELEVATION_MASK_DEG = 10        # por debajo de 10° de elevación no contamos el satélite como visible

# Grupos de CelesTrak y altura media de su capa operativa (km). El filtro deja fuera
# satélites en maniobra, de reserva o bajando para retirarse.
# (Starlink, nov 2026: ~9200 de 11195 están entre 460 y 500 km; otra capa a ~350 km)
GROUPS = {'GALILEO': (23000, 23400), 'STARLINK': (460, 500)}
SATS_PER_GROUP = 2             # 2 + 2 = 4 satélites
CACHE_HOURS = 2                # CelesTrak pide no consultar más a menudo
REQUIRED_GP_FIELDS = ('OBJECT_NAME', 'NORAD_CAT_ID', 'EPOCH', 'MEAN_MOTION',
                      'ECCENTRICITY', 'INCLINATION', 'RA_OF_ASC_NODE',
                      'ARG_OF_PERICENTER', 'MEAN_ANOMALY')

# Carpetas: data/ guarda la caché de CelesTrak; outputs/ recibe gráficas y datos para la web
if '__file__' in globals():
    PROJECT_DIR = Path(__file__).resolve().parent
else:
    PROJECT_DIR = Path.cwd()  # "Run Cell" de VS Code arranca en la carpeta del script
DATA_DIR = PROJECT_DIR / 'data'
OUT_DIR = PROJECT_DIR / 'outputs'
for folder in (DATA_DIR, OUT_DIR):
    folder.mkdir(parents=True, exist_ok=True)


def fetch_gp_group(group):
    """Registros GP de un grupo: de la caché si tiene < CACHE_HOURS; si no, se descargan.
    Devuelve (registros, hora UTC de la descarga)."""
    cache_path = DATA_DIR / f'gp_{group}.json'
    now = datetime.now(timezone.utc)
    age_h = (now.timestamp() - cache_path.stat().st_mtime) / 3600 if cache_path.is_file() else None

    if age_h is None or age_h > CACHE_HOURS:
        # Certificados del sistema operativo (necesario si un antivirus inspecciona HTTPS)
        try:
            import truststore
            truststore.inject_into_ssl()
        except ImportError:
            pass
        url = f'https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=JSON'
        print(f'Downloading {url}')
        response = requests.get(url, timeout=30)
        if not response.ok:                # CelesTrak explica el motivo (p. ej. 403 por consultar demasiado)
            print(f'CelesTrak answered {response.status_code}: {response.text.strip()[:300]}')
        response.raise_for_status()
        response.json()                    # error claro si no es JSON
        cache_path.write_text(response.text, encoding='utf-8')  # solo se guarda si todo fue bien
        retrieved = now
    else:
        print(f'Using cache {cache_path.name} ({age_h:.1f} h old, limit {CACHE_HOURS} h)')
        retrieved = datetime.fromtimestamp(cache_path.stat().st_mtime, timezone.utc)

    records = json.loads(cache_path.read_text(encoding='utf-8'))
    if not isinstance(records, list) or not records:
        raise ValueError(f'{cache_path.name} has no GP records.')
    for rec in records:
        missing = [f for f in REQUIRED_GP_FIELDS if f not in rec]
        if missing:
            raise ValueError(f"{rec.get('OBJECT_NAME', '?')} in {cache_path.name} is missing: {missing}")
    return records, retrieved


def mean_altitude_km(rec):
    """Altura media a partir del movimiento medio: n (rev/día) -> a (3ª ley de Kepler) -> a - R."""
    n = 2 * math.pi * float(rec['MEAN_MOTION']) / 86400
    return (MU_EARTH_KM3_S2 / n**2) ** (1 / 3) - EARTH_RADIUS_KM


# Ejecutarlo: de cada grupo, los primeros por NORAD dentro de su capa operativa
sats, notes = [], []
for group, (alt_min, alt_max) in GROUPS.items():
    records, retrieved = fetch_gp_group(group)
    operational = [r for r in records if alt_min <= mean_altitude_km(r) <= alt_max]
    if len(operational) < SATS_PER_GROUP:
        raise ValueError(f'{group}: only {len(operational)} satellites between {alt_min} and {alt_max} km.')
    chosen = sorted(operational, key=lambda r: int(r['NORAD_CAT_ID']))[:SATS_PER_GROUP]
    for rec in chosen:
        rec['GROUP'] = group               # recordamos de qué grupo viene cada satélite
    sats += chosen
    notes.append(f'{group} {len(chosen)} of {len(records)} '
                 f'({len(operational)} in the {alt_min}-{alt_max} km shell), '
                 f'retrieved {retrieved:%Y-%m-%d %H:%M} UTC')

source_note = 'CelesTrak GP data (OMM JSON): ' + '; '.join(notes)
print(source_note)
print(f"Observer: {OBSERVER['name']} ({OBSERVER['lat_deg']:.4f} N, {OBSERVER['lon_deg']:.4f} E), "
      f'elevation mask {ELEVATION_MASK_DEG} deg')
for s in sats:
    print(f"  {s['GROUP']:<9} {s['OBJECT_NAME']:<25} NORAD {s['NORAD_CAT_ID']:>6}   "
          f"EPOCH {s['EPOCH'][:19]}   mean alt {mean_altitude_km(s):8.1f} km")

# %% [markdown]
# ## Paso 2 · Propagar las órbitas
#
# La ventana empieza **ahora** (redondeado al minuto) y dura 24 h: así lo que
# calculamos es lo que está pasando en el cielo de Madrid hoy. Cada satélite se
# propaga desde su propio epoch con el modelo de dos cuerpos del taller (Kepler +
# rotación de Greenwich). Cuanto más lejos del epoch, más error: en Starlink, tan
# bajo, el rozamiento con la atmósfera (que este modelo no tiene) lo hace crecer
# más rápido que en Galileo.

# %%
# --- Paso 2: propagar las órbitas ---
if 'sats' not in globals():
    raise NameError('sats is not defined: run the Step 1 cell first.')

STEP_SECONDS = 10      # 10 s: suficiente para seguir una pasada de Starlink de pocos minutos
DURATION_HOURS = 24
J2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)  # epoch de referencia del GMST


def parse_gp_elements(rec):
    """Un registro GP -> elementos de Kepler en unidades del modelo (km, rad, rad/s, fecha UTC)."""
    n = 2 * math.pi * float(rec['MEAN_MOTION']) / 86400        # rev/día -> rad/s
    return {
        'name': rec['OBJECT_NAME'].strip(),
        'norad_id': int(rec['NORAD_CAT_ID']),
        'group': rec['GROUP'],
        'epoch': datetime.fromisoformat(rec['EPOCH'].rstrip('Z')).replace(tzinfo=timezone.utc),
        'n_rad_s': n,
        'a_km': (MU_EARTH_KM3_S2 / n**2) ** (1 / 3),            # tercera ley de Kepler
        'e': float(rec['ECCENTRICITY']),
        'i_rad': math.radians(float(rec['INCLINATION'])),
        'raan_rad': math.radians(float(rec['RA_OF_ASC_NODE'])),
        'argp_rad': math.radians(float(rec['ARG_OF_PERICENTER'])),
        'M0_rad': math.radians(float(rec['MEAN_ANOMALY'])),
    }


def solve_kepler(M, e, tol=1e-12, max_iter=50):
    """Resuelve M = E - e*sin(E) para la anomalía excéntrica E (Newton-Raphson)."""
    E = math.pi if e > 0.8 else M
    for _ in range(max_iter):
        dE = (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
        E -= dE
        if abs(dE) < tol:
            return E
    raise RuntimeError(f'Kepler solver did not converge (M={M}, e={e}).')


def gmst_rad(t):
    """Tiempo sidéreo medio de Greenwich (IAU-1982): ángulo de rotación de la Tierra en rad."""
    d = (t - J2000).total_seconds() / 86400
    T = d / 36525
    return math.radians((280.46061837 + 360.98564736629 * d
                         + 0.000387933 * T**2 - T**3 / 38710000) % 360)


def propagate(el, times):
    """Dos cuerpos: para cada instante, posición ECEF (km) y lat/lon/alt sobre una Tierra esférica."""
    a, e, i = el['a_km'], el['e'], el['i_rad']
    raan, argp = el['raan_rad'], el['argp_rad']
    points = []
    for t in times:
        M = (el['M0_rad'] + el['n_rad_s'] * (t - el['epoch']).total_seconds()) % (2 * math.pi)
        E = solve_kepler(M, e)
        r = a * (1 - e * math.cos(E))                                   # radio
        nu = math.atan2(math.sqrt(1 - e**2) * math.sin(E), math.cos(E) - e)  # anomalía verdadera
        u = argp + nu                                                   # argumento de latitud
        # Inercial (ECI): girar el plano de la órbita según RAAN e inclinación
        x = r * (math.cos(raan) * math.cos(u) - math.sin(raan) * math.sin(u) * math.cos(i))
        y = r * (math.sin(raan) * math.cos(u) + math.cos(raan) * math.sin(u) * math.cos(i))
        z = r * math.sin(u) * math.sin(i)
        # Fija a la Tierra (ECEF): deshacer la rotación de la Tierra
        th = gmst_rad(t)
        xf, yf = math.cos(th) * x + math.sin(th) * y, -math.sin(th) * x + math.cos(th) * y
        points.append({'time': t, 'ecef_km': (xf, yf, z), 'eci_km': (x, y, z),
                       'lat_deg': math.degrees(math.atan2(z, math.hypot(xf, yf))),
                       'lon_deg': math.degrees(math.atan2(yf, xf)),
                       'alt_km': r - EARTH_RADIUS_KM})
    return points


# Comprobaciones del propagador (las mismas que en el taller)
assert abs(math.degrees(gmst_rad(J2000)) - 280.46) < 0.01, 'GMST at J2000 should be ~280.46 deg'
for M_test in (0.1, 1.0, 3.0, 5.5):
    for e_test in (0.0, 0.1, 0.5, 0.9):
        E_test = solve_kepler(M_test, e_test)
        assert abs(E_test - e_test * math.sin(E_test) - M_test) < 1e-10, 'Kepler residual too large'

# Ventana: desde ahora (redondeado al minuto) durante DURATION_HOURS
start = datetime.now(timezone.utc).replace(second=0, microsecond=0)
end = start + timedelta(hours=DURATION_HOURS)
n_points = int((end - start).total_seconds()) // STEP_SECONDS + 1
times = [start + timedelta(seconds=k * STEP_SECONDS) for k in range(n_points)]

elements = [parse_gp_elements(s) for s in sats]
tracks = [propagate(el, times) for el in elements]

print(f'Window (UTC): {start:%Y-%m-%d %H:%M} -> {end:%Y-%m-%d %H:%M}, step {STEP_SECONDS} s, {n_points} points')
print(f"{'Satellite':<25} {'Period':>9} {'Perigee':>9} {'Apogee':>9} {'i':>9}  {'Epoch age':>10}")
for el, pts in zip(elements, tracks):
    period_h = 2 * math.pi / el['n_rad_s'] / 3600
    age_h = (start - el['epoch']).total_seconds() / 3600
    print(f"{el['name']:<25} {period_h:>7.3f} h {el['a_km'] * (1 - el['e']) - EARTH_RADIUS_KM:>6.1f} km "
          f"{el['a_km'] * (1 + el['e']) - EARTH_RADIUS_KM:>6.1f} km {math.degrees(el['i_rad']):>5.2f} deg"
          f"{age_h:>8.1f} h")
    # Comprobación: el periodo coincide con la constelación (Galileo ~14,08 h; Starlink ~1,57 h)
    expected = {'GALILEO': (14.0, 14.2), 'STARLINK': (1.5, 1.6)}[el['group']]
    assert expected[0] <= period_h <= expected[1], f"{el['name']}: period {period_h:.3f} h out of {expected}"
print('Checks passed: GMST, Kepler solver and periods of both constellations.')

# %% [markdown]
# ## Paso 3 · Visibilidad desde Madrid
#
# Para cada instante pasamos el vector Madrid -> satélite a ejes locales **ENU**
# (Este, Norte, Arriba). De ahí salen el **azimut** (rumbo desde el Norte, en
# sentido horario) y la **elevación** (altura sobre el horizonte). Un satélite
# cuenta como visible cuando su elevación supera la máscara de 10°: por debajo,
# edificios, montañas y la atmósfera lo tapan o degradan la señal.
#
# Una **pasada** es un tramo continuo por encima de la máscara. Las horas de salida
# y puesta se interpolan entre las dos muestras que cruzan los 10°.
#
# Qué esperar: Starlink, a ~480 km, cruza el cielo en pocos minutos y muchas veces
# al día; Galileo, a ~23 200 km, se mueve despacio y se queda horas a la vista.

# %%
# --- Paso 3: azimut/elevación, pasadas, gráficas y datos para la web ---
if 'tracks' not in globals():
    raise NameError('tracks is not defined: run the Step 2 cell first.')

import matplotlib.pyplot as plt

WEB_STEP_S = 30   # una muestra cada 30 s en el JSON de la web (una pasada de Starlink: ~10-20 puntos)
GROUP_COLORS = {'GALILEO': ['#1f77b4', '#17becf'], 'STARLINK': ['#d62728', '#ff7f0e']}  # azules / rojos
MODEL_NOTE = ('Two-body Kepler orbit from SGP4 mean elements, spherical Earth, simple Greenwich '
              'rotation, no atmospheric drag - an educational approximation.')


def observer_ecef(obs):
    """Posición ECEF (km) del observador sobre la Tierra esférica del modelo."""
    lat, lon = math.radians(obs['lat_deg']), math.radians(obs['lon_deg'])
    r = EARTH_RADIUS_KM + obs['alt_km']
    return (r * math.cos(lat) * math.cos(lon), r * math.cos(lat) * math.sin(lon), r * math.sin(lat))


def az_el_range(obs, sat_ecef):
    """Azimut (0-360°, desde el Norte hacia el Este), elevación (°) y distancia (km) a un satélite."""
    lat, lon = math.radians(obs['lat_deg']), math.radians(obs['lon_deg'])
    ox, oy, oz = observer_ecef(obs)
    dx, dy, dz = sat_ecef[0] - ox, sat_ecef[1] - oy, sat_ecef[2] - oz
    # Vector Madrid -> satélite en ejes locales Este, Norte, Arriba
    east = -math.sin(lon) * dx + math.cos(lon) * dy
    north = (-math.sin(lat) * math.cos(lon) * dx - math.sin(lat) * math.sin(lon) * dy
             + math.cos(lat) * dz)
    up = math.cos(lat) * math.cos(lon) * dx + math.cos(lat) * math.sin(lon) * dy + math.sin(lat) * dz
    rng = math.sqrt(dx**2 + dy**2 + dz**2)
    return math.degrees(math.atan2(east, north)) % 360, math.degrees(math.asin(up / rng)), rng


def find_passes(pts, mask=ELEVATION_MASK_DEG):
    """Tramos continuos con elevación >= mask. Salida/puesta interpoladas a la máscara.
    partial=True si la pasada ya había empezado al inicio o sigue al final de la ventana."""

    def cross(i, j):                     # instante entre las muestras i y j en que la elevación vale mask
        a, b = pts[i], pts[j]
        f = (mask - a['el_deg']) / (b['el_deg'] - a['el_deg'])
        return a['time'] + (b['time'] - a['time']) * f

    passes, k = [], 0
    while k < len(pts):
        if pts[k]['el_deg'] < mask:
            k += 1
            continue
        k0 = k                                       # primera muestra por encima de la máscara
        while k + 1 < len(pts) and pts[k + 1]['el_deg'] >= mask:
            k += 1                                   # k: última muestra por encima
        rise = cross(k0 - 1, k0) if k0 > 0 else pts[k0]['time']
        set_ = cross(k, k + 1) if k + 1 < len(pts) else pts[k]['time']
        top = max(pts[k0:k + 1], key=lambda p: p['el_deg'])
        passes.append({'rise': rise, 'set': set_, 'max_el_deg': top['el_deg'],
                       'duration_min': (set_ - rise).total_seconds() / 60,
                       'partial': k0 == 0 or k + 1 == len(pts)})
        k += 1
    return passes


def utc(t):
    return f'{t:%Y-%m-%dT%H:%M:%SZ}'


# 1) Azimut/elevación de cada punto, color de cada satélite y sus pasadas
colors, all_passes = [], []
used = {g: 0 for g in GROUPS}
for el, pts in zip(elements, tracks):
    colors.append(GROUP_COLORS[el['group']][used[el['group']]])
    used[el['group']] += 1
    for p in pts:
        p['az_deg'], p['el_deg'], p['range_km'] = az_el_range(OBSERVER, p['ecef_km'])
    all_passes.append(find_passes(pts))

# Comprobación: desde el suelo, la distancia nunca puede ser menor que la altura del satélite
for el, pts in zip(elements, tracks):
    min_range = min(p['range_km'] for p in pts)
    min_alt = min(p['alt_km'] for p in pts)
    assert min_range >= min_alt - OBSERVER['alt_km'] - 1e-6, f"{el['name']}: range {min_range:.1f} < altitude"
print('Check passed: slant range is never shorter than the satellite altitude.')

# 2) Qué se ve ahora mismo y tabla de pasadas
print(f"\nRight now ({utc(start)}) from {OBSERVER['name']}:")
for el, pts in zip(elements, tracks):
    p = pts[0]
    state = 'VISIBLE' if p['el_deg'] >= ELEVATION_MASK_DEG else 'below mask'
    print(f"  {el['name']:<25} az {p['az_deg']:6.1f} deg  el {p['el_deg']:+6.1f} deg  "
          f"range {p['range_km']:8.0f} km  {state}")

print(f'\nPasses above {ELEVATION_MASK_DEG} deg in the next {DURATION_HOURS} h (UTC; * = cut by the window):')
for el, passes in zip(elements, all_passes):
    full = [ps for ps in passes if not ps['partial']]
    mean_dur = (f"{sum(ps['duration_min'] for ps in full) / len(full):.1f} min" if full
                else 'n/a (every pass is cut by the window)')
    visible_h = sum(ps['duration_min'] for ps in passes) / 60
    print(f"  {el['name']} [{el['group']}]: {len(passes)} passes, visible {visible_h:.1f} h in total, "
          f"mean full pass {mean_dur}")
    for ps in passes:
        print(f"    {ps['rise']:%m-%d %H:%M:%S} -> {ps['set']:%m-%d %H:%M:%S}  "
              f"{ps['duration_min']:7.1f} min  max el {ps['max_el_deg']:5.1f} deg{' *' if ps['partial'] else ''}")

# 3) Figura 1: elevación frente al tiempo (arriba Galileo, abajo Starlink)
fig, axes = plt.subplots(2, 1, figsize=(12, 6.5), sharex=True)
for ax, group in zip(axes, GROUPS):
    for el, pts, color in zip(elements, tracks, colors):
        if el['group'] == group:
            # bajo el horizonte no se dibuja (None corta la línea)
            ax.plot([p['time'] for p in pts], [p['el_deg'] if p['el_deg'] >= 0 else None for p in pts],
                    color=color, linewidth=1.6, label=el['name'])
    ax.axhline(ELEVATION_MASK_DEG, color='gray', linestyle='--', linewidth=1,
               label=f'{ELEVATION_MASK_DEG} deg mask')
    ax.set_ylim(0, 90)
    ax.set_ylabel('Elevation [deg]')
    ax.set_title(f"{group} seen from {OBSERVER['name']}", fontsize=10, loc='left')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(alpha=0.3)
axes[-1].set_xlabel('Time [UTC]')
fig.suptitle(f'Elevation over Madrid, {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC')
fig.tight_layout()
fig.savefig(OUT_DIR / 'elevation_madrid.png', dpi=200, bbox_inches='tight')
print(f"\nSaved {OUT_DIR / 'elevation_madrid.png'}")
plt.show()

# 4) Figura 2: skyplot (Norte arriba, sentido horario; centro = cenit, borde = horizonte)
fig = plt.figure(figsize=(7.5, 7.5))
ax = fig.add_subplot(projection='polar')
ax.set_theta_zero_location('N')
ax.set_theta_direction(-1)
for el, pts, color in zip(elements, tracks, colors):
    seg_az, seg_r, first = [], [], True
    for p in pts + [None]:                       # None final: cierra el último tramo
        if p is not None and p['el_deg'] >= 0:
            seg_az.append(math.radians(p['az_deg']))
            seg_r.append(90 - p['el_deg'])
        elif seg_az:                             # el satélite se ha puesto: dibujar ese tramo
            ax.plot(seg_az, seg_r, color=color, linewidth=1.4, label=el['name'] if first else None)
            first, seg_az, seg_r = False, [], []
    p0 = pts[0]                                  # posición ahora (inicio de la ventana)
    if p0['el_deg'] >= 0:
        ax.plot(math.radians(p0['az_deg']), 90 - p0['el_deg'], 'o', color=color, markersize=9,
                markeredgecolor='black')
ax.plot([math.radians(a) for a in range(361)], [90 - ELEVATION_MASK_DEG] * 361,
        color='gray', linestyle='--', linewidth=1)
ax.set_rlim(0, 90)
ax.set_rticks([30, 60, 90])
ax.set_yticklabels(['60°', '30°', '0°'])         # radio = 90 - elevación
ax.set_rlabel_position(112.5)                     # etiquetas de elevación lejos de N/E/S/W
ax.set_thetagrids(range(0, 360, 45), ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'])
ax.set_title(f"Sky over {OBSERVER['name']}, next {DURATION_HOURS} h (dots = now)", pad=20)
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.06), ncol=2, fontsize=8)
fig.savefig(OUT_DIR / 'skyplot_madrid.png', dpi=200, bbox_inches='tight')
print(f"Saved {OUT_DIR / 'skyplot_madrid.png'}")
plt.show()


# 5) Datos para el visor web (mismo esquema que el Satellite Orbit Explorer + campos de Madrid)
def orbit_regime(a_km):
    """LEO / MEO / GEO según la altura media."""
    alt = a_km - EARTH_RADIUS_KM
    return 'LEO' if alt < 2000 else 'MEO' if alt < 35000 else 'GEO'


def export_web_json(path, step_s=WEB_STEP_S):
    """JSON compacto para la web: metadatos + por satélite órbita, ECEF/ECI, az/el y pasadas."""
    if step_s % STEP_SECONDS:
        raise ValueError(f'step_s ({step_s} s) must be a multiple of STEP_SECONDS ({STEP_SECONDS} s).')
    every = step_s // STEP_SECONDS
    satellites = []
    for el, pts, passes, color in zip(elements, tracks, all_passes, colors):
        samples = pts[::every]
        if samples[-1] is not pts[-1]:
            samples.append(pts[-1])
        a, e = el['a_km'], el['e']
        satellites.append({
            'name': el['name'],
            'norad_id': el['norad_id'],
            'group': el['group'],
            'regime': orbit_regime(a),
            'color': color,
            'period_h': round(2 * math.pi / el['n_rad_s'] / 3600, 4),
            'perigee_km': round(a * (1 - e) - EARTH_RADIUS_KM, 1),
            'apogee_km': round(a * (1 + e) - EARTH_RADIUS_KM, 1),
            'i_deg': round(math.degrees(el['i_rad']), 3),
            'e': round(e, 7),
            'ecef': [[round(v, 1) for v in p['ecef_km']] for p in samples],
            'eci': [[round(v, 1) for v in p['eci_km']] for p in samples],
            'azel': [[round(p['az_deg'], 2), round(p['el_deg'], 2)] for p in samples],
            'passes': [{'rise_utc': utc(ps['rise']), 'set_utc': utc(ps['set']),
                        'max_el_deg': round(ps['max_el_deg'], 1),
                        'duration_min': round(ps['duration_min'], 1),
                        'partial': ps['partial']} for ps in passes],
        })
    data = {
        'start_utc': utc(start),
        'step_s': step_s,
        'n_points': len(satellites[0]['ecef']),
        'units': 'km',
        'earth_radius_km': EARTH_RADIUS_KM,
        'frames': {
            'ecef': 'Earth-fixed, spherical Earth (x to 0 deg lon, z to North pole)',
            'eci': 'ECEF rotated by +GMST (IAU-1982); pseudo-inertial of date, no precession/nutation',
        },
        'observer': {**OBSERVER, 'elevation_mask_deg': ELEVATION_MASK_DEG},
        'source': source_note,
        'model_note': MODEL_NOTE,
        'satellites': satellites,
    }
    text = json.dumps(data, separators=(',', ':'))   # compacto
    path.write_text(text, encoding='utf-8')
    # Los mismos datos como script: una web los carga con <script src=...>, también con doble clic (file://)
    path.with_suffix('.js').write_text(f'window.ORBITS_WEB_DATA = {text};\n', encoding='utf-8')
    print(f"Saved {path} and {path.with_suffix('.js').name} ({len(satellites)} satellites, "
          f"{data['n_points']} points each, every {step_s} s, {path.stat().st_size / 1024:.0f} KB)")
    return data


web_data = export_web_json(OUT_DIR / 'orbits_web.json')
assert all(len(s['azel']) == len(s['ecef']) == len(s['eci']) == web_data['n_points']
           for s in web_data['satellites']), 'azel/ecef/eci must have one entry per time step'
print('Check passed: azel, ecef and eci have one entry per time step for every satellite.')
