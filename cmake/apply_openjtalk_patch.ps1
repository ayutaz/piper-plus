param([string]$SourceDir)

$filePath = Join-Path $SourceDir "mecab/src/dictionary.cpp"
Write-Host "Patching file: $filePath"

if (Test-Path $filePath) {
    # Read content as individual lines to preserve formatting
    $lines = Get-Content -Path $filePath
    
    # Check if already patched
    $content = Get-Content -Path $filePath -Raw
    if ($content -match 'MSVC_BINARY_FUNCTION_WORKAROUND') {
        Write-Host "File already patched"
        exit 0
    }
    
    Write-Host "Applying C++17 compatibility patch..."
    
    # Build new content - insert the fix after includes
    $newLines = @()
    $insertDone = $false
    
    for ($i = 0; $i -lt $lines.Length; $i++) {
        # Look for a good place to insert - after the last include but before namespace
        if (-not $insertDone -and $lines[$i] -match '^\s*namespace\s+MeCab\s*\{') {
            # Insert before the MeCab namespace
            $newLines += ''
            $newLines += '// MSVC_BINARY_FUNCTION_WORKAROUND'
            $newLines += '#if defined(_MSC_VER) && _MSC_VER >= 1900'
            $newLines += '// VS2015 and later removed std::binary_function'
            $newLines += 'namespace std {'
            $newLines += '  template<typename Arg1, typename Arg2, typename Result>'
            $newLines += '  struct binary_function {'
            $newLines += '    typedef Arg1 first_argument_type;'
            $newLines += '    typedef Arg2 second_argument_type;'
            $newLines += '    typedef Result result_type;'
            $newLines += '  };'
            $newLines += '}'
            $newLines += '#endif'
            $newLines += ''
            $insertDone = $true
        }
        
        # Add the original line
        $newLines += $lines[$i]
    }
    
    if (-not $insertDone) {
        Write-Host "ERROR: Could not find appropriate insertion point"
        exit 1
    }
    
    # Write the patched content
    Set-Content -Path $filePath -Value $newLines
    Write-Host "Successfully applied C++17 compatibility patch"
    
    # Verify the patch
    $verifyContent = Get-Content -Path $filePath -Raw
    if ($verifyContent -match 'MSVC_BINARY_FUNCTION_WORKAROUND') {
        Write-Host "Patch verification: SUCCESS"
    } else {
        Write-Host "Patch verification: FAILED"
        exit 1
    }
} else {
    Write-Host "ERROR: File not found: $filePath"
    exit 1
}