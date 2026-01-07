@echo off
chcp 65001 > nul
echo ========================================
echo 마이너 버전 증가 (새 기능 추가)
echo ========================================
echo.

python bump_version.py minor

echo.
echo version.json을 열어서 release_notes를 수정하세요!
echo.
pause
