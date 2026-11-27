@echo off
REM Prueft, ob BLUMBOERG die Abschnitte von 10-K und 10-Q selbst aus SEC EDGAR lesen kann (Ersatz fuer sec-api). Kein LLM, keine Kosten.
cd /d "%~dp0\.."
call .venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python ai_in_finance\scripts\check_edgar_sections.py MNST KO CSCO SPGI AMZN
echo.
pause
