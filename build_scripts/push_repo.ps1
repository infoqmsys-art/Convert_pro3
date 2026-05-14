# Git add / commit / push for Convert_pro repo (repo root = parent of build_scripts)
$ErrorActionPreference = "Stop"
try {
    if ($env:OS -eq 'Windows_NT') {
        & chcp.com 65001 2>$null | Out-Null
        try {
            [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
            $OutputEncoding = [Console]::OutputEncoding
        } catch { }
    }
} catch { }

$Root = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Push-Location $Root

try {
    $null = git rev-parse --is-inside-work-tree 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: not a git repository."
        exit 1
    }

    $branch = git branch --show-current 2>$null
    if (-not [string]::IsNullOrWhiteSpace($branch)) { $branch = $branch.TrimEnd() }
    else { $branch = "main" }

    Write-Host ""
    Write-Host "Repo: $Root"
    Write-Host "Branch: $branch"
    Write-Host ""

    $IndexPath = Join-Path $Root "monitoring\templates\index.html"

    function Get-WebVersionCommitLine {
        if (-not (Test-Path -LiteralPath $IndexPath)) { return $null }
        $line = Get-Content -LiteralPath $IndexPath -Encoding UTF8 |
            Where-Object { $_ -match '^\s+v\d+\.\d+\.\d+\s+\([^)]+\)\s+' } |
            Select-Object -First 1
        if (-not $line) { return $null }
        return $line.Trim()
    }

    $commitMsgFromArgs = ""
    $argsRemain = @($args | ForEach-Object { $_ })
    if ($argsRemain.Count -gt 0 -and ($argsRemain[0] -notmatch '^--')) {
        $commitMsgFromArgs = ($argsRemain -join " ").Trim()
    }

    function Git-CommitFile {
        param([string]$Utf8NoBomPath)
        git commit -F $Utf8NoBomPath
        if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
    }

    if ($commitMsgFromArgs -ne "") {
        git add -A
        git diff --cached --quiet 2>$null
        $hasStaged = $LASTEXITCODE -ne 0
        if ($hasStaged) {
            git commit -m $commitMsgFromArgs
            if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
            Write-Host "--- committed ---"
        } else {
            Write-Host "INFO: nothing to commit (working tree clean)."
        }
    } else {
        Write-Host "--- git status (short) ---"
        git status --short
        Write-Host "--------------------------"

        Write-Host "--- WEB_VERSION auto candidate (first history line in index.html) ---"
        $candidate = Get-WebVersionCommitLine
        if (-not $candidate) {
            Write-Host "(could not find WEB_VERSION history line)"
        } else {
            Write-Host $candidate
        }
        Write-Host "-----------------------------------------------------------------------------"
        Write-Host "[1]+Enter : use WEB_VERSION line above as commit message | other : type your message"
        $choice = Read-Host "?"

        if ([string]::IsNullOrWhiteSpace($choice)) {
            Write-Host "Canceled."
            exit 1
        }

        git add -A
        git diff --cached --quiet 2>$null
        $hasStaged = $LASTEXITCODE -ne 0

        if (-not $hasStaged) {
            Write-Host "INFO: nothing to commit (working tree clean)."
        } elseif ($choice -eq "1") {
            $line = Get-WebVersionCommitLine
            if (-not $line) { throw "WEB_VERSION line missing in index.html" }
            $tmp = Join-Path $env:TEMP "cp_gitmsg_utf8.tmp"
            $enc = New-Object System.Text.UTF8Encoding $false
            [System.IO.File]::WriteAllText($tmp, $line, $enc)
            try {
                Git-CommitFile -Utf8NoBomPath $tmp
                Write-Host "--- committed ---"
            } finally {
                Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
            }
        } else {
            git commit -m $choice
            if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
            Write-Host "--- committed ---"
        }
    }

    Write-Host ""
    Write-Host "--- git push origin $branch ..."
    git push origin $branch
    if ($LASTEXITCODE -ne 0) { throw "git push failed" }

    Write-Host "OK - push finished."
    exit 0
} catch {
    Write-Host $_
    exit 1
} finally {
    Pop-Location
}
