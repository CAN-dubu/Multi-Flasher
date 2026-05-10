@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python multi_flash/main.py
) else (
    py -3 multi_flash/main.py
)
if errorlevel 1 pause
