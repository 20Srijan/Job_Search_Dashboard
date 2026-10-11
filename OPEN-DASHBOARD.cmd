@echo off
title Job Search Dashboard - keep this window open
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run SETUP.cmd once first.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -u launch_local.py
if errorlevel 1 pause
