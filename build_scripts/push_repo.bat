@echo off
setlocal

REM ============================================================
REM  Git push helper (repo root = parent folder of build_scripts)
REM  1) git add -A
REM  2) git commit -m "..."  (skip if nothing to commit)
REM  3) git push origin current-branch
REM
REM  Convert program: git pull via [Web Patch] / manual.
REM  This script: push YOUR local changes UP to GitHub.
REM
REM  Usage:
REM    push_repo.bat One-line commit message
REM    push_repo.bat "Quoted message"
REM    push_repo.bat                           (prompts for message)
REM ============================================================

set "ROOT=%~dp0.."
pushd "%ROOT%" || (
  echo ERROR: cannot cd to %ROOT%
  exit /b 1
)

git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo ERROR: not a git repository.
  popd
  exit /b 1
)

set "BRANCH=main"
for /f "usebackq delims=" %%B in (`git branch --show-current 2^>nul`) do set "BRANCH=%%B"
if "%BRANCH%"=="" set "BRANCH=main"

echo.
echo Repo: %CD%
echo Branch: %BRANCH%
echo.
echo --- git status (short) ---
git status --short
echo --------------------------
echo.

if "%~1"=="" (
  set /p "CMSG=Commit message (blank=cancel): "
  if not defined CMSG (
    echo Canceled.
    popd
    exit /b 1
  )
) else (
  set "CMSG=%*"
)

git add -A

git diff --cached --quiet
if errorlevel 1 (
  git commit -m "%CMSG%"
  if errorlevel 1 (
    echo ERROR: git commit failed
    popd
    exit /b 1
  )
  echo --- committed ---
) else (
  echo INFO: nothing to commit ^(working tree clean^).
)

echo.
echo --- git push origin %BRANCH% ...
git push origin "%BRANCH%"
if errorlevel 1 (
  echo ERROR: git push failed
  popd
  exit /b 1
)

echo OK - push finished.
popd
exit /b 0
