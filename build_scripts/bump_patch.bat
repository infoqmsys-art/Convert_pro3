@echo off
chcp 65001 > nul
echo ========================================
echo 패치 버전 증가 (버그 수정)
echo ========================================
echo.

python bump_version.py patch

echo.
echo version.json을 열어서 release_notes를 수정하세요!
echo.
pause
