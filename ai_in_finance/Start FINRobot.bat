@echo off
REM Startet die App im Browser
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo Bitte zuerst setup.bat ausfuehren.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -c "import streamlit" 2>nul || python -m pip install streamlit
REM Streamlit-Begruessung (E-Mail-Abfrage) beim ersten Start ueberspringen
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  mkdir "%USERPROFILE%\.streamlit" 2>nul
  echo [general]> "%USERPROFILE%\.streamlit\credentials.toml"
  echo email = "">> "%USERPROFILE%\.streamlit\credentials.toml"
)
python -m streamlit run ai_in_finance\app\app.py --browser.gatherUsageStats false
pause
