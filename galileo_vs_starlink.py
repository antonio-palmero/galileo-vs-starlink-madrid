# %% [markdown]
# # Galileo vs Starlink · el cielo de Madrid en tiempo real
#
# Proyecto independiente basado en el *Satellite Orbit Explorer* (Space Career
# Week 2026 · GNSS Academy). Descarga los datos GP actuales de CelesTrak, elige
# dos satélites Galileo (MEO, ~23 200 km) y dos Starlink (LEO, ~480 km) y compara
# cómo se ven desde Madrid.
#
# 1. Configuración y datos en directo
#
# *Modelo: órbita kepleriana de dos cuerpos (como en el taller). Los registros GP
# son elementos medios de SGP4, así que es una aproximación educativa.*

# %%
# --- Paso 1: configuración y datos GP en directo de CelesTrak ---
# Convenios: fechas en UTC (con zona horaria), distancias en km, ángulos en grados.
import json, math
from datetime import datetime, timezone
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
