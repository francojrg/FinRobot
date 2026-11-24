# Franci's FINRobot – Kurzanleitung

Ein System aus Research-Agenten für ein Aktienportfolio: Annual Reports zum 10-K, Earnings Reviews je Quartal,
News Digest, Portfolio Review und ein Weekly Brief mit den nächsten Schritten. Alles läuft lokal auf deinem Rechner.
Nur für akademische Zwecke, keine Anlageberatung.

## Einmalig einrichten (ca. 10 Minuten)
1. **Python 3.11** installieren (python.org, Windows-Installer 64-bit, „Add python.exe to PATH“ anhaken).
2. Im Ordner `ai_in_finance` **`setup.bat`** doppelklicken. Es legt eine Python-Umgebung an und installiert alle Pakete.
3. **`Start FINRobot.bat`** doppelklicken. Die App öffnet sich im Browser.
4. Unter **⚙ Einstellungen** eintragen:
   - **OpenRouter-Schlüssel** (Pflicht, openrouter.ai → Keys; dort am besten ein Ausgabelimit von z. B. 5 USD setzen)
   - **SEC User-Agent**: Name und E-Mail (Pflicht für die SEC-Datenbank EDGAR)
   - **Finnhub** (kostenlos, für News) und **sec-api.io** (kostenloses Kontingent, für die 10-K-Texte)
   Die Schlüssel bleiben lokal auf deinem Rechner.

## Analyse starten
1. **▶ Analyse starten** → CSV hochladen. Formate:
   - Gewichte: `ticker,weight` (z. B. `GOOG,14`)
   - Stückzahlen: `ticker,shares`
   - Exporte von Trade Republic, Scalable Capital oder Smartbroker (mit Käufen und Verkäufen → echte Performance)
2. **Plan erstellen**: zeigt, welche Agenten für welche Titel laufen, mit geschätzter Dauer und Kosten.
   Annual Report und Earnings Review gibt es nur für US-Unternehmen mit Form 10-K.
3. **Analyse starten**. Ein Erstlauf für 10 Titel dauert etwa eine Stunde und kostet grob 1–1,50 USD.
   Der Lauf geht im Hintergrund weiter; der Fortschritt steht auf der Startseite.

## Ergebnisse
- **🏠 Home**: Weekly Brief – wo eine Entscheidung nötig ist, was man lesen sollte, Termine und aktuelle News.
- **📊 Portfolio**: Kennzahlen, Performance gegen MSCI ACWI, Struktur, Risiko, Optimierung, Research-Sicht je Position.
- **🔎 Research**: Annual Reports und Earnings Reviews; jede Zahl ist grün (in den Quellen gefunden) oder rot markiert.
- **📰 News**: Storylines und News Digest. **🧾 Protokoll**: Läufe, Kosten, Evaluation.

Erneuter Start erstellt nur, was fällig ist (neuer 10-K, neue Quartalszahlen, Wochen-News) – das geht dann schnell.
Das Investment Committee ist standardmäßig aus (langsam, teuer, selten ein Ergebnis) und lässt sich beim Start zuschalten.
