# 💧 Water Resources App

🇬🇧 **English** · 🇩🇪 [Deutsch](README.de.md)

An interactive world map that shows how water is doing anywhere on Earth: current
weather, evaporation, changes in land water storage and water stress — for exactly the
region you are looking at.

**[wasser.maazi.de](https://wasser.maazi.de) — try it live**

The project is under active development and a lot will still change. This README has two
parts: a short guide for visitors of the live site, and a [section for developers](#for-developers).
Feedback and questions are welcome as issues in this repository.

## Why water?

- **Almost all of Earth's water is out of reach.** Over 97 % is salt water, and most of
  the fresh water is locked in glaciers, ice sheets or deep underground.
- **Water scarcity already affects billions of people.** Large parts of the world's
  population live with severe water scarcity for at least one month a year — not only in
  obviously dry regions.
- **The most important part is invisible.** Groundwater often drains over decades without
  any sign at the surface. NASA's GRACE satellites made visible how strongly regions like
  California's Central Valley, parts of northern India or the North China Plain have lost
  water — this app shows exactly this kind of data.
- **Water travels the world unseen.** Every imported T-shirt or cup of coffee carries
  "virtual water" used for its production somewhere else.
- **Climate change makes both extremes more likely**: more intense droughts and more
  intense heavy rain, often in the same regions.

Such numbers stay abstract as global averages. The idea of this app: show the same data
for the place you care about — your city, a holiday destination, a region in the news.

## What you can do

- **Explore the map**: zoom, pan, search for a place or use your own location.
- **Switch data layers**: current weather, evaporation, land water storage change
  (satellite data) and a water stress index — each layer colours the map by its own values.
- **Scroll through time**: a slider covers the last 30 days up to a short-term forecast.
- **Take results with you**: export the current view as an image or as raw data (CSV/JSON).
- **Adjust the look**: light, dark or eye-friendly mode.

Every value shown carries its source, licence and processing method. The guiding
principle: every number should be traceable to its origin instead of just being believed.

## Data sources

Only public, openly available data is used, among others from
[Open-Meteo](https://open-meteo.com), [NASA](https://www.nasa.gov) (POWER and the
GRACE/GRACE-FO satellite missions) and the [World Resources Institute](https://www.wri.org)
(Aqueduct). Licence and processing details per layer are shown in the app itself.

---

# For developers

## Principles

- **Transparency**: every API response carries a `provenance` block (source, licence,
  processing).
- **Users never talk to external APIs directly.** Only the backend does. The Earth is split
  into **1°×1° grid cells** and results are cached per cell (live weather 1 h, historical
  days 30 days), which decouples the number of users from API usage. A grid was chosen over
  administrative borders because the source data are grid-based themselves.
- **Always visualise, never leave blank**: the grid renders immediately; missing data is
  shown as its own (grey) state.
- **Honest naming**: GRACE measures the change of the *total* land water storage
  (groundwater, soil moisture, surface water, snow/ice), not the groundwater level.

## Architecture

```
Data sources → Flask backend (per-cell cache) → MapLibre frontend
```

| Path | Content |
|---|---|
| `backend/app.py` | Flask app: API routes, cell cache, SSE status console; also serves the frontend |
| `backend/layers.py` | Layer registry (status, colour scale, source) — add new layers here |
| `backend/data/` | Precomputed grids (water stress, GRACE), small and versioned |
| `frontend/index.html` | Whole frontend (MapLibre GL, MapTiler tiles) as a Jinja template |
| `scripts/` | One-off local preprocessing scripts for the static grids |

Routes: `/api/weather` (live or `date=YYYY-MM-DD`), `/api/evaporation`, `/api/groundwater`,
`/api/water-stress`, `/api/geocode`, `/api/layers`, `/api/config`, `/api/events` (SSE).

## Run locally

Requires Python 3.10+ and a free [MapTiler](https://www.maptiler.com) key.

```bash
cp .env.example .env          # add your MAPTILER_API_KEY
cd backend
python -m venv .venv
source .venv/bin/activate     # Linux/macOS  |  Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. The key is injected server-side and never lands in the repo.
`/?kiosk` shows only the map and a status line and reloads every 10 minutes (for smart
picture frames).

The static grids in `backend/data/*.json` are already in the repo. To rebuild them from new
raw data (WRI Aqueduct GDB, GRACE NetCDF in `datasets/`, not versioned):
`pip install -r scripts/requirements.txt`, then run `scripts/build_water_stress_grid.py`
and `scripts/build_groundwater_grid.py`. Never needed on the server.

## Deployment

Run Gunicorn behind a reverse proxy — **with a single worker process**:

```bash
gunicorn --workers 1 --threads 4 --bind 127.0.0.1:5000 app:app
```

Cache and SSE subscribers live in process memory. With several worker *processes* the
status console stops receiving events and the cache is filled per process. Threads share
memory and are fine. (Gunicorn does not run on Windows; use `python app.py` there.)

## Known limitations

- Only the cell centre is queried per cell, no true area aggregation.
- Exactly one layer is active at a time.
- **Water stress**: unweighted mean of all Aqueduct basins touching a cell.
- **GRACE**: latest month only, no time series.
- **Evaporation (NASA POWER)**: ~10 days latency, native ~0.5° data averaged to 1° cells.
- Open-Meteo returns `429` if the timeline is played very fast; affected cells turn grey.

## Roadmap

See [todo.md](todo.md) (in German): OpenStreetMap water bodies, ERA5 soil moisture/runoff,
GRACE time series, rate-limit backoff. Contributions, ideas and bug reports are welcome
as issues.
