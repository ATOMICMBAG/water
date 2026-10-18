"""Phase-1-Backend: Karte + eine Datenebene (aktuelles Wetter) + Zoom/Suche
mit Statistik-Panel, siehe Abschnitt 8 im Projektplan.

Kernregel (Abschnitt 4): Das Frontend spricht nie direkt mit externen APIs.
Alles läuft über diese Flask-App, mit einem Cache pro 1°x1°-Rasterzelle.
"""

import datetime
import math
import os
import queue
import time
import json

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, Response, render_template, abort

from layers import layers_for_frontend, get_layer

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MAPTILER_API_KEY = os.environ.get("MAPTILER_API_KEY", "")

def load_static_grid(filename):
    """Lädt eine einmalig lokal vorgerechnete Ebene (Abschnitt 9) beim Start ins
    RAM — danach nie wieder externer Zugriff oder Laufzeit-Verarbeitung nötig.
    Siehe scripts/build_water_stress_grid.py bzw. build_groundwater_grid.py."""
    path = os.path.join(os.path.dirname(__file__), "data", filename)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data["cells"], data["meta"]
    except FileNotFoundError:
        return {}, {}


WATER_STRESS_GRID, WATER_STRESS_META = load_static_grid("water_stress_grid.json")
GROUNDWATER_GRID, GROUNDWATER_META = load_static_grid("groundwater_grid.json")

CELL_SIZE_DEG = 1.0
MAX_CELLS_PER_REQUEST = 100  # verhindert unbegrenzte Live-Calls bei weit rausgezoomter Karte
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
NASA_POWER_REGIONAL_URL = "https://power.larc.nasa.gov/api/temporal/daily/regional"
REQUEST_TIMEOUT_SECONDS = 10
NASA_POWER_TIMEOUT_SECONDS = 25  # regionale Abfragen brauchen spürbar länger als Open-Meteo

# NASA POWERs satellitengestützte Verdunstungsdaten (EVLAND) haben eine
# Verarbeitungsverzögerung; empirisch geprüft: 3 Tage zurück lieferte den
# Fehlwert -999, 10 Tage zurück einen echten Wert. Bewusst konservativ gewählt
# und im Frontend transparent als "Stand: <Datum>" ausgewiesen statt als "live".
EVAPORATION_LAG_DAYS = 10
EVAPORATION_FILL_VALUE = -999.0

# Ein vergangenes Kalenderdatum ändert sich nicht mehr (anders als "aktuelles
# Wetter"), daher lohnt ein deutlich längerer Cache als bei Live-Daten.
HISTORICAL_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30

# Eine Prognose für einen zukünftigen Tag wird von Open-Meteo mehrmals täglich
# aktualisiert (anders als ein historischer Tag) - kürzere TTL als beim Archiv,
# aber länger als "live", um nicht bei jedem Kartenschritt neu abzurufen.
FORECAST_CACHE_TTL_SECONDS = 60 * 60 * 3

# Empirisch geprüft (siehe README): Open-Meteos kostenlose Forecast-API deckt
# maximal 15 Tage im Voraus ab, danach kommt ein 400 "out of allowed range".
FORECAST_MAX_DAYS_AHEAD = 15

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "..", "frontend"),
    static_folder=os.path.join(os.path.dirname(__file__), "..", "frontend"),
    static_url_path="",
)

# --- Monitoring-Konsole (Abschnitt 12): einfache In-Process Pub/Sub für SSE. -----
# WICHTIG (in Produktion beobachtet, siehe todo.md): Diese Liste lebt nur im
# Speicher EINES Prozesses. Startet Gunicorn/Passenger mit mehreren
# Worker-PROZESSEN (nicht Threads), landet die offene SSE-Verbindung eines
# Nutzers in Prozess A, während ein nachfolgender API-Call (z.B. nach einer
# Ortssuche) von Prozess B beantwortet wird — dessen broadcast() erreicht dann
# nur Prozess B's eigene (leere) _subscribers-Liste, nie den Client in Prozess
# A. Die Konsole zeigt dann scheinbar "eingefroren" nichts Neues an, obwohl die
# Karte/Daten korrekt aktualisiert werden. Betrifft aus demselben Grund auch
# den Rasterzellen-Cache weiter unten. Fix: Gunicorn mit genau einem
# Worker-PROZESS starten (mehrere Threads sind unproblematisch, die teilen
# sich denselben Speicher): `gunicorn --workers 1 --threads 4 ...`.

