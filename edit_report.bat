@echo off
rem Work record editor. Double-click to run; it asks for the target date.
setlocal
cd /d "%~dp0"

rem Use the project venv when available, otherwise fall back to PATH python.
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" edit_report.py %*
set "EXITCODE=%ERRORLEVEL%"

rem Keep the window open so the result stays readable on double-click.
echo.
pause
exit /b %EXITCODE%
