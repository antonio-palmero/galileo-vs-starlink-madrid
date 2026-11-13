# Galileo vs Starlink · Madrid's sky in real time

How do two very different constellations look from the same place on Earth?
This project downloads today's orbital data from [CelesTrak](https://celestrak.org),
picks two **Galileo** satellites (MEO, ~23 200 km) and two **Starlink** satellites
(LEO, ~480 km), propagates their orbits and compares what an observer in **Madrid**
sees: how often each one rises, how long it stays above the horizon and how high it climbs.

> 🚧 Work in progress. Built step by step on top of my
> [Satellite Orbit Explorer](https://github.com/antonio-palmero/satellite-orbit-explorer)
> (Space Career Week 2026 · GNSS Academy).

## Roadmap

- [x] **1. Live data**: CelesTrak GP (OMM JSON) for the `GALILEO` and `STARLINK` groups,
      cached for 2 h (CelesTrak asks users not to poll), 2 satellites per group taken from
      each constellation's operational shell
- [ ] **2. Propagation**: two-body Kepler orbits over a 24 h window starting *now*
- [ ] **3. Visibility from Madrid**: azimuth/elevation, 10° mask, pass table and plots
- [ ] **4. Web page**: interactive 3D globe in real time plus Madrid's sky view

## Run it

```bash
pip install -r requirements.txt
python galileo_vs_starlink.py
```

The script is split into `# %%` cells, so it also runs cell by cell in VS Code or Jupyter.
Downloaded data goes to `data/` (not versioned); it is fetched again automatically when
it is more than 2 hours old.

## Model

Two-body Keplerian orbits on a spherical Earth. CelesTrak GP records are SGP4 mean
elements, so this is an educational approximation, not a precise orbit prediction.
