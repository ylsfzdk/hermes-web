@echo off
chcp 65001 >nul
title Hermes Web Launcher
setlocal EnableDelayedExpansion

set "PIDFILE=%TEMP%\hermes-web-gw.pid"
set "OWNED=0"

echo ==========================================
echo   Hermes Web - Launcher
echo ==========================================
echo.

set PYTHONUTF8=1

where hermes >nul 2>nul
if errorlevel 1 (
  echo [ERROR] hermes not found in PATH.
  echo         Install it first:  pip install hermes-agent
  goto :end
)

echo [1/3] Checking Hermes Gateway on port 8642...
netstat -an | findstr ":8642" | findstr "LISTENING" >nul
if not errorlevel 1 goto :reuse

echo       Not running. Starting hidden gateway...
powershell -NoProfile -Command "$p=Start-Process -FilePath 'hermes' -ArgumentList 'gateway' -WindowStyle Hidden -PassThru; Set-Content -Path '%PIDFILE%' -Value $p.Id" >nul 2>nul
set "OWNED=1"

echo       Waiting for gateway to become ready...
set /a tries=0
:wait
timeout /t 1 /nobreak >nul 2>nul || ping -n 2 127.0.0.1 >nul
set /a tries+=1
netstat -an | findstr ":8642" | findstr "LISTENING" >nul
if not errorlevel 1 goto :ready
if !tries! lss 30 goto :wait
echo [WARN] Gateway did not open port 8642 within 30s.
echo        Run "hermes gateway" manually to see the error.
goto :ready

:reuse
echo [INFO] Gateway already running - reusing it.
echo        It will NOT be stopped when this window closes.
goto :ready

:ready
echo.
echo [2/3] Starting web server on port 3000...
echo.
echo ==========================================
echo   Ready.
echo.

set "LANIP="
for /f "delims=" %%i in ('powershell -NoProfile -Command "$s=New-Object System.Net.Sockets.UdpClient; $s.Connect([Net.IPAddress]([byte[]](8,8,8,8)),53); $s.Client.LocalEndPoint.Address.ToString(); $s.Close()"') do set "LANIP=%%i"

if not defined LANIP goto :noip
if "!LANIP!"=="0.0.0.0" goto :noip
if "!LANIP!"=="127.0.0.1" goto :noip
echo   Phone access: http://!LANIP!:3000
goto :afterip

:noip
echo   Phone access: not detected - connect to WiFi first

:afterip
echo   Local access: http://localhost:3000
echo.
echo   Press Ctrl+C to stop the web server.
echo ==========================================
echo.

python backend\server.py 3000

:end
echo.
if "%OWNED%"=="1" (
  echo [3/3] Stopping the gateway we started...
  if exist "%PIDFILE%" (
    set /p GWPID=<"%PIDFILE%"
    taskkill /PID !GWPID! /T /F >nul 2>nul
    del "%PIDFILE%" >nul 2>nul
    echo       Gateway stopped.
  )
) else (
  echo   Gateway left running ^(it was already up before launch^).
)
echo.
pause