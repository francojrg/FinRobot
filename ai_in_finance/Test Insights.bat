@echo off
REM Testet die Insights-Watchlist an echten Seiten (Banken-Research, YouTube, RSS). Kein LLM, keine Kosten.
cd /d "%~dp0\.."
call .venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python ai_in_finance\scripts\test_insights.py
echo.
pause
