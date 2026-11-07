@echo off
cd /d "%~dp0"
if exist ".git" goto pull
echo.
echo  This copy was downloaded as a ZIP file. To update Bookkeeper:
echo    1. Download the newest ZIP from GitHub - Code, then Download ZIP.
echo    2. Unpack it over this folder and allow it to replace the files.
echo  Your library lives in the "data" folder and is kept.
echo.
pause
exit /b 0

:pull
git pull
pause
