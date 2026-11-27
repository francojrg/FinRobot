@echo off
REM Prueft ASML, TSM (20-F) und MA (10-K): Jahresbericht, Abschnitte, Quartalsmeldungen, Kennzahlen. Kein LLM, keine Kosten.
cd /d "%~dp0\.."
call .venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python ai_in_finance\scripts\check_foreign_filer.py ASML TSM MA > ai_in_finance\eval\check_foreign_filer.txt 2>&1
type ai_in_finance\eval\check_foreign_filer.txt
echo.
echo Fertig. Ergebnis steht in ai_in_finance\eval\check_foreign_filer.txt
pause
