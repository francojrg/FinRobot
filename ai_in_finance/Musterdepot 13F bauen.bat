@echo off
REM Baut das Musterdepot aus den 13F-Meldungen von Valley Forge (SEC EDGAR). Kein LLM, keine Kosten. Dauer 1-3 Minuten.
cd /d "%~dp0\.."
call .venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python ai_in_finance\scripts\build_13f_portfolio.py --cik 1697868 --name sample_transactions_vfc
echo.
echo Fertig. Ausgabe auch in ai_in_finance\eval\build_13f_portfolio.txt
pause
