@echo off
setlocal
title Bookkeeper
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
chcp 65001 >nul

rem Bookkeeper runs on Python. On the first start this downloads "uv", a small tool that installs
rem the right Python and libraries for Bookkeeper (about 150 MB in total). Later starts are quick.
set "TOOLS=%~dp0.tools"
set "UV=%TOOLS%\uv.exe"
if exist "%UV%" goto run

echo.
echo  First start: setting things up. This takes a few minutes, only this once...
echo.
if not exist "%TOOLS%" mkdir "%TOOLS%"
set "ARCH=x86_64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=aarch64"
curl.exe -L --fail --progress-bar -o "%TOOLS%\uv.zip" "https://github.com/astral-sh/uv/releases/latest/download/uv-%ARCH%-pc-windows-msvc.zip"
if errorlevel 1 goto failed
tar.exe -xf "%TOOLS%\uv.zip" -C "%TOOLS%"
del "%TOOLS%\uv.zip"
if not exist "%UV%" goto failed

:run
echo  Starting Bookkeeper. If nothing changes for a long time, press Esc once in this window.
"%UV%" run --frozen --python 3.12 bookkeeper %*
if errorlevel 1 goto crashed
exit /b 0

:crashed
echo.
echo  Bookkeeper stopped with an error. The details are above and in data\logs\bookkeeper.log
pause
exit /b 1

:failed
echo.
echo  Could not download the setup tool. Check your internet connection and run Bookkeeper.bat again.
pause
exit /b 1
