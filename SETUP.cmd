@echo off
cd /d "%~dp0"
python setup_independent.py
if errorlevel 1 pause
