# PowerShell script to download OpenJTalk binary for Windows
# This is a temporary solution until the automated builds are available

param(
    [string]$TargetDir = "piper/bin"
)

Write-Host "OpenJTalk Windows binary download script" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green

# Create target directory if it doesn't exist
if (!(Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}

$openJtalkPath = Join-Path $TargetDir "open_jtalk.exe"

# Check if already exists
if (Test-Path $openJtalkPath) {
    Write-Host "OpenJTalk binary already exists at: $openJtalkPath" -ForegroundColor Yellow
    exit 0
}

Write-Host "Downloading OpenJTalk binary..." -ForegroundColor Cyan

# Alternative download sources (update these with actual URLs when available)
$downloadUrls = @(
    # Primary URL (will work after PR is merged to ayutaz/piper-plus)
    "https://github.com/ayutaz/piper-plus/releases/download/openjtalk-windows-latest/open_jtalk.exe",
    
    # Alternative: Build from source using MSYS2
    # Instructions will be added in WINDOWS_OPENJTALK.md
)

$downloaded = $false
foreach ($url in $downloadUrls) {
    try {
        Write-Host "Trying: $url" -ForegroundColor Gray
        Invoke-WebRequest -Uri $url -OutFile $openJtalkPath -ErrorAction Stop
        $downloaded = $true
        Write-Host "Successfully downloaded OpenJTalk binary" -ForegroundColor Green
        break
    }
    catch {
        Write-Host "Failed to download from: $url" -ForegroundColor Red
    }
}

if (!$downloaded) {
    Write-Host "`nFailed to download OpenJTalk binary." -ForegroundColor Red
    Write-Host "Please see docs/WINDOWS_OPENJTALK.md for manual build instructions." -ForegroundColor Yellow
    exit 1
}

Write-Host "`nOpenJTalk binary saved to: $openJtalkPath" -ForegroundColor Green