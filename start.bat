@echo off
chcp 65001 >nul
title Hermes Web Launcher
setlocal EnableDelayedExpansion

rem Unbuffered output so gateway-start progress shows up in this window.
rem Keep this whole file ASCII: chcp runs after cmd has already tokenized the
rem batch text, so non-ASCII comments get mangled and executed as commands.
set PYTHONUNBUFFERED=1
set PYTHONDONTWRITEBYTECODE=1

echo ==========================================
echo   Hermes Web - Launcher
echo ==========================================
echo.

set PYTHONUTF8=1

rem Locate the source-tree venv python, then run the backend.
rem This launcher only starts the web server: the Hermes gateway on 8642 must
rem already be running (start it yourself). Without it /api/* answers 502.

set "HERMES_SRC=%~dp0..\hermes-agent-0.23.1"
for %%i in ("%HERMES_SRC%") do set "HERMES_SRC=%%~fi"
set "HERMES_PY=%HERMES_SRC%\.venv\Scripts\python.exe"
set "HERMES_HOME=%HERMES_SRC%\.hermes-home"
set "PYTHONPATH=%HERMES_SRC%"

if not exist "%HERMES_PY%" (
  echo [ERROR] Source install not found: "%HERMES_SRC%"
  echo         Expected python at: "%HERMES_PY%"
  goto :end
)

echo Web server: http://localhost:3000
echo Gateway on 8642 is NOT started here - run it yourself first.
echo ==========================================
echo.

"%HERMES_PY%" backend\server.py 3000

:end
echo.
pause