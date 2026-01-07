@echo off
chcp 65001 > nul
echo ========================================
echo 메이저 버전 증가 (대규모 변경)
echo ========================================
echo.

python bump_version.py major

echo.
echo version.json을 열어서 release_notes를 수정하세요!
echo.
pause
