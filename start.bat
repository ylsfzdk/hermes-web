@echo off
chcp 65001 >nul
title Hermes Web 客户端启动器

echo ==========================================
echo   Hermes Web 客户端 - 一键启动
echo ==========================================
echo.

set PYTHONUTF8=1

echo [1/2] 启动 Hermes Gateway...
start "Hermes Gateway" cmd /k "hermes gateway"

timeout /t 5 /nobreak >nul

echo [2/2] 启动网页服务器 (端口 3000)...
echo.
echo ==========================================
echo   启动完成！
echo.
echo   电脑访问: http://localhost:3000
echo   手机访问: http://你的IP:3000
echo.
echo   按 Ctrl+C 停止网页服务器
echo   关闭 "Hermes Gateway" 窗口可停止后端
echo ==========================================
echo.

python -m http.server 3000
pause