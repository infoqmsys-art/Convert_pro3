@echo off
setlocal

echo.
echo ============================================
echo   Web patch: copy monitoring folder
echo ============================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

pushd "%PROJECT_ROOT%" || (
  echo ERROR: Cannot cd to project root
  pause
  exit /b 1
)

goto main_entry

REM Subroutine copy_monitoring_to target_dir
:copy_monitoring_to
set "TGT=%~1"
if "%TGT%"=="" exit /b 1
echo   TARGET: "%TGT%"
if not exist "%TGT%\monitoring" mkdir "%TGT%\monitoring"
if not exist "%TGT%\monitoring\templates" mkdir "%TGT%\monitoring\templates"
for %%Q in (server.py data_cache.py __init__.py) do (
  if exist "%PROJECT_ROOT%\monitoring\%%Q" (
    copy /Y "%PROJECT_ROOT%\monitoring\%%Q" "%TGT%\monitoring\%%Q" >nul 2>nul
    echo     %%Q OK
  )
)
xcopy /E /Y /Q "%PROJECT_ROOT%\monitoring\templates\*" "%TGT%\monitoring\templates\" >nul 2>nul
echo     templates OK
exit /b 0

:main_entry

git --version >nul 2>nul
if errorlevel 1 (
  echo ERROR: git not found. Install from https://git-scm.com/download/win
  pause
  popd
  exit /b 1
)

set "BRANCH=main"
for /f "usebackq delims=" %%B in (`git branch --show-current 2^>nul`) do set "BRANCH=%%B"
if "%BRANCH%"=="" set "BRANCH=main"

echo Branch: %BRANCH%
echo.

echo [1/3] git pull...
git pull origin "%BRANCH%"
if errorlevel 1 (
  echo ERROR: git pull failed
  pause
  popd
  exit /b 1
)
echo.

echo [2/3] Copy monitoring to project root and dist...
call :copy_monitoring_to "%CD%"
if exist "%CD%\dist\" (
  echo EXTRA: copy to dist\
  call :copy_monitoring_to "%CD%\dist"
) else (
  echo INFO: dist\ not found - only project root updated
)
echo.

echo [3/3] Done.
echo Tip: Reload browser Ctrl+F5. Web Restart if server.py changed.
echo.
pause
popd
exit /b 0
