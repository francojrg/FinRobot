@echo off
REM Prueft den Portfolio-Upload mit typischen CSV-Varianten. Kein LLM, keine Kosten.
cd /d "%~dp0\.."
call .venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python ai_in_finance\scripts\test_upload.py > ai_in_finance\eval\test_upload.txt 2>&1
type ai_in_finance\eval\test_upload.txt
echo.
pause
