@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PS_SCRIPT=%~dp0scripts\start-proxy.ps1"
if not exist "%PS_SCRIPT%" exit /b 1

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
exit /b %ERRORLEVEL%
