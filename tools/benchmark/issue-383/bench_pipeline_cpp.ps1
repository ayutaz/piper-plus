# Issue #383 C++ Phase 1 実機ベンチ
#
# piper.exe を serial (PIPER_G2P_PARALLELISM=1) と parallel (auto) で呼び、
# total wall-clock を計測する。warmup 1 + repeats 3、median を採用。
#
# Usage (from repo root):
#   pwsh -File tools/benchmark/issue-383/bench_pipeline_cpp.ps1

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot/../../..").Path
$Piper = Join-Path $RepoRoot "build/Release/piper.exe"
$Model = Join-Path $RepoRoot "test/models/multilingual-test-medium.onnx"
$TextFile = Join-Path $RepoRoot "tools/benchmark/texts/ja.txt"
$OutDir = Join-Path $RepoRoot "tools/benchmark/issue-383/cpp_bench_tmp"
$ResultsJson = Join-Path $RepoRoot "tools/benchmark/issue-383/cpp_bench_results.json"

if (-not (Test-Path $Piper)) { throw "piper.exe not found: $Piper" }
if (-not (Test-Path $Model)) { throw "model not found: $Model" }
if (-not (Test-Path $TextFile)) { throw "text not found: $TextFile" }

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

$Sentences = Get-Content $TextFile -Encoding UTF8 | Where-Object { $_.Trim() -ne "" }
$NSentences = $Sentences.Count
Write-Host "[bench] piper: $Piper"
Write-Host "[bench] model: $Model"
Write-Host "[bench] $NSentences seed sentences"

function Build-Text([int]$N) {
    if ($N -le $Sentences.Count) {
        return ($Sentences[0..($N-1)] -join "")
    }
    $buf = ""
    for ($i = 0; $i -lt $N; $i++) {
        $buf += $Sentences[$i % $Sentences.Count]
    }
    return $buf
}

function Run-Once([string]$Text, [string]$OutWav) {
    # piper.exe は --text 引数で直接テキストを取る (Windows のコマンドライン
    # 長制限があるが N=50 までならまず安全)。
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    & $Piper -m $Model -t $Text -f $OutWav --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "piper.exe failed (exit=$LASTEXITCODE) for text length $($Text.Length)" }
    $sw.Stop()
    return $sw.Elapsed.TotalMilliseconds
}

# Global warmup (process startup, model load, etc.) を均すため事前に 3 回流す。
Write-Host "[bench] global warmup (3 short runs)..."
$wText = Build-Text -N 2
for ($i = 0; $i -lt 3; $i++) { Run-Once $wText (Join-Path $OutDir "warmup_$i.wav") | Out-Null }

$Configs = @(
    @{ Name = "serial";   Env = "1" },
    @{ Name = "parallel"; Env = $null }
)

$Ns = @(1, 2, 5, 10, 20)
$Results = @{}

foreach ($cfg in $Configs) {
    Write-Host "`n[bench] === config: $($cfg.Name) ==="
    if ($null -eq $cfg.Env) {
        Remove-Item Env:PIPER_G2P_PARALLELISM -ErrorAction SilentlyContinue
    } else {
        $env:PIPER_G2P_PARALLELISM = $cfg.Env
    }

    $cfgResults = @{}
    foreach ($n in $Ns) {
        $text = Build-Text -N $n
        $chars = ($text.ToCharArray() | Where-Object { -not [char]::IsWhiteSpace($_) }).Count
        Write-Host ("[bench] N={0} (chars={1}) - 1 warmup + 3 repeats" -f $n, $chars)
        # Per-N warmup
        Run-Once $text (Join-Path $OutDir ("warm_${($cfg.Name)}_n${n}.wav")) | Out-Null

        $samples = @()
        for ($r = 0; $r -lt 3; $r++) {
            $ms = Run-Once $text (Join-Path $OutDir ("rep_${($cfg.Name)}_n${n}_r${r}.wav"))
            $samples += $ms
            Write-Host ("  rep {0}: {1,8:N1} ms" -f $r, $ms)
        }
        $sorted = $samples | Sort-Object
        $median = $sorted[[int]([Math]::Floor($sorted.Count / 2))]
        # Use string keys for ConvertTo-Json compatibility (PowerShell rejects
        # int-keyed Hashtables when serialising — see PSJsonInvalidKey error).
        $cfgResults["$n"] = @{
            samples = $samples
            median = $median
            mean = ($samples | Measure-Object -Average).Average
        }
    }
    $Results[$cfg.Name] = $cfgResults
}

# Restore env (clean exit)
Remove-Item Env:PIPER_G2P_PARALLELISM -ErrorAction SilentlyContinue

# Save JSON
$payload = @{
    piper_path = $Piper
    model = $Model
    text = $TextFile
    ns = $Ns
    repeats = 3
    warmups = 1
    cpu = (Get-CimInstance Win32_Processor).Name
    os = (Get-CimInstance Win32_OperatingSystem).Caption
    results = $Results
} | ConvertTo-Json -Depth 6
Set-Content -Path $ResultsJson -Value $payload -Encoding UTF8
Write-Host "`n[bench] wrote $ResultsJson"

# Summary table
Write-Host "`n=== SUMMARY (median ms) ==="
Write-Host ("{0,4} {1,12} {2,12} {3,8}" -f "N", "serial_ms", "parallel_ms", "Δ%")
foreach ($n in $Ns) {
    $s = $Results["serial"]["$n"].median
    $p = $Results["parallel"]["$n"].median
    $delta = if ($s -gt 0) { (($p - $s) / $s) * 100 } else { 0 }
    Write-Host ("{0,4} {1,12:N1} {2,12:N1} {3,+8:N1}%" -f $n, $s, $p, $delta)
}

# Cleanup tmp wavs
Remove-Item -Recurse -Force $OutDir -ErrorAction SilentlyContinue
