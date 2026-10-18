"""Ebenen-Registry (siehe Abschnitt 13 im Projektplan).

Jede Datenebene wird hier einmal beschrieben statt im Code verstreut zu werden.
Das Frontend liest diese Liste über GET /api/layers und baut daraus das
Ebenen-Panel (gruppiert nach category). Ebenen mit status "planned" haben noch
keinen Endpoint — sie erscheinen im Panel als "kommt noch", siehe Abschnitt 5/9
im Plan für den jeweiligen Blocker (Datensatz-Auswahl, EULA, Speicher-Scoping).

"unit"/"supports_timeline" steuern das generische Frontend-Rendering (Legende,
Zeitachse an/aus) — jede neue Ebene mit eigenem Endpoint braucht diese Felder.
"""

LAYERS = [
    {
        "id": "current_weather",
        "category": "Kreislauf-Dynamik",
        "label": "Aktuelles Wetter",
        "phase": 1,
        "source": "Open-Meteo",
        "source_url": "https://open-meteo.com",
        "license": "CC BY 4.0",
        "status": "available",
        "cache_ttl_seconds": 3600,
        "endpoint": "/api/weather",
        "unit": "°C",
        "supports_timeline": True,
    },
    {
        "id": "evaporation_land",
        "category": "Kreislauf-Dynamik",
        "label": "Verdunstung (Landoberfläche)",
        "phase": 4,
        "source": "NASA POWER (EVLAND)",
        "source_url": "https://power.larc.nasa.gov",
        "license": "Public Domain (NASA)",
        "status": "available",
        "cache_ttl_seconds": 60 * 60 * 24,
        "endpoint": "/api/evaporation",
        "unit": "mm/Tag",
        "supports_timeline": False,
    },
    {
        # Bewusst NICHT "Grundwasserspiegel" genannt: GRACE misst die Änderung des
        # GESAMTEN terrestrischen Wasserspeichers (Grundwasser + Bodenfeuchte +
        # Oberflächenwasser + Schnee/Eis), keine isolierte Grundwassermessung —
        # siehe scripts/build_groundwater_grid.py und provenance.caveat.
        "id": "groundwater_grace",
        "category": "Wasserbestand",
        "label": "Landwasserspeicher-Änderung (GRACE)",
        "phase": 4,
        "source": "JPL GRACE/GRACE-FO Mascon RL06.3Mv04 CRI",
        "source_url": "https://grace.jpl.nasa.gov",
        "license": "Public Domain (NASA)",
        "status": "available",
        "cache_ttl_seconds": None,  # aktuell nur der neueste Monat, kein Ablauf
        "endpoint": "/api/groundwater",
        "unit": "cm (Anomalie)",
        "supports_timeline": False,
        # Vorzeichenbehaftete Größe (Verlust/Zuwachs ggü. Baseline) — anders als
        # die anderen Ebenen (0 = wenig/gut, hoch = viel/schlecht) braucht das
        # eine divergierende statt einer sequenziellen Farbskala, siehe Frontend.
        "color_scheme": "diverging",
    },
    {
        "id": "water_stress",
        "category": "Mensch & Gesellschaft",
        "label": "Wasserstress-Index",
        "phase": 4,
        "source": "WRI Aqueduct 4.0 (Baseline Water Stress)",
        "source_url": "https://www.wri.org/aqueduct",
        "license": "CC BY 4.0",
        "status": "available",
        "cache_ttl_seconds": None,  # statisch, kein Ablauf — siehe backend/data/water_stress_grid.json
        "endpoint": "/api/water-stress",
        "unit": "Score 0–5",
        "supports_timeline": False,
    },
    {
        "id": "surface_water_osm",
        "category": "Wasserbestand",
        "label": "Gewässerflächen (OSM)",
        "phase": 4,
        "source": "OpenStreetMap / Geofabrik-Extrakt",
        "source_url": "https://www.geofabrik.de",
        "license": "ODbL",
        "status": "planned",
        "cache_ttl_seconds": None,
        "endpoint": None,
        "unit": None,
        "supports_timeline": False,
        "blocked_reason": "Braucht eine Scoping-Entscheidung (welche Region als Extrakt laden, "
        "Speicher-/Bandbreitenbedarf) — siehe Abschnitt 5 im Plan, nicht ungefragt einen "
        "möglicherweise großen Datensatz herunterladen.",
    },
]


def layers_for_frontend():
    return [
        {k: v for k, v in layer.items() if k != "cache_ttl_seconds"}
        for layer in LAYERS
    ]


def get_layer(layer_id):
    for layer in LAYERS:
        if layer["id"] == layer_id:
            return layer
    return None
