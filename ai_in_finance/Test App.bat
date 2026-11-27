@echo off
REM Seitentest: oeffnet alle Seiten der App und meldet Abstuerze. Kein LLM, keine Kosten.
cd /d "%~dp0\.."
call .venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python ai_in_finance\scripts\test_app.py %* > ai_in_finance\eval\test_app.txt 2>&1
type ai_in_finance\eval\test_app.txt
echo.
pause