_subscribers = []


def broadcast(event_type, message, **extra):
    payload = {"ts": time.time(), "type": event_type, "message": message, **extra}
    data = json.dumps(payload, ensure_ascii=False)
    for q in list(_subscribers):
        q.put(data)


@app.route("/api/events")
def events():
    def stream():
        q = queue.Queue()
        _subscribers.append(q)
        try:
            # Sofort eine Kommentarzeile senden: manche Reverse-Proxies puffern
            # die Antwort, bis eine Mindestmenge an Bytes da ist — ohne das hier
            # bleibt der Browser sonst "hängend" ohne je ein erstes Byte zu sehen.
            yield ": connected\n\n"
            while True:
                # Timeout + Ping: ohne das blockiert q.get() ewig, auch wenn der
                # Browser längst weg ist — der Thread wird nie frei (Gunicorn-
                # Threads sind endlich, siehe todo.md). Der Ping löst beim
                # nächsten Schreiben einen Fehler aus, sobald die Verbindung
                # tot ist, und der finally-Block räumt auf.
                try:
                    data = q.get(timeout=15)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                yield f"data: {data}\n\n"
        finally:
            _subscribers.remove(q)

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # falls doch mal hinter nginx statt Apache
            "Connection": "keep-alive",
        },
    )


# --- Cache pro Rasterzelle (Abschnitt 4) ------------------------------------
# Cache-Schlüssel ist (cell, when): "when" ist entweder "live" (aktuelles Wetter,
# kurze TTL) oder ein ISO-Datum "YYYY-MM-DD" (historischer Tag, lange TTL, siehe
# Abschnitt 8 Phase 2: Zeitreihen-Cache). Derselbe Multi-Prozess-Vorbehalt wie
# bei den SSE-Subscribern oben gilt auch hier — siehe dortigen Kommentar.

_cache = {}  # (cell_lon_idx, cell_lat_idx, when) -> {"data": {...}, "expires_at": epoch}


def cell_index(lon, lat):
    return (math.floor(lon / CELL_SIZE_DEG), math.floor(lat / CELL_SIZE_DEG))


def cell_center(cell_lon_idx, cell_lat_idx):
    return (
        cell_lon_idx * CELL_SIZE_DEG + CELL_SIZE_DEG / 2,
        cell_lat_idx * CELL_SIZE_DEG + CELL_SIZE_DEG / 2,
    )


def cell_bounds(cell_lon_idx, cell_lat_idx):
    return (
        cell_lon_idx * CELL_SIZE_DEG,
        cell_lat_idx * CELL_SIZE_DEG,
        (cell_lon_idx + 1) * CELL_SIZE_DEG,
        (cell_lat_idx + 1) * CELL_SIZE_DEG,
    )


def cells_in_bbox(min_lon, min_lat, max_lon, max_lat):
    lon_start, lat_start = cell_index(min_lon, min_lat)
    lon_end, lat_end = cell_index(max_lon, max_lat)
    cells = []
    for lon_idx in range(lon_start, lon_end + 1):
        for lat_idx in range(lat_start, lat_end + 1):
            cells.append((lon_idx, lat_idx))
    return cells


