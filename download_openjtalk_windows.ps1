# PowerShell script to download OpenJTalk binary for Windows
param(
    [string]$TargetDir = "bin"
)

$ErrorActionPreference = "Stop"

# Create target directory
if (!(Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir | Out-Null
}

# Download URL for jtalkdll releases
$ReleaseUrl = "https://api.github.com/repos/rosmarinus/jtalkdll/releases/latest"

Write-Host "Fetching latest jtalkdll release..."
try {
    $Release = Invoke-RestMethod -Uri $ReleaseUrl
    $Asset = $Release.assets | Where-Object { $_.name -like "*win*.zip" } | Select-Object -First 1
    
    if (!$Asset) {
        Write-Error "Could not find Windows binary in latest release"
        exit 1
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
    Write-Error "Failed to download OpenJTalk: $_"
    exit 1
}