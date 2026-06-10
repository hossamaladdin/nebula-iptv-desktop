<#
.SYNOPSIS
    Build Nebula IPTV as a Windows executable via PyInstaller.

.DESCRIPTION
    Compatible with Windows PowerShell 5.1+ (avoids PS7-only syntax).
    Prompts for release vs. debug-console build. Cleans the build/ and dist/
    folders, then invokes PyInstaller with the right --add-data entries for
    every module + image asset.

.EXAMPLE
    .\build.ps1
        Interactive — prompts which build to produce.

    .\build.ps1 -Mode release
        Build only the release (no console) variant.

    .\build.ps1 -Mode debug
        Build only the debug-console variant.

    .\build.ps1 -Mode both
        Build both variants.
#>

[CmdletBinding()]
param(
    # Default = both, so a fresh clone just needs `./build.ps1` with no flags.
    [ValidateSet('release', 'debug', 'both', 'ask')]
    [string]$Mode = 'both'
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

# ----------------------------------------------------------- prerequisites
# Prefer the `pyinstaller` console script when it's on PATH, otherwise fall
# back to `python -m PyInstaller` — the script gets installed inside the
# user-site Scripts dir on per-user pip installs and that dir isn't always
# on PATH.
$pyInstallerCmd = $null
if (Get-Command pyinstaller -ErrorAction SilentlyContinue) {
    $pyInstallerCmd = @{ Exe = 'pyinstaller'; UseModule = $false }
} else {
    python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pyInstallerCmd = @{ Exe = 'python'; UseModule = $true }
    }
}
if (-not $pyInstallerCmd) {
    Write-Host "PyInstaller not available." -ForegroundColor Red
    Write-Host "Install it with:" -ForegroundColor Yellow
    Write-Host "    python -m pip install --upgrade pyinstaller" -ForegroundColor Yellow
    exit 1
}

$mainScript = 'nebula_iptv.py'
if (-not (Test-Path $mainScript)) {
    Write-Host "Missing main script: $mainScript" -ForegroundColor Red
    exit 1
}

# Force the legacy interactive prompt to read from terminal even when piped.
if ($Mode -eq 'ask') {
    Write-Host ''
    Write-Host 'Nebula IPTV build — pick a target:' -ForegroundColor Cyan
    Write-Host '  1)  Release (no console window)'
    Write-Host '  2)  Debug    (with console window, for troubleshooting)'
    Write-Host '  3)  Both'
    $choice = Read-Host 'Selection [1-3]'
    switch ($choice) {
        '1' { $Mode = 'release' }
        '2' { $Mode = 'debug' }
        '3' { $Mode = 'both' }
        default {
            Write-Host "Unknown selection '$choice'." -ForegroundColor Red
            exit 1
        }
    }
}

# ----------------------------------------------------------- clean output
foreach ($dir in 'build', 'dist') {
    if (Test-Path $dir) {
        Write-Host "Removing $dir/ ..." -ForegroundColor DarkGray
        Remove-Item -Recurse -Force $dir
    }
}

# ----------------------------------------------------------- assets to bundle
# Every image referenced by nebula_iptv.py + every Python module the entry
# point imports. PyInstaller doesn't auto-collect images, and a partial list
# would produce a shipping app that crashes on first use.
$images = @(
    'Images/TV_icon.ico',
    'Images/404_not_found.png',
    'Images/no_image.jpg',
    'Images/loading-icon.png',
    'Images/home_tab_icon.ico',
    'Images/tv_tab_icon.ico',
    'Images/movies_tab_icon.ico',
    'Images/series_tab_icon.ico',
    'Images/favorite_tab_icon.ico',
    'Images/favorite_tab_icon_colour.ico',
    'Images/info_tab_icon.ico',
    'Images/settings_tab_icon.ico',
    'Images/search_bar_icon.ico',
    'Images/sorting_icon.ico',
    'Images/clear_button_icon.ico',
    'Images/go_back_icon.ico',
    'Images/account_manager_icon.ico',
    'Images/film_camera_icon.ico',
    'Images/primary_full-TMDB.svg',
    'Images/yt_icon_rgb.png',
    'Images/unknown_status.png',
    'Images/online_status.png',
    'Images/maybe_status.png',
    'Images/offline_status.png'
)
$modules = @(
    'workers.py',
    'info_boxes.py',
    'accounts.py',
    'tv_root.py',
    'tv_screens.py'
)

# Build the common --add-data argument list (Windows uses `;` separator).
$addDataArgs = @()
foreach ($img in $images)    { $addDataArgs += @('--add-data', "$img;Images") }
foreach ($mod in $modules)   { $addDataArgs += @('--add-data', "$mod;.") }

function Invoke-Build {
    param(
        [string]$Variant,   # 'release' or 'debug'
        [string]$Name
    )

    Write-Host ''
    Write-Host "Building $Name ($Variant) ..." -ForegroundColor Cyan

    $args = @(
        '--clean',
        '--onefile',
        '--noconfirm',
        '--icon', 'Images/TV_icon.ico',
        '--name', $Name,
        '--workpath', 'build',
        '--distpath', 'dist'
    )
    if ($Variant -eq 'release') {
        $args += '--noconsole'
    }
    $args += $addDataArgs
    $args += $mainScript

    if ($pyInstallerCmd.UseModule) {
        & $pyInstallerCmd.Exe '-m' 'PyInstaller' @args
    } else {
        & $pyInstallerCmd.Exe @args
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "PyInstaller failed with exit code $LASTEXITCODE." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

if ($Mode -eq 'release' -or $Mode -eq 'both') {
    Invoke-Build -Variant release -Name 'NebulaIPTV'
}
if ($Mode -eq 'debug' -or $Mode -eq 'both') {
    Invoke-Build -Variant debug -Name 'NebulaIPTV_debug'
}

Write-Host ''
Write-Host 'Done. Executables are in .\dist\' -ForegroundColor Green
Get-ChildItem dist | Format-Table Name, Length, LastWriteTime -AutoSize
