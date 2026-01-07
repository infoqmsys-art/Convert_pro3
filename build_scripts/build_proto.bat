@echo off
echo ======================================
echo Convert Pro 3 v1.0 - Build Script
echo ======================================

REM 프로젝트 루트로 이동
cd /d C:\projects\Convert_pro3

REM 이전 빌드 정리
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist ConvertPro3_v1.0.spec del ConvertPro3_v1.0.spec

echo.
echo [1/3] PyInstaller build start...
echo.

REM 콘솔 ON (v1.0 확정)
pyinstaller ^
  --clean ^
  --onefile ^
  --name ConvertPro3_v1.0 ^
  Convert_pro3.py

echo.
echo [2/3] Build finished.
echo.

REM 결과 확인
if exist dist\ConvertPro3_v1.0.exe (
    echo [SUCCESS] dist\ConvertPro3_v1.0.exe 생성 완료
) else (
    echo [ERROR] exe 생성 실패
)

echo.
echo [3/3] Press any key to exit...
pause > nul

