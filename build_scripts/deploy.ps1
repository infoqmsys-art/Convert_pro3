# ========================================
# Convert Pro 3 자동 배포 스크립트
# ========================================

param(
    [string]$ReleaseNotes = "버그 수정 및 개선"
)

$ErrorActionPreference = "Stop"

# 환경변수 PATH 새로고침 (gh 명령 인식을 위해)
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# 프로젝트 루트로 이동
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptRoot
Set-Location $projectRoot

# version.py에서 버전 읽기
$versionContent = Get-Content "version.py" -Raw
if ($versionContent -match 'VERSION_MAJOR = (\d+)') { $major = $Matches[1] }
if ($versionContent -match 'VERSION_MINOR = (\d+)') { $minor = $Matches[1] }
if ($versionContent -match 'VERSION_PATCH = (\d+)') { $patch = $Matches[1] }
$version = "$major.$minor.$patch"
$versionTag = "v$version"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Convert Pro 3 자동 배포" -ForegroundColor Cyan
Write-Host "버전: $versionTag" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. exe 파일 확인
$exePath = "dist\ConvertPro3.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "빌드 파일을 찾을 수 없습니다: $exePath" -ForegroundColor Red
    Write-Host "먼저 빌드를 실행하세요: .\build_scripts\build.bat" -ForegroundColor Yellow
    exit 1
}

Write-Host "빌드 파일 확인: $exePath" -ForegroundColor Green

# 2. version.json 생성
$deployPath = "C:\Users\qm202\Desktop\convert-pro3-updates"
$updatesPath = "$deployPath\updates"

if (-not (Test-Path $updatesPath)) {
    New-Item -ItemType Directory -Path $updatesPath -Force | Out-Null
}

$releaseNotesArray = $ReleaseNotes -split '\n' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
$versionJson = @{
    version = $version
    release_date = (Get-Date -Format "yyyy-MM-dd")
    download_url = "https://github.com/infoqmsys-art/Convert_pro3_updates/releases/download/$versionTag/ConvertPro3_v$major.$minor.$patch.exe"
    release_notes = $releaseNotesArray
} | ConvertTo-Json -Depth 10

# UTF-8 without BOM으로 저장
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText("$updatesPath\version.json", $versionJson, $utf8NoBom)
Write-Host "version.json 생성 완료" -ForegroundColor Green

# 3. Git 작업
Write-Host ""
Write-Host "GitHub에 업로드 중..." -ForegroundColor Cyan

Set-Location $deployPath

# Git 상태 확인
$gitStatus = git status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Git 저장소 초기화 중..." -ForegroundColor Yellow
    git init
    git remote add origin https://github.com/infoqmsys-art/Convert_pro3_updates.git
    git branch -M main
}

# 변경사항 추가 및 커밋
git add updates/version.json
git commit -m "Update to $versionTag"

# 원격 저장소와 동기화
Write-Host "원격 저장소와 동기화 중..." -ForegroundColor Yellow
git pull origin main --rebase

# Push 시도
Write-Host ""
Write-Host "GitHub 로그인 필요" -ForegroundColor Yellow
Write-Host "브라우저가 열리면 infoqmsys-art 계정으로 로그인하세요" -ForegroundColor Yellow
Write-Host ""

git push origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "version.json 업로드 완료!" -ForegroundColor Green
    
    # GitHub Release 자동 생성
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "GitHub Release 생성 중..." -ForegroundColor Yellow
    Write-Host ""
    
    # GitHub CLI 인증 확인
    $ghAuth = & gh auth status 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "GitHub CLI 인증이 필요합니다." -ForegroundColor Yellow
        Write-Host "브라우저가 열리면 infoqmsys-art 계정으로 로그인하세요" -ForegroundColor Yellow
        & gh auth login -h github.com -w
    }
    
    # Release 노트 생성
    $releaseNotes = @"
## 변경사항
$($ReleaseNotes -split '\n' | ForEach-Object { "- $_" } | Out-String)

## 다운로드
- [ConvertPro3_v$major.$minor.$patch.exe](https://github.com/infoqmsys-art/Convert_pro3_updates/releases/download/$versionTag/ConvertPro3_v$major.$minor.$patch.exe)
- [update.exe](https://github.com/infoqmsys-art/Convert_pro3_updates/releases/download/$versionTag/update.exe)
"@
    
    # Release 생성 및 파일 업로드
    $updateExePath = Join-Path $projectRoot "dist\update.exe"
    
    # 절대 경로로 변환 (프로젝트 루트에서)
    Push-Location $projectRoot
    $exeFullPath = Resolve-Path $exePath
    $updateExeFullPath = Resolve-Path $updateExePath
    Pop-Location
    
    try {
        Set-Location $deployPath
        & gh release create $versionTag `
            --repo infoqmsys-art/Convert_pro3_updates `
            --title "Convert Pro 3 $versionTag" `
            --notes $releaseNotes `
            "$exeFullPath" `
            "$updateExeFullPath"
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Host "========================================" -ForegroundColor Green
            Write-Host "배포 완료!" -ForegroundColor Green
            Write-Host "========================================" -ForegroundColor Green
            Write-Host ""
            Write-Host "Release URL:" -ForegroundColor White
            Write-Host "https://github.com/infoqmsys-art/Convert_pro3_updates/releases/tag/$versionTag" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "2-3분 후 자동 업데이트 활성화됩니다." -ForegroundColor Yellow
            Write-Host "========================================" -ForegroundColor Cyan
        } else {
            Write-Host ""
            Write-Host "Release 생성 실패" -ForegroundColor Red
            Write-Host "수동으로 생성하세요: https://github.com/infoqmsys-art/Convert_pro3_updates/releases/new" -ForegroundColor Yellow
        }
    } catch {
        Write-Host ""
        Write-Host "Release 생성 중 오류: $_" -ForegroundColor Red
        Write-Host "수동으로 생성하세요: https://github.com/infoqmsys-art/Convert_pro3_updates/releases/new" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "Push 실패" -ForegroundColor Red
    Write-Host "수동으로 GitHub에 업로드하세요" -ForegroundColor Yellow
}

Set-Location $projectRoot
