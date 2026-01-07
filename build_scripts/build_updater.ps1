# Build script for update.exe
# update.exe 빌드 스크립트

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Convert Pro 3 - update.exe 빌드" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 가상환경 활성화 확인
if (-not (Test-Path "..\.venv\Scripts\Activate.ps1")) {
    Write-Host "가상환경이 없습니다" -ForegroundColor Red
    exit 1
}

Write-Host "1. 가상환경 활성화..." -ForegroundColor Yellow
& ..\\.venv\\Scripts\\Activate.ps1

Write-Host "2. update.exe 빌드 중..." -ForegroundColor Yellow
Set-Location ..
pyinstaller updater.spec --clean
Set-Location build_scripts

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "빌드 완료!" -ForegroundColor Green
    Write-Host ""
    Write-Host "생성된 파일:" -ForegroundColor Cyan
    Write-Host "  - ..\dist\update.exe" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "빌드 실패" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
