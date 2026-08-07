@echo off
cd /d "%~dp0\..\.."
python tools\release\make.py %*
pause
