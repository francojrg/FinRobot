@echo off
REM Vergleicht die eigene Zerlegung von 10-K/10-Q mit den frueheren sec-api-Abschnitten. Kein LLM, keine Kosten, 2-4 Minuten.
cd /d "%~dp0\.."
call .venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python ai_in_finance\scripts\compare_sec_api.py
echo.
pause
