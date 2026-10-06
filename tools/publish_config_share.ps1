# 큐엠메인서버3에서 관리자 PowerShell 로 한 번 실행한다.
# C:\Projects\Convert_pro3 를 공유 이름 ConvertPro3 로 연다.
# 개발 PC는 \\<이 컴퓨터>\ConvertPro3\config.json 으로 같은 파일을 연다.
#
#   cd C:\Projects\Convert_pro3
#   powershell -ExecutionPolicy Bypass -File tools\publish_config_share.ps1

param(
    [string]$Folder = "C:\Projects\Convert_pro3",
    [string]$ShareName = "ConvertPro3",
    [string]$Account = ""
)

$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "관리자 권한이 필요합니다."
    Write-Host "시작 메뉴에서 Windows PowerShell 을 마우스 오른쪽 클릭 → 관리자로 실행 후 다시 실행하세요."
    exit 1
}

if (-not (Test-Path -LiteralPath $Folder)) {
    Write-Host "폴더가 없습니다: $Folder"
    exit 1
}

if (-not $Account) {
    $Account = "$env:COMPUTERNAME\$env:USERNAME"
}

$existing = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Path -ne $Folder) {
        Write-Host "공유 이름 $ShareName 이 다른 폴더를 가리킵니다: $($existing.Path)"
        exit 1
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
        Write-Host "방화벽 규칙은 자동으로 켜지지 않았습니다. 파일 및 프린터 공유를 허용하세요."
    }
}

$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    ForEach-Object { $_.IPAddress }

Write-Host ""
Write-Host "컴퓨터 이름: $env:COMPUTERNAME"
Write-Host "IP: $($ips -join ', ')"
Write-Host "공유 계정: $Account"
Write-Host ""
Write-Host "개발 PC 에서 쓸 경로:"
Write-Host "  \\$env:COMPUTERNAME\$ShareName\config.json"
foreach ($ip in $ips) {
    Write-Host "  \\$ip\$ShareName\config.json"
}
Write-Host ""
Write-Host "서버의 Convert Pro가 켜져 있으면 저장 때 이 파일을 통째로 다시 씁니다."
Write-Host "개발 PC 에서 고친 뒤에는 서버 Convert Pro를 껐다 켜세요."
