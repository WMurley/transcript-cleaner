@echo off
rem Same as the .vbs launcher, but keeps a window open so you can see errors.
"%~dp0..\.venv\Scripts\python.exe" "%~dp0app.py"
pause
