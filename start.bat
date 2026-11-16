@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist config.json copy /y config.example.json config.json >nul
python server.py
if errorlevel 1 pause
