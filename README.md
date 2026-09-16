# 💧 Wasser-Ressourcen-App

**[👉 wasser.maazi.de](https://wasser.maazi.de) — live ausprobieren**

Eine interaktive Weltkarte, die zeigt, wie es um Wasser an einem beliebigen Ort der
Erde steht: aktuelles Wetter, Verdunstung, Veränderung des Landwasserspeichers und
Wasserstress — für die Region, die du dir gerade ansiehst.

Dieses Projekt ist noch in aktiver Entwicklung. Diese README ist deshalb bewusst ein
Handbuch für Besucher der Live-Seite, keine vollständige technische Dokumentation —
vieles wird sich noch ändern. Wer tiefer einsteigen will, findet die technischen
Details in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) und die komplette
Projekt-Vision in [wasser-app-plan.md](wasser-app-plan.md).

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

## Status

Das Projekt befindet sich zwischen Grundgerüst und weiterem Ausbau — einzelne
Datenebenen und Funktionen kommen noch dazu. Feedback und Fragen sind willkommen, über
Issues in diesem Repository.
