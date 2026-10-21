@echo off
rem Double-click to set up Transcript Cleaner on this computer (about 800 MB, into this folder only).
rem The setup script runs with this window's permission only; nothing system-wide changes.
title Transcript Cleaner setup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\setup-windows.ps1"
