# 💧 Wasser-Ressourcen-App

🇬🇧 [English](README.md) · 🇩🇪 **Deutsch**

Eine interaktive Weltkarte, die zeigt, wie es um Wasser an einem beliebigen Ort der
Erde steht: aktuelles Wetter, Verdunstung, Veränderung des Landwasserspeichers und
Wasserstress — für die Region, die du dir gerade ansiehst.

Dieses Projekt ist noch in aktiver Entwicklung — vieles wird sich noch ändern. Der
erste Teil dieser README ist ein Handbuch für Besucher der Live-Seite, der zweite Teil
([Für Entwickler](#für-entwickler)) erklärt Architektur, lokales Setup und Deployment.

**[wasser.maazi.de](https://wasser.maazi.de) — live ausprobieren**

## Status

Das Projekt befindet sich zwischen Grundgerüst und weiterem Ausbau — einzelne
Datenebenen und Funktionen kommen noch dazu. Feedback und Fragen sind willkommen, über
Issues in diesem Repository.

## Warum Wasser?

Wasser wirkt wie eine Selbstverständlichkeit — bis man genauer hinschaut:

- **Fast alles Wasser der Erde ist für uns unerreichbar.** Rund 70 % der Erdoberfläche
  sind von Wasser bedeckt, aber über 97 % davon ist Salzwasser. Von dem restlichen
  Süßwasser steckt der allergrößte Teil in Gletschern und Eisschilden oder tief im
  Untergrund. Was am Ende für Trinkwasser, Landwirtschaft und Industrie tatsächlich
  zugänglich ist, macht nur einen winzigen Bruchteil der gesamten Wassermenge der Erde
  aus.
- **Wassermangel betrifft heute schon Milliarden Menschen.** UN-Water und
  Forschungsarbeiten wie die von Mekonnen & Hoekstra gehen davon aus, dass ein großer
  Teil der Weltbevölkerung mindestens einen Monat im Jahr mit spürbarer Wasserknappheit
  lebt — nicht nur in offensichtlich trockenen Weltregionen.
- **Der wichtigste Teil ist unsichtbar.** Grundwasserspeicher leeren sich oft über
  Jahrzehnte, ohne dass an der Oberfläche etwas davon zu sehen ist. Erst die
  GRACE-Satellitenmissionen der NASA haben sichtbar gemacht, wie stark sich z. B. das
  kalifornische Central Valley, Teile Nordindiens oder die Nordchinesische Tiefebene
  in den letzten Jahrzehnten entleert haben — diese App zeigt genau solche Daten.
- **Wasser reist um die Welt, ohne dass man es sieht.** In jedem importierten
  T-Shirt, jeder Tasse Kaffee, jedem Stück Fleisch steckt "virtuelles Wasser" — die
  Wassermenge, die für die Produktion irgendwo anders auf der Welt verbraucht wurde.
  Wasserprobleme in einer Region sind dadurch oft mit Konsum in einer ganz anderen
  Region verknüpft.
- **Der Klimawandel macht beide Extreme wahrscheinlicher.** Ein wärmeres Klima
  beschleunigt den Wasserkreislauf — das begünstigt sowohl intensivere Dürren als
  auch intensivere Starkregen-Ereignisse, oft in denselben Regionen zu unterschiedlichen
  Jahreszeiten.

Diese Zahlen bleiben oft abstrakt, solange sie nur als globaler Durchschnitt in einem
Bericht stehen. Die Idee dieser App: dieselben Daten direkt für den Ort zeigen, der
gerade interessiert — die eigene Stadt, ein Urlaubsziel, eine Region in den
Nachrichten.

## Was du auf wasser.maazi.de machen kannst

- **Karte erkunden**: zoomen, verschieben, einen Ort suchen oder den eigenen Standort
  verwenden.
- **Zwischen Datenebenen wechseln**: aktuelles Wetter, Verdunstung, Veränderung des
  Landwasserspeichers (Satellitendaten) und ein Wasserstress-Index — jede Ebene färbt
  die Karte nach ihren eigenen Werten ein.
- **Durch die Zeit scrollen**: ein Regler zeigt Wetterdaten der letzten 30 Tage bis hin
  zu einer kurzfristigen Prognose.
- **Ergebnisse mitnehmen**: aktuelle Ansicht als Bild oder als Rohdaten (CSV/JSON)
  exportieren.
- **Darstellung anpassen**: hell, dunkel oder augenschonend — je nachdem, wie du die
  Karte gerade lesen willst.

Jeder angezeigte Wert ist in der App selbst mit seiner Quelle, Lizenz und
Verarbeitungsart hinterlegt — das Leitprinzip des Projekts ist, dass sich jede Zahl
empirisch bis zu ihrem Ursprung zurückverfolgen lässt, statt sie einfach zu glauben.

## Datenquellen

Die App bezieht ausschließlich öffentliche, frei zugängliche Daten, unter anderem von
[Open-Meteo](https://open-meteo.com), der [NASA](https://www.nasa.gov) (POWER-Projekt
und die GRACE/GRACE-FO-Satellitenmissionen) und dem
[World Resources Institute](https://www.wri.org) (Aqueduct). Details zu Lizenz und
Verarbeitung je Ebene stehen direkt in der App.

---

# Für Entwickler

## Leitprinzipien

- **Transparenz**: Jeder angezeigte Wert trägt Quelle, Lizenz und Verarbeitungsart mit
  sich (`provenance` in jeder API-Antwort). Die Zahlen sollen sich bis zum Ursprung
  zurückverfolgen lassen.
- **Nutzer sprechen nie direkt mit externen APIs.** Nur das Backend ruft Datenquellen ab.
  Die Erde ist in **1°×1°-Rasterzellen** unterteilt, das Ergebnis pro Zelle wird
  zwischengespeichert (Live-Wetter 1 h, historische Tage 30 Tage). Die Zahl der Nutzer
  ist so vom API-Verbrauch entkoppelt. Bewusst Raster statt Verwaltungsgrenzen: die
  Quelldaten sind selbst gitterbasiert, Ländergrenzen würden eine Genauigkeit vortäuschen,
  die die Quellen nicht liefern.
- **Immer visualisieren, nie leer lassen**: Das Raster erscheint sofort; fehlende Daten
  werden als eigener Zustand (grau) gezeigt statt als leere Karte.
- **Ehrliche Benennung**: GRACE misst die Änderung des *gesamten* Landwasserspeichers
  (Grund-, Boden-, Oberflächenwasser, Schnee/Eis), nicht den Grundwasserspiegel — die
  Ebene heißt deshalb „Landwasserspeicher-Änderung".

## Architektur

```
Datenquellen → Flask-Backend (Cache pro Rasterzelle) → MapLibre-Frontend
```

| Pfad | Inhalt |
|---|---|
| `backend/app.py` | Flask-App: API-Routen, Zellen-Cache, SSE-Statuskonsole, liefert auch das Frontend aus |
| `backend/layers.py` | Registry aller Datenebenen (Status, Farbskala, Quelle) — neue Ebenen hier eintragen |
| `backend/data/` | Vorberechnete Raster (Wasserstress, GRACE) — klein, im Repo versioniert |
| `frontend/index.html` | Komplettes Frontend (MapLibre GL, MapTiler-Kacheln), Jinja-Template |
| `scripts/` | Einmalige lokale Preprocessing-Skripte für die statischen Raster |

| Route | Zweck |
|---|---|
| `/api/weather` | Wetter pro Zelle, live oder mit `date=YYYY-MM-DD` historisch/Prognose (Open-Meteo) |
| `/api/evaporation` | Verdunstung (NASA POWER) |
| `/api/groundwater` | Landwasserspeicher-Änderung (GRACE/GRACE-FO, statisch) |
| `/api/water-stress` | Wasserstress-Index (WRI Aqueduct, statisch) |
| `/api/geocode` | Ortssuche (Open-Meteo Geocoding) |
| `/api/layers`, `/api/config` | Ebenen-Registry, Frontend-Konfiguration |
| `/api/events` | Server-Sent Events für die Status-Konsole |

## Lokal starten

Voraussetzungen: Python 3.10+ und ein [MapTiler](https://www.maptiler.com)-Key (kostenlos).

```bash
cp .env.example .env          # MAPTILER_API_KEY eintragen
cd backend
python -m venv .venv
source .venv/bin/activate     # Linux/macOS  |  Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Dann `http://127.0.0.1:5000` öffnen. Der MapTiler-Key wird serverseitig in das Template
eingesetzt und landet nie im Repo. Tipp: Den Key in MapTiler auf deine Domain
beschränken.

Weitere URL-Parameter: `/?kiosk` zeigt nur Karte und Statuszeile und lädt alle 10 Minuten
neu (z. B. für einen Smart-Bilderrahmen).

### Statische Raster neu erzeugen (optional)

`backend/data/*.json` liegen fertig im Repo. Nur bei neuen Rohdaten (WRI-Aqueduct-GDB bzw.
GRACE-NetCDF nach `datasets/` legen — nicht versioniert) einmalig lokal ausführen:

```bash
pip install -r scripts/requirements.txt     # geopandas, h5py, … — nie auf dem Server nötig
python scripts/build_water_stress_grid.py
python scripts/build_groundwater_grid.py
```

## Deployment

Produktiv läuft die App mit Gunicorn hinter einem Reverse-Proxy (Apache/nginx).
**Wichtig: Gunicorn muss mit einem einzigen Worker-Prozess laufen**, z. B.

```bash
gunicorn --workers 1 --threads 4 --bind 127.0.0.1:5000 app:app
```

Zellen-Cache und SSE-Abonnenten liegen im Prozessspeicher. Bei mehreren Worker-*Prozessen*
sieht die Status-Konsole keine Ereignisse mehr und der Cache wird pro Prozess neu befüllt.
Threads teilen sich den Speicher und sind unproblematisch. (Gunicorn läuft nicht unter
Windows — dort `python app.py`.) Für mehrere Prozesse müsste der Cache auf SQLite/Redis
umziehen.

## Bekannte Einschränkungen

- Pro Zelle wird nur der Zellmittelpunkt abgefragt, keine echte Flächen-Aggregation.
- Es ist immer genau eine Ebene aktiv, kein Überlagern mehrerer Ebenen.
- **Wasserstress**: ungewichteter Mittelwert aller Aqueduct-Basins, die eine Zelle
  berühren (Vereinfachung, in `provenance.processing` ausgewiesen).
- **GRACE**: nur der jeweils neueste Monat, keine Zeitreihe.
- **Verdunstung (NASA POWER)**: ca. 10 Tage Verzug; Werte aus dem nativen ~0,5°-Raster
  auf 1°-Zellen gemittelt.
- Open-Meteo antwortet bei sehr schnellem Durchspielen der Zeitachse mit `429`; die App
  zeigt betroffene Zellen dann grau statt falscher Werte.
- Der PNG-Export braucht `preserveDrawingBuffer: true` (etwas GPU-Kosten) und enthält nur
  Karte und Statistik-Werte, keine Bedienelemente.

## Roadmap

Offene Punkte stehen in [todo.md](todo.md): Gewässerflächen (OpenStreetMap), ERA5-
Bodenfeuchte/Abfluss (Copernicus CDS), GRACE-Zeitreihe, Rate-Limit-Backoff. Langfristig
denkbar: Gletscher und Schnee, Stauseen, virtuelles Wasser im Welthandel, 3D-Globus.

Beiträge, Ideen und Fehlerberichte sind als Issues willkommen.
