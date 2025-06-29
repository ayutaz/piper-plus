# Simple Windows build script for Piper
# This script downloads pre-built dependencies and builds only the main piper executable

param(
    [string]$BuildType = "Release",
    [string]$Platform = "x64"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Piper Windows Build Script ===" -ForegroundColor Green
Write-Host "Build Type: $BuildType" -ForegroundColor Yellow
Write-Host "Platform: $Platform" -ForegroundColor Yellow

# Create build directory
$BuildDir = "build_simple"
if (Test-Path $BuildDir) {
    Write-Host "Cleaning existing build directory..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $BuildDir
}
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

# Download dependencies
$DepsDir = "$BuildDir/deps"
New-Item -ItemType Directory -Force -Path $DepsDir | Out-Null

Write-Host "`nDownloading dependencies..." -ForegroundColor Green

# Download pre-built espeak-ng
$EspeakUrl = "https://github.com/espeak-ng/espeak-ng/releases/download/1.51.1/espeak-ng-X64.msi"
$EspeakInstaller = "$DepsDir/espeak-ng.msi"
if (!(Test-Path $EspeakInstaller)) {
    Write-Host "Downloading espeak-ng..."
    Invoke-WebRequest -Uri $EspeakUrl -OutFile $EspeakInstaller
}

# Extract espeak-ng without installing
Write-Host "Extracting espeak-ng..."
$EspeakDir = "$DepsDir/espeak-ng"
New-Item -ItemType Directory -Force -Path $EspeakDir | Out-Null
msiexec /a $EspeakInstaller /qb TARGETDIR="$((Get-Location).Path)\$EspeakDir"

# Download ONNX Runtime
$OnnxVersion = "1.16.3"
$OnnxUrl = "https://github.com/microsoft/onnxruntime/releases/download/v$OnnxVersion/onnxruntime-win-x64-$OnnxVersion.zip"
$OnnxZip = "$DepsDir/onnxruntime.zip"
if (!(Test-Path $OnnxZip)) {
    Write-Host "Downloading ONNX Runtime..."
    Invoke-WebRequest -Uri $OnnxUrl -OutFile $OnnxZip
}

Write-Host "Extracting ONNX Runtime..."
Expand-Archive -Path $OnnxZip -DestinationPath $DepsDir -Force
$OnnxDir = "$DepsDir/onnxruntime-win-x64-$OnnxVersion"

# Download fmt
$FmtVersion = "10.0.0"
$FmtUrl = "https://github.com/fmtlib/fmt/archive/refs/tags/$FmtVersion.zip"
$FmtZip = "$DepsDir/fmt.zip"
if (!(Test-Path $FmtZip)) {
    Write-Host "Downloading fmt..."
    Invoke-WebRequest -Uri $FmtUrl -OutFile $FmtZip
}
Expand-Archive -Path $FmtZip -DestinationPath $DepsDir -Force

# Download spdlog
$SpdlogVersion = "1.12.0"
$SpdlogUrl = "https://github.com/gabime/spdlog/archive/refs/tags/v$SpdlogVersion.zip"
$SpdlogZip = "$DepsDir/spdlog.zip"
if (!(Test-Path $SpdlogZip)) {
    Write-Host "Downloading spdlog..."
    Invoke-WebRequest -Uri $SpdlogUrl -OutFile $SpdlogZip
}
Expand-Archive -Path $SpdlogZip -DestinationPath $DepsDir -Force

# Build fmt
Write-Host "`nBuilding fmt..." -ForegroundColor Green
$FmtBuildDir = "$BuildDir/fmt-build"
cmake -S "$DepsDir/fmt-$FmtVersion" -B $FmtBuildDir `
    -G "Visual Studio 17 2022" -A $Platform `
    -DCMAKE_BUILD_TYPE=$BuildType `
    -DFMT_TEST=OFF `
    -DBUILD_SHARED_LIBS=OFF

cmake --build $FmtBuildDir --config $BuildType

# Build spdlog
Write-Host "`nBuilding spdlog..." -ForegroundColor Green
$SpdlogBuildDir = "$BuildDir/spdlog-build"
cmake -S "$DepsDir/spdlog-$SpdlogVersion" -B $SpdlogBuildDir `
    -G "Visual Studio 17 2022" -A $Platform `
    -DCMAKE_BUILD_TYPE=$BuildType `
    -DSPDLOG_BUILD_SHARED=OFF `
    -DSPDLOG_FMT_EXTERNAL=ON `
    -Dfmt_DIR="$FmtBuildDir"

cmake --build $SpdlogBuildDir --config $BuildType

# Create simplified CMakeLists.txt for piper only
$SimpleCMake = @"
cmake_minimum_required(VERSION 3.13)
project(piper_simple C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Force static runtime
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded`$<`$<CONFIG:Debug>:Debug>")

# Add main executable
add_executable(piper 
    src/cpp/main.cpp 
    src/cpp/piper.cpp
    src/cpp/openjtalk_phonemize.cpp
    src/cpp/openjtalk_wrapper.c
    src/cpp/openjtalk_dictionary_manager.c
)

# Define version
file(READ "`${CMAKE_SOURCE_DIR}/VERSION" piper_version)
string(STRIP "`${piper_version}" piper_version)
target_compile_definitions(piper PUBLIC _PIPER_VERSION=`${piper_version})

# Windows specific
target_compile_definitions(piper PUBLIC WIN32_LEAN_AND_MEAN _WIN32_WINNT=0x0601)

# Include directories
target_include_directories(piper PUBLIC
    `${CMAKE_SOURCE_DIR}/src/cpp
    $((Get-Location).Path)/$FmtBuildDir/include
    $((Get-Location).Path)/$DepsDir/spdlog-$SpdlogVersion/include
    $((Get-Location).Path)/$OnnxDir/include
    $((Get-Location).Path)/$EspeakDir/ProgramFiles/eSpeak_NG/include
)

# Link libraries
target_link_libraries(piper
    $((Get-Location).Path)/$FmtBuildDir/$BuildType/fmt.lib
    $((Get-Location).Path)/$SpdlogBuildDir/$BuildType/spdlog.lib
    $((Get-Location).Path)/$OnnxDir/lib/onnxruntime.lib
    $((Get-Location).Path)/$EspeakDir/ProgramFiles/eSpeak_NG/lib/espeak-ng.lib
)

# Copy DLLs
add_custom_command(TARGET piper POST_BUILD
    COMMAND `${CMAKE_COMMAND} -E copy_if_different
        "$((Get-Location).Path)/$OnnxDir/lib/onnxruntime.dll"
        "`$<TARGET_FILE_DIR:piper>"
    COMMAND `${CMAKE_COMMAND} -E copy_if_different
        "$((Get-Location).Path)/$EspeakDir/ProgramFiles/eSpeak_NG/libespeak-ng.dll"
        "`$<TARGET_FILE_DIR:piper>"
)

# Install
install(TARGETS piper DESTINATION bin)
install(FILES
    "$((Get-Location).Path)/$OnnxDir/lib/onnxruntime.dll"
    "$((Get-Location).Path)/$EspeakDir/ProgramFiles/eSpeak_NG/libespeak-ng.dll"
    DESTINATION bin
)
"@

$SimpleCMake | Out-File -FilePath "$BuildDir/CMakeLists.txt" -Encoding UTF8

# Copy source files
Write-Host "`nCopying source files..." -ForegroundColor Green
Copy-Item -Path "src" -Destination $BuildDir -Recurse
Copy-Item -Path "VERSION" -Destination $BuildDir

# Build piper
Write-Host "`nBuilding piper..." -ForegroundColor Green
$PiperBuildDir = "$BuildDir/piper-build"
cmake -S $BuildDir -B $PiperBuildDir `
    -G "Visual Studio 17 2022" -A $Platform `
    -DCMAKE_BUILD_TYPE=$BuildType `
    -DCMAKE_INSTALL_PREFIX="$BuildDir/install"

cmake --build $PiperBuildDir --config $BuildType
cmake --install $PiperBuildDir --config $BuildType

Write-Host "`nBuild complete!" -ForegroundColor Green
Write-Host "Piper executable: $BuildDir/install/bin/piper.exe" -ForegroundColor Yellow

# Test the build
if (Test-Path "$BuildDir/install/bin/piper.exe") {
    Write-Host "`nTesting piper..." -ForegroundColor Green
    & "$BuildDir/install/bin/piper.exe" --help
} else {
    Write-Host "ERROR: piper.exe not found!" -ForegroundColor Red
    exit 1
}