def fetch_current_weather_batch(cells):
    """Ruft Open-Meteo für alle übergebenen Zellen in einem einzigen HTTP-Call ab."""
    if not cells:
        return {}

    centers = [cell_center(*cell) for cell in cells]
    lats = ",".join(f"{lat:.4f}" for _, lat in centers)
    lons = ",".join(f"{lon:.4f}" for lon, _ in centers)

    try:
        resp = requests.get(
            OPEN_METEO_FORECAST_URL,
            params={"latitude": lats, "longitude": lons, "current_weather": "true"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        broadcast("error", f"Open-Meteo nicht erreichbar: {exc}", source="open-meteo")
        return {}

    # Open-Meteo liefert bei mehreren Koordinaten eine Liste, bei einer einzelnen
    # ein einzelnes Objekt zurück.
    results = payload if isinstance(payload, list) else [payload]

    fetched = {}
    now = time.time()
    layer = get_layer("current_weather")
    ttl = layer["cache_ttl_seconds"]
    for cell, result in zip(cells, results):
        current = result.get("current_weather")
        if current is None:
            continue
        fetched[cell] = current
        _cache[(*cell, "live")] = {"data": current, "expires_at": now + ttl}

    failed = len(cells) - len(fetched)
    message = f"{len(fetched)} Zelle(n) live von Open-Meteo abgerufen"
    if failed:
        message += f", {failed} ohne Daten in der Antwort"
    broadcast("live_call", message, source="open-meteo", cell_count=len(fetched))
    return fetched


def fetch_daily_batch(cells, date_str, base_url, source_label, ttl_seconds):
    """Gemeinsame Implementierung für einen Kalendertag mit Tages-Aggregaten:
    Open-Meteos Archiv-API (Vergangenheit, ERA5-Reanalyse) und Forecast-API
    (Zukunft, Prognosemodell) liefern dieselbe "daily"-Antwortform, nur die
    URL und die Bedeutung der Werte unterscheiden sich (Messung vs. Prognose).
    "temperature" ist eine Näherung (Mittel aus Tageshöchst-/Tiefstwert), da
    beide APIs keinen direkten Tagesmittelwert liefern — wird transparent so
    ausgewiesen (siehe provenance.processing in /api/weather)."""
    if not cells:
        return {}

    centers = [cell_center(*cell) for cell in cells]
    lats = ",".join(f"{lat:.4f}" for _, lat in centers)
    lons = ",".join(f"{lon:.4f}" for lon, _ in centers)

    try:
        resp = requests.get(
            base_url,
            params={
                "latitude": lats,
                "longitude": lons,
                "start_date": date_str,
                "end_date": date_str,
                "daily": "temperature_2m_max,temperature_2m_min,windspeed_10m_max",
                "timezone": "UTC",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        broadcast("error", f"{source_label} nicht erreichbar: {exc}", source=source_label)
        return {}

    results = payload if isinstance(payload, list) else [payload]

    fetched = {}
    now = time.time()
    for cell, result in zip(cells, results):
        daily = result.get("daily") or {}
        temps_max = daily.get("temperature_2m_max") or []
        temps_min = daily.get("temperature_2m_min") or []
        wind_max = daily.get("windspeed_10m_max") or []
        if not temps_max or not temps_min or temps_max[0] is None or temps_min[0] is None:
            continue
        data = {
            "temperature": round((temps_max[0] + temps_min[0]) / 2, 1),
            "windspeed": wind_max[0] if wind_max else None,
            "time": date_str,
        }
        fetched[cell] = data
        _cache[(*cell, date_str)] = {"data": data, "expires_at": now + ttl_seconds}

    failed = len(cells) - len(fetched)
    message = f"{len(fetched)} Zelle(n) für {date_str} von {source_label} abgerufen"
    if failed:
        message += f", {failed} ohne Daten in der Antwort"
    broadcast("live_call", message, source=source_label, cell_count=len(fetched))
    return fetched


def get_weather_for_cells(cells, when):
    """Liefert für jede angefragte Zelle Daten (falls vorhanden) + einen Status:
    'cached' (aus Cache bedient), 'live' (gerade frisch abgerufen) oder
    'unavailable' (Abfrage lief, aber keine Daten — z.B. Quelle down oder
    liefert für diese Koordinate nichts). Jede angefragte Zelle bekommt IMMER
    einen Eintrag, damit das Frontend das Rasterfeld auch ohne Daten zeichnen
    kann (siehe Abschnitt 7 im Plan: "immer visualisieren, nie leer lassen").

    "when" ist "live" für aktuelles Wetter oder ein ISO-Datum — je nachdem, ob
    das Datum in der Vergangenheit (Phase 2: Archiv) oder Zukunft (Phase 3:
    Prognose) liegt, wird intern die passende Open-Meteo-API gewählt."""
    now = time.time()
    data_by_cell = {}
    status_by_cell = {}
    missing = []

    for cell in cells:
        cached = _cache.get((*cell, when))
        if cached and cached["expires_at"] > now:
            data_by_cell[cell] = cached["data"]
            status_by_cell[cell] = "cached"
        else:
            missing.append(cell)

    if data_by_cell:
        broadcast(
            "cache_hit",
            f"{len(data_by_cell)} Zelle(n) aus Cache bedient",
            source="cache",
            cell_count=len(data_by_cell),
        )

    if missing:
        if when == "live":
            fetched = fetch_current_weather_batch(missing)
        elif datetime.date.fromisoformat(when) < datetime.date.today():
            fetched = fetch_daily_batch(
                missing, when, OPEN_METEO_ARCHIVE_URL, "open-meteo-archive", HISTORICAL_CACHE_TTL_SECONDS
            )
        else:
            fetched = fetch_daily_batch(
                missing, when, OPEN_METEO_FORECAST_URL, "open-meteo-forecast", FORECAST_CACHE_TTL_SECONDS
            )
        for cell in missing:
            if cell in fetched:
                data_by_cell[cell] = fetched[cell]
                status_by_cell[cell] = "live"
            else:
                status_by_cell[cell] = "unavailable"

    return data_by_cell, status_by_cell


# --- Verdunstung (Phase 4, NASA POWER) --------------------------------------
# Eigener Cache-Namensraum (4er-Tupel statt 3er), damit er nicht mit dem
# Wetter-Cache oben kollidiert. Anders als bei Open-Meteo liefert NASA POWERs
# "regional"-Endpoint direkt ein Punktraster für eine ganze Bounding Box in
# einem Aufruf — aber in einer nativen Auflösung (~0,5°x0,625°), die nicht mit
# unserem 1°-Raster übereinstimmt. Wir mitteln deshalb alle nativen Punkte, die
# in eine Zelle fallen — das wird transparent in provenance.processing gesagt.


def evaporation_reference_date():
    return datetime.date.today() - datetime.timedelta(days=EVAPORATION_LAG_DAYS)


def fetch_evaporation_for_bbox(cells, min_lon, min_lat, max_lon, max_lat, date_str):
    if not cells:
        return {}

    yyyymmdd = date_str.replace("-", "")
    try:
        resp = requests.get(
            NASA_POWER_REGIONAL_URL,
            params={
                "parameters": "EVLAND",
                "community": "AG",
                "longitude-min": min_lon,
                "longitude-max": max_lon,
                "latitude-min": min_lat,
                "latitude-max": max_lat,
                "start": yyyymmdd,
                "end": yyyymmdd,
                "format": "JSON",
            },
            timeout=NASA_POWER_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        broadcast("error", f"NASA POWER nicht erreichbar: {exc}", source="nasa-power")
        return {}

    # Native Punkte pro Zelle sammeln und mitteln.
    sums = {}
    counts = {}
    for feature in payload.get("features", []):
        lon, lat = feature["geometry"]["coordinates"][:2]
        value = feature["properties"]["parameter"]["EVLAND"].get(yyyymmdd)
        if value is None or value == EVAPORATION_FILL_VALUE:
            continue
        cell = cell_index(lon, lat)
        sums[cell] = sums.get(cell, 0.0) + value
        counts[cell] = counts.get(cell, 0) + 1

    fetched = {}
    now = time.time()
    ttl = get_layer("evaporation_land")["cache_ttl_seconds"]
    for cell in cells:
        if cell not in counts:
            continue
        avg = round(sums[cell] / counts[cell], 2)
        fetched[cell] = avg
        _cache[(*cell, "evap", date_str)] = {"data": avg, "expires_at": now + ttl}

    failed = len(cells) - len(fetched)
    message = f"{len(fetched)} Zelle(n) Verdunstung für {date_str} von NASA POWER abgerufen"
    if failed:
        message += f", {failed} ohne Daten in der Antwort"
    broadcast("live_call", message, source="nasa-power", cell_count=len(fetched))
    return fetched


def get_evaporation_for_cells(cells, min_lon, min_lat, max_lon, max_lat, date_str):
    now = time.time()
    data_by_cell = {}
    status_by_cell = {}
    missing = []

    for cell in cells:
        cached = _cache.get((*cell, "evap", date_str))
        if cached and cached["expires_at"] > now:
            data_by_cell[cell] = cached["data"]
            status_by_cell[cell] = "cached"
        else:
            missing.append(cell)

    if data_by_cell:
        broadcast(
            "cache_hit",
            f"{len(data_by_cell)} Zelle(n) Verdunstung aus Cache bedient",
            source="cache",
            cell_count=len(data_by_cell),
        )

    if missing:
        fetched = fetch_evaporation_for_bbox(missing, min_lon, min_lat, max_lon, max_lat, date_str)
        for cell in missing:
            if cell in fetched:
                data_by_cell[cell] = fetched[cell]
                status_by_cell[cell] = "live"
            else:
                status_by_cell[cell] = "unavailable"

    return data_by_cell, status_by_cell


# --- Routen ------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html", maptiler_key=MAPTILER_API_KEY)


@app.route("/api/layers")
def api_layers():
    return jsonify(layers_for_frontend())


@app.route("/api/config")
def api_config():
    """Konstanten, die Backend und Frontend synchron halten müssen (Abschnitt 4/7:
    Grid-Auflösung und Zellen-Limit), damit das Frontend beim optimistischen
    Vor-Zeichnen des Rasters (vor Eintreffen echter Daten) dieselbe Geometrie
    verwendet wie das Backend."""
    return jsonify(
        {
            "cell_size_deg": CELL_SIZE_DEG,
            "max_cells_per_request": MAX_CELLS_PER_REQUEST,
            "forecast_max_days_ahead": FORECAST_MAX_DAYS_AHEAD,
        }
    )


@app.route("/api/weather")
def api_weather():
    bbox_param = request.args.get("bbox")
    if not bbox_param:
        abort(400, "Query-Parameter 'bbox' fehlt (Format: minLon,minLat,maxLon,maxLat)")

    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox_param.split(","))
    except ValueError:
        abort(400, "bbox muss 4 kommagetrennte Zahlen sein: minLon,minLat,maxLon,maxLat")

    date_param = request.args.get("date")
    if date_param:
        try:
            requested_date = datetime.date.fromisoformat(date_param)
        except ValueError:
            abort(400, "date muss im Format YYYY-MM-DD sein")
        max_future_date = datetime.date.today() + datetime.timedelta(days=FORECAST_MAX_DAYS_AHEAD)
        if requested_date > max_future_date:
            abort(
                400,
                f"date darf höchstens {FORECAST_MAX_DAYS_AHEAD} Tage in der Zukunft liegen "
                "(Open-Meteos kostenloser Prognose-Horizont)",
            )
        when = date_param
    else:
        when = "live"

    cells = cells_in_bbox(min_lon, min_lat, max_lon, max_lat)

    if len(cells) > MAX_CELLS_PER_REQUEST:
        return jsonify(
            {
                "error": "area_too_large",
                "message": "Bitte weiter in die Karte hineinzoomen für Live-Daten.",
                "cell_count": len(cells),
                "max_cells": MAX_CELLS_PER_REQUEST,
            }
        )

    data_by_cell, status_by_cell = get_weather_for_cells(cells, when)

    # Jede angefragte Zelle bekommt einen Eintrag — auch ohne Daten — damit das
    # Frontend das Raster immer vollständig zeichnen kann (nur die Einfärbung
    # nach Werten entfällt bei status == "unavailable").
    cell_results = []
    temperatures = []
    status_counts = {"cached": 0, "live": 0, "unavailable": 0}
    for cell in cells:
        status = status_by_cell[cell]
        status_counts[status] += 1
        data = data_by_cell.get(cell)
        lon, lat = cell_center(*cell)
        min_lon_c, min_lat_c, max_lon_c, max_lat_c = cell_bounds(*cell)
        entry = {
            "cell": {"lon_idx": cell[0], "lat_idx": cell[1]},
            "center": {"lon": lon, "lat": lat},
            "bounds": {
                "min_lon": min_lon_c,
                "min_lat": min_lat_c,
                "max_lon": max_lon_c,
                "max_lat": max_lat_c,
            },
            "status": status,
            "temperature_c": None,
            "windspeed_kmh": None,
            "observed_at": None,
        }
        if data is not None:
            temperatures.append(data["temperature"])
            entry["temperature_c"] = data["temperature"]
            entry["windspeed_kmh"] = data["windspeed"]
            entry["observed_at"] = data["time"]
        cell_results.append(entry)

    if when == "live":
        mode = "live"
    elif datetime.date.fromisoformat(when) < datetime.date.today():
        mode = "historical"
    else:
        mode = "forecast"

    provenance_by_mode = {
        "live": {
            "source": "Open-Meteo",
            "source_url": "https://open-meteo.com",
            "license": "CC BY 4.0",
            "processing": "unveränderte aktuelle Messung/Kurzfrist-Modell pro Rasterzelle",
            "resolution_deg": CELL_SIZE_DEG,
            "cache_ttl_seconds": get_layer("current_weather")["cache_ttl_seconds"],
        },
        "historical": {
            "source": "Open-Meteo Historical Weather API (ERA5)",
            "source_url": "https://open-meteo.com/en/docs/historical-weather-api",
            "license": "CC BY 4.0",
            "processing": "Tagesmittel genähert aus Tageshöchst-/Tiefstwert (Reanalyse, gemessen)",
            "resolution_deg": CELL_SIZE_DEG,
            "cache_ttl_seconds": HISTORICAL_CACHE_TTL_SECONDS,
        },
        "forecast": {
            "source": "Open-Meteo Forecast API (Tagesprognose)",
            "source_url": "https://open-meteo.com/en/docs",
            "license": "CC BY 4.0",
            "processing": "Tagesmittel genähert aus prognostiziertem Tageshöchst-/Tiefstwert "
            "— Vorhersage, keine Messung",
            "resolution_deg": CELL_SIZE_DEG,
            "cache_ttl_seconds": FORECAST_CACHE_TTL_SECONDS,
        },
    }
    provenance = provenance_by_mode[mode]

    return jsonify(
        {
            "bbox": {
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
            },
            "when": when,
            "mode": mode,
            "cell_size_deg": CELL_SIZE_DEG,
            "cells": cell_results,
            "aggregate": {
                "avg_temperature_c": (
                    round(sum(temperatures) / len(temperatures), 1) if temperatures else None
                ),
                "cell_count": len(cell_results),
                "cached_count": status_counts["cached"],
                "live_count": status_counts["live"],
                "unavailable_count": status_counts["unavailable"],
            },
            "provenance": provenance,
        }
    )


@app.route("/api/evaporation")
def api_evaporation():
    bbox_param = request.args.get("bbox")
    if not bbox_param:
        abort(400, "Query-Parameter 'bbox' fehlt (Format: minLon,minLat,maxLon,maxLat)")

    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox_param.split(","))
    except ValueError:
        abort(400, "bbox muss 4 kommagetrennte Zahlen sein: minLon,minLat,maxLon,maxLat")

    cells = cells_in_bbox(min_lon, min_lat, max_lon, max_lat)

    if len(cells) > MAX_CELLS_PER_REQUEST:
        return jsonify(
            {
                "error": "area_too_large",
                "message": "Bitte weiter in die Karte hineinzoomen für Daten.",
                "cell_count": len(cells),
                "max_cells": MAX_CELLS_PER_REQUEST,
            }
        )

    date_str = evaporation_reference_date().isoformat()
    data_by_cell, status_by_cell = get_evaporation_for_cells(
        cells, min_lon, min_lat, max_lon, max_lat, date_str
    )

    cell_results = []
    values = []
    status_counts = {"cached": 0, "live": 0, "unavailable": 0}
    for cell in cells:
        status = status_by_cell[cell]
        status_counts[status] += 1
        value = data_by_cell.get(cell)
        lon, lat = cell_center(*cell)
        min_lon_c, min_lat_c, max_lon_c, max_lat_c = cell_bounds(*cell)
        if value is not None:
            values.append(value)
        cell_results.append(
            {
                "cell": {"lon_idx": cell[0], "lat_idx": cell[1]},
                "center": {"lon": lon, "lat": lat},
                "bounds": {
                    "min_lon": min_lon_c,
                    "min_lat": min_lat_c,
                    "max_lon": max_lon_c,
                    "max_lat": max_lat_c,
                },
                "status": status,
                "evaporation_mm": value,
                "observed_at": date_str if value is not None else None,
            }
        )

    return jsonify(
        {
            "bbox": {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat},
            "when": date_str,
            "mode": "reference_date",
            "cell_size_deg": CELL_SIZE_DEG,
            "cells": cell_results,
            "aggregate": {
                "avg_evaporation_mm": round(sum(values) / len(values), 2) if values else None,
                "cell_count": len(cell_results),
                "cached_count": status_counts["cached"],
                "live_count": status_counts["live"],
                "unavailable_count": status_counts["unavailable"],
            },
            "provenance": {
                "source": "NASA POWER (EVLAND, Community AG)",
                "source_url": "https://power.larc.nasa.gov",
                "license": "Public Domain (NASA)",
                "processing": f"Tageswert, gemittelt aus NASA POWERs nativem ~0,5°×0,625°-Raster auf "
                f"unsere 1°-Zellen. Stand {date_str} (~{EVAPORATION_LAG_DAYS} Tage Verarbeitungsverzug "
                "bei NASA — kein Live-/Echtzeitwert, siehe README).",
                "resolution_deg": CELL_SIZE_DEG,
                "cache_ttl_seconds": get_layer("evaporation_land")["cache_ttl_seconds"],
            },
        }
    )


@app.route("/api/water-stress")
def api_water_stress():
    """Wasserstress-Index (WRI Aqueduct 4.0, Baseline Water Stress). Anders als
    die anderen Ebenen kein externer Live-Call: die Werte kommen aus einer
    einmalig lokal vorgerechneten Datei (siehe scripts/build_water_stress_grid.py
    und Abschnitt 9 im Plan) — bewusst so gebaut, um den VPS nicht mit Downloads
    oder Geodaten-Verarbeitung zur Laufzeit zu belasten."""
    bbox_param = request.args.get("bbox")
    if not bbox_param:
        abort(400, "Query-Parameter 'bbox' fehlt (Format: minLon,minLat,maxLon,maxLat)")

    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox_param.split(","))
    except ValueError:
        abort(400, "bbox muss 4 kommagetrennte Zahlen sein: minLon,minLat,maxLon,maxLat")

    cells = cells_in_bbox(min_lon, min_lat, max_lon, max_lat)

    if len(cells) > MAX_CELLS_PER_REQUEST:
        return jsonify(
            {
                "error": "area_too_large",
                "message": "Bitte weiter in die Karte hineinzoomen.",
                "cell_count": len(cells),
                "max_cells": MAX_CELLS_PER_REQUEST,
            }
        )

    cell_results = []
    values = []
    status_counts = {"cached": 0, "live": 0, "unavailable": 0}
    for cell in cells:
        entry_data = WATER_STRESS_GRID.get(f"{cell[0]},{cell[1]}")
        status = "cached" if entry_data else "unavailable"
        status_counts[status] += 1
        lon, lat = cell_center(*cell)
        min_lon_c, min_lat_c, max_lon_c, max_lat_c = cell_bounds(*cell)
        score = entry_data["score"] if entry_data else None
        if score is not None:
            values.append(score)
        cell_results.append(
            {
                "cell": {"lon_idx": cell[0], "lat_idx": cell[1]},
                "center": {"lon": lon, "lat": lat},
                "bounds": {
                    "min_lon": min_lon_c,
                    "min_lat": min_lat_c,
                    "max_lon": max_lon_c,
                    "max_lat": max_lat_c,
                },
                "status": status,
                "water_stress_score": score,
                "basin_count": entry_data["basin_count"] if entry_data else None,
            }
        )

    return jsonify(
        {
            "bbox": {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat},
            "when": "static",
            "mode": "static",
            "cell_size_deg": CELL_SIZE_DEG,
            "cells": cell_results,
            "aggregate": {
                "avg_water_stress_score": round(sum(values) / len(values), 2) if values else None,
                "cell_count": len(cell_results),
                "cached_count": status_counts["cached"],
                "live_count": status_counts["live"],
                "unavailable_count": status_counts["unavailable"],
            },
            "provenance": {
                "source": WATER_STRESS_META.get("source", "WRI Aqueduct 4.0"),
                "source_url": "https://www.wri.org/aqueduct",
                "license": "CC BY 4.0",
                "processing": WATER_STRESS_META.get("aggregation", ""),
                "resolution_deg": CELL_SIZE_DEG,
                "cache_ttl_seconds": None,
            },
        }
    )


@app.route("/api/groundwater")
def api_groundwater():
    """Landwasserspeicher-Änderung (GRACE/GRACE-FO Mascon). Wie /api/water-stress
    rein aus einer lokal vorgerechneten Datei bedient — kein externer Call, keine
    NetCDF-Verarbeitung zur Laufzeit auf dem VPS. Zeigt aktuell nur den neuesten
    verfügbaren Monat (siehe scripts/build_groundwater_grid.py); die volle
    Monats-Zeitreihe (259 Monate seit 2002) ist eine mögliche spätere Ausbaustufe."""
    bbox_param = request.args.get("bbox")
    if not bbox_param:
        abort(400, "Query-Parameter 'bbox' fehlt (Format: minLon,minLat,maxLon,maxLat)")

    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox_param.split(","))
    except ValueError:
        abort(400, "bbox muss 4 kommagetrennte Zahlen sein: minLon,minLat,maxLon,maxLat")

    cells = cells_in_bbox(min_lon, min_lat, max_lon, max_lat)

    if len(cells) > MAX_CELLS_PER_REQUEST:
        return jsonify(
            {
                "error": "area_too_large",
                "message": "Bitte weiter in die Karte hineinzoomen.",
                "cell_count": len(cells),
                "max_cells": MAX_CELLS_PER_REQUEST,
            }
        )

    cell_results = []
    values = []
    status_counts = {"cached": 0, "live": 0, "unavailable": 0}
    for cell in cells:
        entry_data = GROUNDWATER_GRID.get(f"{cell[0]},{cell[1]}")
        status = "cached" if entry_data else "unavailable"
        status_counts[status] += 1
        lon, lat = cell_center(*cell)
        min_lon_c, min_lat_c, max_lon_c, max_lat_c = cell_bounds(*cell)
        value = entry_data["value_cm"] if entry_data else None
        if value is not None:
            values.append(value)
        cell_results.append(
            {
                "cell": {"lon_idx": cell[0], "lat_idx": cell[1]},
                "center": {"lon": lon, "lat": lat},
                "bounds": {
                    "min_lon": min_lon_c,
                    "min_lat": min_lat_c,
                    "max_lon": max_lon_c,
                    "max_lat": max_lat_c,
                },
                "status": status,
                "storage_anomaly_cm": value,
                "native_cell_count": entry_data["native_cell_count"] if entry_data else None,
            }
        )

    reference_month = GROUNDWATER_META.get("reference_month", "?")
    return jsonify(
        {
            "bbox": {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat},
            "when": reference_month,
            "mode": "reference_date",
            "cell_size_deg": CELL_SIZE_DEG,
            "cells": cell_results,
            "aggregate": {
                "avg_storage_anomaly_cm": round(sum(values) / len(values), 2) if values else None,
                "cell_count": len(cell_results),
                "cached_count": status_counts["cached"],
                "live_count": status_counts["live"],
                "unavailable_count": status_counts["unavailable"],
            },
            "provenance": {
                "source": GROUNDWATER_META.get("source", "JPL GRACE/GRACE-FO Mascon"),
                "source_url": "https://grace.jpl.nasa.gov",
                "license": "Public Domain (NASA)",
                "processing": GROUNDWATER_META.get("aggregation", "")
                + " "
                + GROUNDWATER_META.get("caveat", ""),
                "resolution_deg": CELL_SIZE_DEG,
                "cache_ttl_seconds": None,
            },
        }
    )


@app.route("/api/geocode")
def api_geocode():
    query = request.args.get("q", "").strip()
    if not query:
        abort(400, "Query-Parameter 'q' fehlt")

    try:
        resp = requests.get(
            OPEN_METEO_GEOCODE_URL,
            params={"name": query, "count": 5, "language": "de", "format": "json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        broadcast("error", f"Geocoding fehlgeschlagen: {exc}", source="open-meteo-geocoding")
        abort(502, "Geocoding-Dienst nicht erreichbar")

    broadcast("geocode", f"Ortssuche: '{query}'", source="open-meteo-geocoding")

    results = [
        {
            "name": r["name"],
            "country": r.get("country"),
            "lat": r["latitude"],
            "lon": r["longitude"],
        }
        for r in payload.get("results", [])
    ]
    return jsonify(results)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
        threaded=True,
    )
