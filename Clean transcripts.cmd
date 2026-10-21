@echo off
rem Drag transcripts, or a whole folder, onto this file. Or double-click it
rem to clean whatever is already waiting in the dirty folder.
setlocal
"%~dp0.venv\Scripts\python.exe" "%~dp0clean.py" %*
echo.
pause
