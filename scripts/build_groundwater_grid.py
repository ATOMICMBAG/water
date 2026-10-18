"""Einmalige Vorverarbeitung: JPL GRACE/GRACE-FO Mascon (Landwasserspeicher-
Anomalie) auf unser 1x1-Grad-Raster aggregieren, siehe Abschnitt 9 im Plan.

WICHTIG zur Begrifflichkeit (Transparenz-Prinzip, Abschnitt 1 im Plan): GRACE
misst NICHT den Grundwasserspiegel isoliert, sondern die Änderung des GESAMTEN
terrestrischen Wasserspeichers (Grundwasser + Bodenfeuchte + Oberflächenwasser +
Schnee/Eis + Biomassewasser zusammen) gegenüber dem Mittel 2004-2009. Die Ebene
heißt deshalb bewusst "Landwasserspeicher-Änderung", nicht "Grundwasserspiegel"
— eine echte Grundwasser-Isolierung bräuchte zusätzlich Bodenfeuchte-/
Oberflächenwassermodelle (z.B. GLDAS) zum Herausrechnen, das ist hier (noch)
nicht gemacht.

Läuft NICHT auf dem Produktions-VPS — lokaler Vorverarbeitungsschritt, Ergebnis
ist die kleine Datei backend/data/groundwater_grid.json (ca. 1-2 MB).

Voraussetzung: die vom Nutzer manuell von PO.DAAC heruntergeladene NetCDF-Datei
liegt unter datasets/ (Dateiname s.u.), siehe Abschnitt 9 im Plan.

Methode: Vom neuesten verfügbaren Monat (letzter Zeitindex) wird lwe_thickness
mit dem von JPL empfohlenen scale_factor korrigiert (wo verfügbar, sonst
Rohwert), auf Landzellen beschränkt (land_mask == 1), und die native 0,5°-
Auflösung durch einfachen Mittelwert auf unser 1°-Raster aggregiert. Die
Längengrad-Konvention der Quelle (0-360°) wird auf unsere (-180-180°)
umgerechnet.

Aufruf: python scripts/build_groundwater_grid.py
"""

import json
import os

import h5py
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NC_PATH = os.path.join(
    PROJECT_ROOT, "datasets", "GRCTellus.JPL.200204_202607.GLO.RL06.3M.MSCNv04CRI.nc"
)
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "backend", "data", "groundwater_grid.json")
CELL_SIZE_DEG = 1.0
FILL_VALUE_THRESHOLD = -99998  # JPLs Fill-Value ist -99999


def build():
    print(f"Lese {NC_PATH} …")
    with h5py.File(NC_PATH, "r") as f:
        time = f["time"][:]
        lat = f["lat"][:]
        lon = f["lon"][:]
        lwe = f["lwe_thickness"][-1]  # letzter (neuester) verfügbarer Monat
        land_mask = f["land_mask"][:]
        scale_factor = f["scale_factor"][:]
        time_epoch = f.attrs["time_epoch"]

    import datetime

    epoch_str = time_epoch.decode() if isinstance(time_epoch, bytes) else time_epoch
    epoch_date = datetime.datetime.fromisoformat(epoch_str.replace("Z", "+00:00")).date()
    reference_date = epoch_date + datetime.timedelta(days=float(time[-1]))
    print(f"Neuester verfügbarer Monat: {reference_date.isoformat()}")

    # Scale-Faktor anwenden, wo verfügbar (JPL-Empfehlung gegen Signal-Leckage),
    # sonst Rohwert. Fill-Werte (-99999) und Ozeanzellen ausschließen.
    valid = (lwe > FILL_VALUE_THRESHOLD) & (land_mask == 1)
    scale_valid = scale_factor > FILL_VALUE_THRESHOLD
    corrected = np.where(scale_valid, lwe * scale_factor, lwe)
    corrected = np.where(valid, corrected, np.nan)

    lon_180 = ((lon + 180) % 360) - 180  # 0..360 -> -180..180

    lat_grid, lon_grid = np.meshgrid(lat, lon_180, indexing="ij")
    df = pd.DataFrame(
        {
            "lon_idx": np.floor(lon_grid.ravel()).astype(int),
            "lat_idx": np.floor(lat_grid.ravel()).astype(int),
            "value": corrected.ravel(),
        }
    )
    df = df.dropna(subset=["value"])
    print(f"{len(df)} native 0,5°-Landzellen mit gültigem Wert")

    grouped = df.groupby(["lon_idx", "lat_idx"])["value"].agg(["mean", "count"])
    print(f"{len(grouped)} Rasterzellen (1°) nach Aggregation")

    result = {
        f"{int(lon_idx)},{int(lat_idx)}": {"value_cm": round(float(mean), 2), "native_cell_count": int(count)}
        for (lon_idx, lat_idx), (mean, count) in grouped.iterrows()
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "meta": {
                    "source": "JPL GRACE/GRACE-FO Mascon RL06.3Mv04 CRI (lwe_thickness)",
                    "reference_month": reference_date.strftime("%Y-%m"),
                    "cell_size_deg": CELL_SIZE_DEG,
                    "unit": "cm (Äquivalent-Wasserhöhe, Anomalie ggü. Mittel 2004-2009)",
                    "aggregation": "Neuester verfügbarer Monat; scale_factor angewendet wo "
                    "verfügbar (JPL-Empfehlung), sonst Rohwert; nur Landzellen "
                    "(land_mask==1); natives 0,5°-Raster durch Mittelwert auf 1°-Zellen "
                    "aggregiert.",
                    "caveat": "Misst die Änderung des GESAMTEN terrestrischen Wasserspeichers "
                    "(Grundwasser+Bodenfeuchte+Oberflächenwasser+Schnee/Eis), nicht "
                    "Grundwasser isoliert. Extreme Werte an Eisschild-Rändern (Grönland/"
                    "Antarktis) sind bekannte, plausible Langzeitsignale, keine Fehler.",
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
