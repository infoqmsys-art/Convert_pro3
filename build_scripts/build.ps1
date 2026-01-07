# Build script for Convert Pro 3
# 버전 정보를 자동으로 반영하여 빌드

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Convert Pro 3 빌드 시작" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 버전 정보 읽기
Write-Host "📌 버전 정보 확인 중..." -ForegroundColor Yellow
$versionContent = Get-Content "..\version.py" -Raw

# VERSION_MAJOR, VERSION_MINOR 추출
if ($versionContent -match 'VERSION_MAJOR = (\d+)' -and $versionContent -match 'VERSION_MINOR = (\d+)') {
    $major = $matches[1]
    $versionContent -match 'VERSION_MINOR = (\d+)' | Out-Null
    $minor = $matches[1]
    $version = "v$major.$minor"
    Write-Host "   현재 버전: $version" -ForegroundColor Green
} else {
    Write-Host "❌ 버전 정보를 찾을 수 없습니다" -ForegroundColor Red
    exit 1
}

# 가상환경 활성화
if (-not (Test-Path "..\.venv\Scripts\Activate.ps1")) {
    Write-Host "❌ 가상환경이 없습니다" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "1️⃣ 가상환경 활성화..." -ForegroundColor Yellow
& ..\\.venv\\Scripts\\Activate.ps1

Write-Host "2️⃣ 기존 빌드 정리..." -ForegroundColor Yellow
if (Test-Path "..\build") { Remove-Item "..\build" -Recurse -Force }
if (Test-Path "..\dist") { Remove-Item "..\dist" -Recurse -Force }

Write-Host "3️⃣ PyInstaller 빌드 중..." -ForegroundColor Yellow
Write-Host "   출력 파일: ConvertPro3_$version.exe" -ForegroundColor Cyan
# 루트에서 실행 (spec 파일도 루트에 있음)
Set-Location ..
pyinstaller ConvertPro3_v1.0.spec --clean
Set-Location build_scripts

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ 빌드 완료!" -ForegroundColor Green
    Write-Host ""
    Write-Host "생성된 파일:" -ForegroundColor Cyan
    
    $exeFile = "..\dist\ConvertPro3_$version.exe"
    if (Test-Path $exeFile) {
        $size = (Get-Item $exeFile).Length / 1MB
        Write-Host "  - $exeFile" -ForegroundColor White
        Write-Host "  - 크기: $($size.ToString('0.00')) MB" -ForegroundColor White
    } else {
        Write-Host "  ⚠️  예상된 파일을 찾을 수 없습니다: $exeFile" -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "다음 단계:" -ForegroundColor Yellow
    Write-Host "  1. dist\ConvertPro3_$version.exe 테스트" -ForegroundColor White
    Write-Host "  2. 서버에 업로드" -ForegroundColor White
    Write-Host "  3. version.json 업데이트" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "❌ 빌드 실패" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
