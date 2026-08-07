@echo off
echo Content-Type: text/plain
echo.

:: POST 데이터를 환경 변수에 저장하여 출력
set /p data=<nul
echo Received data: %data%
