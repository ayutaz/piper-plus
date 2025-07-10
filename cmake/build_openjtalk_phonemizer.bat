@echo off
REM Build open_jtalk_phonemizer after OpenJTalk is built

set SRCDIR=%1
set BUILDDIR=%2
set CC=%3
set HTS_ENGINE_DIR=%4
if "%CC%"=="" set CC=cl

cd /d "%SRCDIR%\bin"

REM Compile open_jtalk_phonemizer
%CC% /Fe:open_jtalk_phonemizer.exe open_jtalk_phonemizer.c ^
    /I..\mecab\src /I..\njd /I..\jpcommon /I..\njd_set_accent_phrase ^
    /I..\njd_set_accent_type /I..\njd_set_digit /I..\njd_set_long_vowel ^
    /I..\njd_set_pronunciation /I..\njd_set_unvoiced_vowel /I..\njd2jpcommon ^
    /I..\text2mecab /I..\mecab2njd ^
    ..\text2mecab\Release\text2mecab.lib ^
    ..\mecab2njd\Release\mecab2njd.lib ^
    ..\njd_set_pronunciation\Release\njd_set_pronunciation.lib ^
    ..\njd_set_digit\Release\njd_set_digit.lib ^
    ..\njd_set_accent_phrase\Release\njd_set_accent_phrase.lib ^
    ..\njd_set_accent_type\Release\njd_set_accent_type.lib ^
    ..\njd_set_unvoiced_vowel\Release\njd_set_unvoiced_vowel.lib ^
    ..\njd_set_long_vowel\Release\njd_set_long_vowel.lib ^
    ..\njd2jpcommon\Release\njd2jpcommon.lib ^
    ..\jpcommon\Release\jpcommon.lib ^
    ..\mecab\src\Release\mecab.lib ^
    ..\njd\Release\njd.lib ^
    "%HTS_ENGINE_DIR%\lib\HTSEngine.lib"

if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

REM Copy to install directory
copy open_jtalk_phonemizer.exe "%BUILDDIR%\bin\"