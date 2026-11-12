@echo off
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -m pip install -q -r requirements.txt
%PY% run_stick_citizen.py
if errorlevel 1 pause
