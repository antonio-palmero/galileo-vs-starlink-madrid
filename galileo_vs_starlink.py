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
