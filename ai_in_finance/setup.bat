@echo off
REM Einmalige Einrichtung: Python-Umgebung, Pakete, Konfiguration
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo Lege Python-Umgebung an ...
  py -3.11 -m venv .venv
  if errorlevel 1 (
    echo Python 3.11 wurde nicht gefunden. Bitte installieren: https://www.python.org/downloads/release/python-3119/
    echo Beim Installieren "Add python.exe to PATH" anhaken, danach setup.bat erneut starten.
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r ai_in_finance\requirements-app.txt
if errorlevel 1 (
  echo Installation fehlgeschlagen - Ausgabe oben pruefen.
  pause
  exit /b 1
)
python -c "import site,os;p=[s for s in site.getsitepackages() if s.lower().endswith('site-packages')][0];open(os.path.join(p,'finrobot_local.pth'),'w').write(os.path.abspath('finrobot_autogen'))"
if not exist finrobot_autogen\config_api_keys copy finrobot_autogen\config_api_keys_sample finrobot_autogen\config_api_keys >nul
if not exist finrobot_autogen\OAI_CONFIG_LIST echo [] > finrobot_autogen\OAI_CONFIG_LIST
echo.
echo Fertig. Jetzt die Start-Datei von BLUMBOERG doppelklicken und unter Einstellungen die Schluessel eintragen.
pause
