"""Einmalige Vorverarbeitung: WRI Aqueduct 4.0 (Baseline Water Stress) auf unser
1x1-Grad-Raster aggregieren, siehe Abschnitt 9 im Projektplan.

Läuft NICHT auf dem Produktions-VPS — bewusst als lokaler Vorverarbeitungsschritt
gedacht, damit der VPS nie die ~500 MB rohe File-Geodatabase sehen muss, sondern
nur das kleine Ergebnis (backend/data/water_stress_grid.json).

Voraussetzung: `datasets/aqueduct-global-maps-40-data/GDB/*.gdb` liegt lokal vor
(vom Nutzer manuell von WRI heruntergeladen, siehe Abschnitt 5).

Methode (bewusst einfach gehalten, siehe provenance.processing in der API):
Für jede 1x1-Grad-Zelle wird der einfache Mittelwert des bws_score aller
Aqueduct-Basins genommen, die die Zelle berühren (räumlicher Join auf
Bounding-Box/Intersects-Basis, keine exakte flächengewichtete Überlappung —
das wäre für ein einmaliges, transparent ausgewiesenes Ergebnis unverhältnismäßig
aufwändig). Basins mit bws_cat == -9999 ("No Data") werden vorher verworfen.

Aufruf: python scripts/build_water_stress_grid.py
"""

import json
import os

import geopandas as gpd
from shapely.geometry import box

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDB_PATH = os.path.join(
    PROJECT_ROOT, "datasets", "aqueduct-global-maps-40-data", "GDB", "Aq40_Y2023D07M05.gdb"
)
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "backend", "data", "water_stress_grid.json")
CELL_SIZE_DEG = 1.0  # muss zu CELL_SIZE_DEG in backend/app.py passen
NO_DATA_CAT = -9999.0


def build():
    print(f"Lese {GDB_PATH} …")
    gdf = gpd.read_file(GDB_PATH, layer="baseline_annual", columns=["bws_score", "bws_cat"])
    print(f"{len(gdf)} Basins gelesen, CRS={gdf.crs}")

    gdf = gdf[gdf["bws_cat"] != NO_DATA_CAT]
    print(f"{len(gdf)} Basins nach Ausschluss von 'No Data' (bws_cat == {NO_DATA_CAT})")

    min_lon, min_lat, max_lon, max_lat = gdf.total_bounds
    lon_start, lon_end = int(min_lon // CELL_SIZE_DEG), int(max_lon // CELL_SIZE_DEG)
    lat_start, lat_end = int(min_lat // CELL_SIZE_DEG), int(max_lat // CELL_SIZE_DEG)

    cells = [
        {"lon_idx": lon_idx, "lat_idx": lat_idx, "geometry": box(lon_idx, lat_idx, lon_idx + 1, lat_idx + 1)}
        for lon_idx in range(lon_start, lon_end + 1)
        for lat_idx in range(lat_start, lat_end + 1)
    ]
    grid = gpd.GeoDataFrame(cells, crs=gdf.crs)
    print(f"{len(grid)} Rasterzellen im Bounding-Box-Bereich der Basins")

    print("Räumlicher Join (kann 1-2 Minuten dauern) …")
    joined = gpd.sjoin(grid, gdf[["bws_score", "geometry"]], predicate="intersects")

    grouped = joined.groupby(["lon_idx", "lat_idx"])["bws_score"].agg(["mean", "count"])
    print(f"{len(grouped)} Rasterzellen mit mindestens einem Basin")

    result = {
        f"{int(lon_idx)},{int(lat_idx)}": {
            "score": round(float(mean), 2),
            "basin_count": int(count),
        }
        for (lon_idx, lat_idx), (mean, count) in grouped.iterrows()
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "meta": {
                    "source": "WRI Aqueduct 4.0 Baseline Water Stress (bws_score)",
                    "generated_from": "Aq40_Y2023D07M05.gdb, layer baseline_annual",
                    "cell_size_deg": CELL_SIZE_DEG,
                    "aggregation": "Mittelwert aller Basins, die die Zelle berühren "
                    "(Bounding-Box/Intersects, keine Flächengewichtung); "
                    "'No Data'-Basins (bws_cat=-9999) ausgeschlossen.",
                    "cell_count": len(result),
                },
                "cells": result,
            },
            f,
            ensure_ascii=False,
        )
    print(f"Geschrieben: {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH) / 1024:.0f} KB)")


if __name__ == "__main__":
    build()
