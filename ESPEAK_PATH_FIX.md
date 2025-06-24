# espeak-ng Data Path Auto-Detection Fix

## Summary

Fixed the issue where espeak-ng data path was not being detected relative to the executable, requiring users to set environment variables. The solution implements automatic path discovery similar to OpenJTalk's dictionary path handling.

## Changes Made

### 1. Added Auto-Detection in `piper.cpp`

- Added `findEspeakDataPath()` function that:
  - First checks `ESPEAK_DATA_PATH` environment variable
  - Then tries to find the executable path using platform-specific methods
  - Searches for espeak-ng-data in multiple relative locations:
    - `<exe_dir>/espeak-ng-data` (same directory as executable)
    - `<exe_dir>/../share/espeak-ng-data` (standard installed location)
    - `<exe_dir>/../espeak-ng-data` (alternative location)
    - `<exe_dir>/../lib/espeak-ng-data` (another alternative)

- Modified `initialize()` to use the auto-detection when no path is provided

### 2. Updated `main.cpp`

- Changed to pass empty string to `piperConfig.eSpeakDataPath` when no user-provided path
- This triggers auto-detection in `initialize()`

### 3. Updated `test.cpp`

- Modified to accept "auto" as the espeak-ng-data path argument
- When "auto" is passed, uses empty string to trigger auto-detection

### 4. Fixed Installation Path in `CMakeLists.txt`

- Changed espeak-ng-data installation from `${CMAKE_INSTALL_PREFIX}` to `${CMAKE_INSTALL_PREFIX}/share`
- This matches the standard location our auto-detection looks for

### 5. Updated Test Command

- Changed test command to use "auto" instead of hardcoded path

## Benefits

1. **No Environment Variables Required**: Users can download and run piper without setting `ESPEAK_DATA_PATH`
2. **Portable Binaries**: The binary package can be extracted anywhere and will find its data files
3. **Backward Compatible**: Still respects `ESPEAK_DATA_PATH` if set
4. **Consistent with OpenJTalk**: Uses the same pattern as OpenJTalk dictionary discovery

## Testing

To test the implementation:

1. Build piper normally
2. Install it to a prefix: `make install`
3. Run the installed binary without setting `ESPEAK_DATA_PATH`
4. It should automatically find espeak-ng-data in `../share/espeak-ng-data` relative to the binary

The included `test_espeak_path.cpp` can be compiled separately to test the path discovery logic.