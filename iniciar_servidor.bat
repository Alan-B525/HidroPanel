@echo off
title Servidor HidroPanel 2.0
chcp 65001 >nul
cd /d "%~dp0"

echo ======================================================================
echo            INICIANDO SERVIDOR HIDROPANEL 2.0 (LAN)
echo ======================================================================

if exist ".venv\Scripts\python.exe" (
    set "PY_BIN=.venv\Scripts\python.exe"
) else (
    set "PY_BIN=python"
)

"%PY_BIN%" app.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] El servidor finalizo con codigo de error %ERRORLEVEL%.
    pause
)
