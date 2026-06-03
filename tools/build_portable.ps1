param(
    [string]$Version = "v1.1.0"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ProjectName = "MediaForge"
$OutputName = "$ProjectName-$Version-portable.zip"
$OutputPath = Join-Path $ProjectRoot "..\$OutputName"
$TempDir = Join-Path $env:TEMP "$ProjectName-portable-build"

Write-Host ""
Write-Host "MediaForge portable build"
Write-Host "Version: $Version"
Write-Host ""

if (Test-Path $TempDir) {
    Remove-Item $TempDir -Recurse -Force
}

New-Item -ItemType Directory -Force $TempDir | Out-Null

$IncludeItems = @(
    "app",
    "downloads",
    ".gitignore",
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "requirements.txt",
    "run.bat",
    "run.py",
    "RUN_SILENT.vbs",
    "SECURITY.md"
)

foreach ($item in $IncludeItems) {
    $source = Join-Path $ProjectRoot $item

    if (Test-Path $source) {
        Copy-Item $source $TempDir -Recurse -Force
        Write-Host "[OK] Added $item"
    }
    else {
        Write-Host "[SKIP] Missing $item"
    }
}

$RemovePatterns = @(
    ".git",
    ".venv",
    "venv",
    "__pycache__"
)

foreach ($pattern in $RemovePatterns) {
    Get-ChildItem $TempDir -Recurse -Force -Directory |
        Where-Object { $_.Name -eq $pattern } |
        ForEach-Object {
            Remove-Item $_.FullName -Recurse -Force
            Write-Host "[CLEAN] Removed $($_.FullName)"
        }
}

Get-ChildItem $TempDir -Recurse -Force -File |
    Where-Object {
        $_.Extension -in @(".pyc", ".pyo") -or
        $_.Name -eq ".DS_Store"
    } |
    ForEach-Object {
        Remove-Item $_.FullName -Force
        Write-Host "[CLEAN] Removed $($_.FullName)"
    }

$DownloadsDir = Join-Path $TempDir "downloads"

if (Test-Path $DownloadsDir) {
    Get-ChildItem $DownloadsDir -Force |
        Where-Object { $_.Name -ne ".gitkeep" } |
        ForEach-Object {
            Remove-Item $_.FullName -Recurse -Force
            Write-Host "[CLEAN] Removed download item $($_.Name)"
        }

    $Gitkeep = Join-Path $DownloadsDir ".gitkeep"

    if (-not (Test-Path $Gitkeep)) {
        New-Item -ItemType File -Force $Gitkeep | Out-Null
        Write-Host "[OK] Created downloads\.gitkeep"
    }
}

if (Test-Path $OutputPath) {
    Remove-Item $OutputPath -Force
}

Compress-Archive -Path (Join-Path $TempDir "*") -DestinationPath $OutputPath -Force

Write-Host ""
Write-Host "[DONE] Portable ZIP created:"
Write-Host $OutputPath
Write-Host ""