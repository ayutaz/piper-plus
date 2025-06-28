# PowerShell script to download or check OpenJTalk binary for Windows
param(
    [string]$TargetDir = "bin"
)

$ErrorActionPreference = "Stop"

# Create target directory
if (!(Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir | Out-Null
}

Write-Host "Checking for OpenJTalk binary..."

# Check if OpenJTalk was built by CMake (either stub or real)
$BuiltBinary = Join-Path (Split-Path $TargetDir) "build\oj\bin\open_jtalk.exe"
$TargetBinary = Join-Path $TargetDir "open_jtalk.exe"

if (Test-Path $BuiltBinary) {
    Write-Host "Found OpenJTalk binary built by CMake: $BuiltBinary"
    Write-Host "Note: This is a stub implementation - Japanese TTS is not supported on Windows"
    # The binary will be installed by CMake install process
    exit 0
}

# Also check if it's already in the target directory
if (Test-Path $TargetBinary) {
    Write-Host "OpenJTalk binary already exists: $TargetBinary"
    exit 0
}

# If not built from source, try to download (but this will likely fail)
Write-Host "OpenJTalk was not built from source. Attempting to download..."
Write-Host "Note: Pre-built Windows binaries are not available."

# Download URL for jtalkdll releases
$ReleaseUrl = "https://api.github.com/repos/rosmarinus/jtalkdll/releases/latest"

Write-Host "Fetching latest jtalkdll release..."
try {
    $Release = Invoke-RestMethod -Uri $ReleaseUrl
    Write-Host "Found release: $($Release.name)"
    Write-Host "Available assets:"
    $Release.assets | ForEach-Object { Write-Host "  - $($_.name)" }
    
    # Look for Windows binary - jtalkdll releases use specific naming
    $Asset = $Release.assets | Where-Object { 
        $_.name -like "*.zip"
    } | Select-Object -First 1
    
    if (!$Asset) {
        Write-Warning "Could not find Windows binary in latest release."
        Write-Warning "OpenJTalk needs to be built from source for Windows."
        Write-Warning "Japanese TTS will not be available without OpenJTalk."
        # Don't fail the build, just skip OpenJTalk
        exit 0
    }
    
    $DownloadUrl = $Asset.browser_download_url
    $ZipFile = Join-Path $env:TEMP "jtalkdll.zip"
    
    Write-Host "Downloading from: $DownloadUrl"
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $ZipFile
    
    Write-Host "Extracting files..."
    Expand-Archive -Path $ZipFile -DestinationPath $TargetDir -Force
    
    # Rename jtalkdll.exe to open_jtalk.exe for compatibility
    $JtalkExe = Join-Path $TargetDir "jtalkdll.exe"
    $OpenJtalkExe = Join-Path $TargetDir "open_jtalk.exe"
    
    if (Test-Path $JtalkExe) {
        Move-Item -Path $JtalkExe -Destination $OpenJtalkExe -Force
        Write-Host "Renamed jtalkdll.exe to open_jtalk.exe"
    }
    
    # Clean up
    Remove-Item -Path $ZipFile -Force
    
    Write-Host "OpenJTalk binary successfully downloaded to: $OpenJtalkExe"
    
} catch {
    Write-Warning "Failed to download OpenJTalk: $_"
    Write-Warning "Japanese TTS will not be available without OpenJTalk."
    exit 0
}