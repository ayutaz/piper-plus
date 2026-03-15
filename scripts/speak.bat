@echo off
setlocal
chcp 65001 >nul 2>&1

REM =============================================
REM speak.bat - piper-plus Text-to-Speech helper
REM =============================================
REM Usage: speak.bat [options] "text to speak"
REM Options:
REM   --model FILE    Path to ONNX model (default: auto-detect)
REM   --config FILE   Path to config file (default: auto-detect)
REM   --speaker NUM   Speaker ID (default: 0)
REM   --output FILE   Output WAV file (default: output.wav)
REM   --no-play       Don't auto-play the output
REM   --help          Show this help

REM Find piper.exe
set "PIPER_EXE="
set "SCRIPT_DIR=%~dp0"

REM Check common locations
if exist "%SCRIPT_DIR%piper.exe" set "PIPER_EXE=%SCRIPT_DIR%piper.exe"
if not defined PIPER_EXE if exist "%SCRIPT_DIR%..\bin\piper.exe" set "PIPER_EXE=%SCRIPT_DIR%..\bin\piper.exe"
if not defined PIPER_EXE if exist "%SCRIPT_DIR%build\Release\piper.exe" set "PIPER_EXE=%SCRIPT_DIR%build\Release\piper.exe"

if not defined PIPER_EXE (
    echo Error: piper.exe not found.
    echo Place this script in the same directory as piper.exe,
    echo or in the project root directory.
    exit /b 1
)

REM Parse arguments
set "MODEL="
set "CONFIG="
set "SPEAKER="
set "OUTPUT=output.wav"
set "NO_PLAY=0"
set "TEXT="

:parse_args
if "%~1"=="" goto :done_args
if "%~1"=="--help" goto :show_help
if "%~1"=="--model" (
    set "MODEL=%~2"
    shift
    shift
    goto :parse_args
)
if "%~1"=="--config" (
    set "CONFIG=%~2"
    shift
    shift
    goto :parse_args
)
if "%~1"=="--speaker" (
    set "SPEAKER=%~2"
    shift
    shift
    goto :parse_args
)
if "%~1"=="--output" (
    set "OUTPUT=%~2"
    shift
    shift
    goto :parse_args
)
if "%~1"=="--no-play" (
    set "NO_PLAY=1"
    shift
    goto :parse_args
)
REM Last argument is the text
set "TEXT=%~1"
shift
if not "%~1"=="" goto :parse_args
goto :done_args

:done_args

if not defined TEXT (
    echo Error: No text provided.
    echo Usage: speak.bat [options] "text to speak"
    echo Run speak.bat --help for more options.
    exit /b 1
)

REM Build piper command
set "CMD="%PIPER_EXE%" --text "%TEXT%" --output_file "%OUTPUT%""
if defined MODEL call set "CMD=%%CMD%% --model "%MODEL%""
if defined CONFIG call set "CMD=%%CMD%% --config "%CONFIG%""
if defined SPEAKER call set "CMD=%%CMD%% --speaker %SPEAKER%"

REM Run piper
%CMD%

if errorlevel 1 (
    echo Error: piper.exe failed.
    exit /b 1
)

echo Generated: %OUTPUT%

REM Auto-play
if "%NO_PLAY%"=="0" (
    if exist "%OUTPUT%" start "" "%OUTPUT%"
)

endlocal
exit /b 0

:show_help
echo.
echo speak.bat - piper-plus Text-to-Speech helper
echo.
echo Usage: speak.bat [options] "text to speak"
echo.
echo Options:
echo   --model FILE    Path to ONNX model file
echo   --config FILE   Path to model config file
echo   --speaker NUM   Speaker ID for multi-speaker models (default: 0)
echo   --output FILE   Output WAV file path (default: output.wav)
echo   --no-play       Don't auto-play the generated audio
echo   --help          Show this help message
echo.
echo Examples:
echo   speak.bat "こんにちは"
echo   speak.bat --model models\tsukuyomi.onnx "テスト"
echo   speak.bat --speaker 0 --output greet.wav "おはようございます"
echo.
endlocal
exit /b 0
