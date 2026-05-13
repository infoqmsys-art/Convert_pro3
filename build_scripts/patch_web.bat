@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul

echo.
echo ============================================
echo  큐엠 자동화 관리 프로그램 - 웹 빠른 패치
echo ============================================
echo.

:: 이 스크립트 위치 기준으로 프로젝트 루트 결정
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..

:: 실행 파일(EXE) 위치 — 기본값: 프로젝트 루트
:: 다른 경로라면 아래를 수정하세요
set EXE_DIR=%PROJECT_ROOT%

cd /d "%PROJECT_ROOT%"

:: ── git 설치 확인 ────────────────────────────────
git --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] git 가 설치되어 있지 않습니다.
    echo   설치: https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)

:: ── 현재 브랜치 확인 ─────────────────────────────
for /f "tokens=*" %%b in ('git branch --show-current 2^>nul') do set BRANCH=%%b
echo  브랜치: %BRANCH%
echo.

:: ── git pull ─────────────────────────────────────
echo [1/3] 최신 변경사항 가져오는 중...
git pull origin %BRANCH%
if errorlevel 1 (
    echo.
    echo [ERROR] git pull 실패
    echo  - 인터넷 연결 확인
    echo  - 충돌 파일이 있는지 확인: git status
    echo.
    pause
    exit /b 1
)
echo.

:: ── monitoring 폴더 복사 ─────────────────────────
echo [2/3] monitoring 파일을 프로그램 폴더로 복사 중...
if not exist "%EXE_DIR%\monitoring" mkdir "%EXE_DIR%\monitoring"
if not exist "%EXE_DIR%\monitoring\templates" mkdir "%EXE_DIR%\monitoring\templates"

:: server.py, data_cache.py 복사
for %%f in (server.py data_cache.py __init__.py) do (
    if exist "%PROJECT_ROOT%\monitoring\%%f" (
        copy /Y "%PROJECT_ROOT%\monitoring\%%f" "%EXE_DIR%\monitoring\%%f" > nul
        echo   %%f 복사 완료
    )
)

:: templates 폴더 전체 복사
xcopy /E /Y /Q "%PROJECT_ROOT%\monitoring\templates\*" "%EXE_DIR%\monitoring\templates\" > nul
echo   templates/ 복사 완료
echo.

:: ── 결과 안내 ────────────────────────────────────
echo [3/3] 패치 완료!
echo.
echo  변경 종류별 반영 방법:
echo  ┌─────────────────────────────────────────┐
echo  │ templates/ (HTML 변경)                  │
echo  │   → 브라우저 새로고침만 하면 즉시 반영  │
echo  │                                         │
echo  │ server.py (API 로직 변경)               │
echo  │   → 프로그램 우상단 [웹 재시작] 클릭   │
echo  │     (메인 프로그램 종료 없이 가능)      │
echo  └─────────────────────────────────────────┘
echo.
pause
