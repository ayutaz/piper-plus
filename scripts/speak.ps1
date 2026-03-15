<#
.SYNOPSIS
    piper-plus Text-to-Speech helper script
.DESCRIPTION
    Generates speech audio from text using piper-plus TTS engine.
    Handles UTF-8 encoding automatically for Japanese and other languages.
.PARAMETER Text
    The text to synthesize
.PARAMETER Model
    Path to ONNX model file (optional, auto-detected)
.PARAMETER Config
    Path to model config file (optional, auto-detected)
.PARAMETER Speaker
    Speaker ID for multi-speaker models (default: 0)
.PARAMETER OutputFile
    Output WAV file path (default: output.wav)
.PARAMETER NoPlay
    Don't auto-play the generated audio
.EXAMPLE
    .\speak.ps1 "こんにちは"
.EXAMPLE
    .\speak.ps1 -Model "models\tsukuyomi.onnx" -Text "テスト"
.EXAMPLE
    .\speak.ps1 -Speaker 0 -OutputFile greet.wav "おはようございます"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$Text,

    [string]$Model,
    [string]$Config,
    [int]$Speaker = -1,
    [string]$OutputFile = "output.wav",
    [switch]$NoPlay
)

# Ensure UTF-8 encoding
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

# Find piper.exe
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$piperLocations = @(
    (Join-Path $scriptDir "piper.exe"),
    (Join-Path $scriptDir "..\bin\piper.exe"),
    (Join-Path $scriptDir "build\Release\piper.exe")
)

$piperExe = $null
foreach ($loc in $piperLocations) {
    if (Test-Path $loc) {
        $piperExe = (Resolve-Path $loc).Path
        break
    }
}

if (-not $piperExe) {
    Write-Error "piper.exe not found. Place this script in the same directory as piper.exe."
    exit 1
}

# Build arguments
$piperArgs = @("--text", $Text, "--output_file", $OutputFile)

if ($Model) {
    $piperArgs += @("--model", $Model)
}

if ($Config) {
    $piperArgs += @("--config", $Config)
}

if ($Speaker -ge 0) {
    $piperArgs += @("--speaker", $Speaker.ToString())
}

# Run piper
Write-Host "Generating speech..." -ForegroundColor Cyan
& $piperExe @piperArgs

if ($LASTEXITCODE -ne 0) {
    Write-Error "piper.exe failed with exit code $LASTEXITCODE"
    exit 1
}

Write-Host "Generated: $OutputFile" -ForegroundColor Green

# Auto-play
if (-not $NoPlay -and (Test-Path $OutputFile)) {
    Start-Process $OutputFile
}
