# TODO — Wasser-Ressourcen-App

Stand: App ist live auf [wasser.maazi.de](https://wasser.maazi.de). Architektur,
Setup und Einschränkungen stehen in der [README.md](README.md).

## Gefundener Bug in Produktion — Status-Konsole aktualisiert sich nicht

Beim echten Test auf wasser.maazi.de (Ortssuche "Paris"): Karte/Ebene aktualisieren
sich korrekt, die Status-Konsole unten bleibt aber unverändert stehen.

**Diagnose**: `backend/app.py` hält den Rasterzellen-Cache UND die SSE-Abonnenten-Liste
(`_subscribers`) als einfache Python-Variablen im Prozessspeicher. Läuft Gunicorn mit
mehr als einem Worker-**Prozess**, landet die offene SSE-Verbindung eines Nutzers in
Prozess A, während ein API-Call kurz danach von Prozess B beantwortet wird — dessen
`broadcast()` erreicht nur Prozess B's eigene, leere `_subscribers`-Liste, nie den
Client in Prozess A. Aus demselben Grund würde vermutlich auch der Cache pro
Nutzer/Prozess unterschiedlich befüllt sein (schwerer zu bemerken als die Konsole, aber
derselbe Fehler).

- [x] Code-seitig abgesichert: SSE-Response schickt jetzt sofort ein erstes Byte
      (gegen Reverse-Proxy-Pufferung) und `Cache-Control: no-cache` /
      `X-Accel-Buffering: no` Header.
- [ ] **Auf dem VPS/in der Gunicorn-Konfiguration prüfen und ggf. korrigieren**:
      Läuft Gunicorn mit `--workers` > 1? Falls ja, auf `--workers 1 --threads 4` (oder
      ähnlich) umstellen — ein Prozess mit mehreren Threads teilt sich denselben Speicher,
      das behebt sowohl die Konsole als auch die Cache-Konsistenz in einem Schritt. Das ist
      der eigentliche Fix, die Header oben sind nur zusätzliche Absicherung.
- [ ] Nach der Umstellung erneut testen: Ort suchen, prüfen ob die Statuskonsole neue
      Zeilen zeigt.
- Konnte lokal nicht mit Gunicorn nachgestellt werden — Gunicorn läuft nicht unter
  Windows (kein `fcntl`-Modul). Diagnose beruht auf Code-Analyse, nicht auf einem
  lokalen Reproduktionstest.

## UI-Layout-Überarbeitung (nach echtem Test auf PC + Mobile)

Alles unten umgesetzt und lokal getestet.

- [x] Titel oben-links "💧 Ressource Wasser | maazi.de", verlinkt auf wasser.maazi.de,
      bei Hover eine Info-Kachel (~2/3 Bildschirmgröße) zum Thema, verschwindet bei Klick
      irgendwo auf der Seite.
- [x] Theme-Toggle aus der Zeitachse raus, jetzt eigene MapLibre-Control direkt unter
      Zoom/Kompass oben rechts, nur Icon + Hovertext.
- [x] Suchleiste unten links, kompakter (nur noch Suche + GPS; Datum/Zeitregler zur
      Zeitachse verschoben).
- [x] Zeitachse unten Mitte (jetzt inkl. Datumsfeld — konzeptionell alles "Wann"
      an einem Ort).
- [x] Statistik-, Ebenen- und Status-Konsole-Panel unten rechts gestapelt
      (Statistik oben, Ebenen darunter, Konsole unten).
- [x] Status-Konsole mit der Maus in Breite/Höhe vergrößerbar (`resize: both`).
- [x] Mobile: Suchleiste und Ebenen-Panel auf- und zuklappbar (Startzustand richtet
      sich einmalig beim Laden nach der Viewport-Breite).
- **Unterwegs gefunden und mitbehoben**: `#search-controls`/`#layers-list` blieben
  trotz `hidden`-Attribut sichtbar, weil ihre eigene `display:flex`-Regel das
  (nicht `!important`) UA-Default für `[hidden]` überstimmt hat — globale
  `[hidden]{display:none!important}`-Regel ergänzt. Und: `.panel` setzt
  `position:absolute` unconditional; als Flex-Kinder von `#bottom-bar` wurden
  Suchleiste/Zeitachse dadurch von der Flexbox komplett ignoriert (Spec:
  absolut positionierte Kinder nehmen nicht an Flex-Layout teil) — Suchleiste,
  Zeitachse und Statistik-Stapel liegen jetzt in einem gemeinsamen
  `#bottom-bar`-Flex-Container statt unabhängig positioniert zu sein, das
  verhindert auch Überlappungen bei mittleren Fensterbreiten.
- Automatisiertes Ziehen am nativen Resize-Griff der Konsole ließ sich im
  Test-Tool nicht zuverlässig auslösen (`resize:both` ist aber korrekt gesetzt,
  Standard-Browserverhalten) — mit echter Maus bitte einmal gegenprüfen.

## Später / bei Bedarf

- [ ] Gewässerflächen (OSM, DE+FR) — zurückgestellt, weil die öffentliche
      Overpass-API beim letzten Versuch überlastet war ("server too busy").
      Später erneut versuchen, oder auf Geofabrik-Länderextrakte ausweichen
      (~4,5–4,7 GB pro Land).
- [ ] CDS/ERA5 (Bodenfeuchte/Abfluss) — architektonisch anders (asynchrone
      Job-Queue statt Live-Request), eigenes Konzept nötig, noch nicht begonnen.
- [ ] GRACE-Zeitreihe: aktuell nur der neueste Monat, nicht die vollen 259
      verfügbaren Monate seit 2002.
- [ ] Rate-Limit/Retry-Backoff für Open-Meteo-Archiv-API, falls das schnelle
      Durchspielen der Zeitachse im echten Betrieb häufiger an ein 429 stößt.
