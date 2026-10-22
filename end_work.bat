@echo off
rem End-of-work button. Double-click to stop today's automatic collection.
setlocal
cd /d "%~dp0"

rem Use the project venv when available, otherwise fall back to PATH python.
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" end_work.py %*
set "EXITCODE=%ERRORLEVEL%"

rem Keep the window open so the result stays readable on double-click.
echo.
pause
exit /b %EXITCODE%
