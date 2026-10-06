# 큐엠메인서버3에서 한 번 실행한다.
# C:\Projects\Convert_pro3 를 공유 이름 ConvertPro3 로 연다.
# 개발 PC는 \\<이 컴퓨터>\ConvertPro3\config.json 으로 같은 파일을 연다.
#
#   powershell -ExecutionPolicy Bypass -File tools\publish_config_share.ps1
#   powershell -ExecutionPolicy Bypass -File tools\publish_config_share.ps1 -Account qm202

param(
    [string]$Folder = "C:\Projects\Convert_pro3",
    [string]$ShareName = "ConvertPro3",
    [string]$Account = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Folder)) {
    Write-Error "폴더가 없습니다: $Folder"
}

if (-not $Account) {
    $Account = "$env:USERDOMAIN\$env:USERNAME"
}

$existing = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Path -ne $Folder) {
        Write-Error "공유 이름 $ShareName 이 다른 폴더를 가리킵니다: $($existing.Path)"
    }
    Write-Host "이미 공유 중: $ShareName -> $($existing.Path)"
} else {
    New-SmbShare -Name $ShareName -Path $Folder -Description "Convert Pro config" -FullAccess $Account | Out-Null
    Write-Host "공유 만듦: $ShareName -> $Folder ($Account)"
}

try {
    Enable-NetFirewallRule -DisplayGroup "File and Printer Sharing" -ErrorAction Stop | Out-Null
} catch {
    try {
        Enable-NetFirewallRule -DisplayGroup "파일 및 프린터 공유" -ErrorAction Stop | Out-Null
    } catch {
        Write-Host "방화벽 규칙은 자동으로 켜지지 않았습니다. 파일 및 프린터 공유를 개인/도메인 프로필에서 허용하세요."
    }
}

$unc = "\\$env:COMPUTERNAME\$ShareName\config.json"
Write-Host ""
Write-Host "개발 PC deploy\env.local.bat 에 이 한 줄을 넣습니다."
Write-Host "set CONVERT_PRO_CONFIG=$unc"
Write-Host ""
Write-Host "서버의 Convert Pro가 켜져 있으면 저장 때 이 파일을 통째로 다시 씁니다."
Write-Host "개발 PC에서 고칠 때는 서버 Convert Pro를 닫아 둡니다."
