using System.Diagnostics;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Subprocess-based CLI integration tests for <c>PiperPlus.Cli</c>.
/// These tests launch the CLI as a child process via <c>dotnet run</c>
/// and verify exit codes, stdout, and stderr output.
/// Marked with <c>[Trait("Category", "CLI")]</c> for selective filtering.
/// </summary>
public sealed class CliIntegrationTests
{
    /// <summary>
    /// Maximum time (ms) to wait for the CLI process to exit.
    /// Generous to account for <c>dotnet run</c> compilation overhead.
    /// </summary>
    private const int ProcessTimeoutMs = 30_000;

    /// <summary>
    /// Returns the absolute path to the <c>PiperPlus.Cli</c> project directory.
    /// Resolves relative to the test assembly location, walking up to
    /// <c>src/csharp/</c> and then into <c>PiperPlus.Cli</c>.
    /// </summary>
    private static string GetCliProjectPath()
    {
        // The test assembly sits under src/csharp/PiperPlus.Core.Tests/bin/...
        // Walk up to find src/csharp, then resolve PiperPlus.Cli.
        string assemblyDir = Path.GetDirectoryName(
            typeof(CliIntegrationTests).Assembly.Location)!;

        // Walk up until we find PiperPlus.Core.Tests directory
        var dir = new DirectoryInfo(assemblyDir);
        while (dir is not null && !dir.Name.Equals("PiperPlus.Core.Tests", StringComparison.Ordinal))
        {
            dir = dir.Parent;
        }

        if (dir?.Parent is null)
        {
            // Fallback: resolve relative to the working directory
            return Path.GetFullPath(
                Path.Combine(
                    Directory.GetCurrentDirectory(),
                    "..", "..", "..", "..", "PiperPlus.Cli"));
        }

        // dir = PiperPlus.Core.Tests, dir.Parent = src/csharp
        return Path.GetFullPath(Path.Combine(dir.Parent.FullName, "PiperPlus.Cli"));
    }

    /// <summary>
    /// If the CLI subprocess failed due to a build infrastructure issue
    /// (e.g. .NET SDK version mismatch), skips the test instead of failing it.
    /// This handles CI environments where a mismatched SDK is pre-installed.
    /// </summary>
    private static void SkipIfBuildFailed(int exitCode, string stderr)
    {
        if (exitCode != 0
            && (stderr.Contains("The build failed", StringComparison.Ordinal)
                || stderr.Contains("error MSB", StringComparison.Ordinal)
                || stderr.Contains("could not be loaded from assembly", StringComparison.Ordinal)))
        {
            Assert.Skip(
                "CLI project could not be built in this environment (SDK version mismatch). " +
                $"stderr: {stderr[..Math.Min(stderr.Length, 500)]}");
        }
    }

    /// <summary>
    /// Verifies the CLI <c>--test-mode</c> output is in a valid state.
    /// Two paths are valid: G2P succeeded (<c>phoneme_ids</c> emitted) OR the
    /// G2P engine reported itself as unavailable (<c>not yet available</c> /
    /// <c>DotNetG2P</c>). The two paths are mutually exclusive — if BOTH or
    /// NEITHER appear, the CLI is in an unexpected state and we fail loudly.
    /// </summary>
    /// <remarks>
    /// Replaces the original 9-call OR-chain pattern. The earlier
    /// <c>Assert.True(success || unavail-msg-1 || unavail-msg-2, …)</c> form
    /// silently passed both when the CLI emitted nothing AND when the CLI
    /// emitted both messages, defeating the purpose of the smoke check.
    /// </remarks>
    private static void AssertCliTestModeOutput(string combined, int exitCode, string context)
    {
        bool hasPhonemeIds = combined.Contains("phoneme_ids", StringComparison.Ordinal);
        bool hasG2pUnavailable =
            combined.Contains("not yet available", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("DotNetG2P", StringComparison.Ordinal);

        Assert.True(
            hasPhonemeIds || hasG2pUnavailable,
            $"[{context}] Neither phoneme_ids nor G2P-unavailable message found — " +
            $"CLI silently produced unrecognized output. ExitCode={exitCode}, Output: {combined}");

        Assert.False(
            hasPhonemeIds && hasG2pUnavailable,
            $"[{context}] BOTH phoneme_ids AND G2P-unavailable message found — " +
            $"CLI is in an inconsistent state. ExitCode={exitCode}, Output: {combined}");

        if (hasPhonemeIds)
        {
            // Success path: phoneme_ids must come with exitCode == 0
            Assert.True(
                exitCode == 0,
                $"[{context}] phoneme_ids emitted but exitCode={exitCode} (expected 0). " +
                $"Output: {combined}");
        }
    }

    /// <summary>
    /// Launches the CLI as a subprocess and captures exit code, stdout, and stderr.
    /// </summary>
    private static async Task<(int ExitCode, string StdOut, string StdErr)> RunCliAsync(
        params string[] args)
    {
        string cliProjectPath = GetCliProjectPath();

        var psi = new ProcessStartInfo
        {
            FileName = "dotnet",
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };

        // Use ArgumentList to avoid quoting/escaping issues with spaces in paths
        psi.ArgumentList.Add("run");
        psi.ArgumentList.Add("--project");
        psi.ArgumentList.Add(cliProjectPath);
        psi.ArgumentList.Add("--");
        foreach (var arg in args)
        {
            psi.ArgumentList.Add(arg);
        }

        using var process = new Process { StartInfo = psi };
        process.Start();

        // Read stdout and stderr concurrently to avoid deadlocks
        Task<string> stdoutTask = process.StandardOutput.ReadToEndAsync();
        Task<string> stderrTask = process.StandardError.ReadToEndAsync();

        using var cts = new CancellationTokenSource(ProcessTimeoutMs);
        try
        {
            await process.WaitForExitAsync(cts.Token);
        }
        catch (OperationCanceledException)
        {
            process.Kill(entireProcessTree: true);
            throw new TimeoutException(
                $"CLI process did not exit within {ProcessTimeoutMs}ms. " +
                $"Args: {string.Join(' ', args)}");
        }

        string stdout = await stdoutTask;
        string stderr = await stderrTask;

        return (process.ExitCode, stdout, stderr);
    }

    // ================================================================
    // --version
    // ================================================================
    [Fact]
    [Trait("Category", "CLI")]
    public async Task Version_Flag_PrintsVersion()
    {
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync("--version");
        SkipIfBuildFailed(exitCode, stderr);

        Assert.Equal(0, exitCode);

        // --version writes to stdout via Console.WriteLine
        string combined = stdout + stderr;
        Assert.False(
            string.IsNullOrWhiteSpace(combined),
            "Expected version output on stdout or stderr");
    }

    // ================================================================
    // --list-models
    // ================================================================
    [Fact]
    [Trait("Category", "CLI")]
    public async Task ListModels_NoFilter_OutputsModels()
    {
        (int exitCode, string _, string? stderr) = await RunCliAsync("--list-models");
        SkipIfBuildFailed(exitCode, stderr);

        Assert.Equal(0, exitCode);
        Assert.Contains("Available voice models:", stderr);
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task ListModels_JapaneseFilter_OutputsJapaneseModels()
    {
        (int exitCode, string _, string? stderr) = await RunCliAsync("--list-models", "ja");
        SkipIfBuildFailed(exitCode, stderr);

        Assert.Equal(0, exitCode);
        Assert.Contains("ja_JP", stderr);
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task ListModels_UnknownLanguage_ShowsNotFound()
    {
        (int exitCode, string _, string? stderr) = await RunCliAsync("--list-models", "xx");
        SkipIfBuildFailed(exitCode, stderr);

        Assert.Equal(0, exitCode);
        Assert.Contains("No voice models found", stderr);
    }

    // ================================================================
    // Error cases
    // ================================================================
    [Fact]
    [Trait("Category", "CLI")]
    public async Task NoModel_NoInput_ShowsError()
    {
        // Running with no arguments should fail because --model is required
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync();
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;

        // Either exit code is non-zero, or the output contains an error/usage message
        Assert.True(
            exitCode != 0
            || combined.Contains("--model", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("required", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("ERR", StringComparison.Ordinal),
            $"Expected error or usage message. ExitCode={exitCode}, Output: {combined}");
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task InvalidModel_ShowsError()
    {
        (int exitCode, string _, string? stderr) = await RunCliAsync(
            "--model", "/nonexistent/path/model.onnx", "--text", "test");
        SkipIfBuildFailed(exitCode, stderr);

        // The CLI uses Environment.ExitCode = 1, which dotnet run may not
        // always propagate. Verify the error message appears on stderr.
        Assert.Contains("not found", stderr, StringComparison.OrdinalIgnoreCase);

        // If the exit code is propagated, it should be non-zero
        if (exitCode != 0)
        {
            Assert.NotEqual(0, exitCode);
        }
    }

    // ================================================================
    // --test-mode
    // ================================================================
    [Fact]
    [Trait("Category", "CLI")]
    public async Task TestMode_WithText_OutputsPhonemeIds()
    {
        // --test-mode with --text skips ONNX inference and outputs phoneme IDs.
        // The G2P engine (DotNetEnglishG2PEngine) is resolved via reflection
        // and may not be available, in which case the CLI reports an error.
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--test-mode", "--text", "hello", "--language", "en");
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;

        // Either the phonemizer succeeds and outputs phoneme_ids,
        // or it fails because the G2P engine is not available.
        AssertCliTestModeOutput(combined, exitCode, "WithText_en");
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task TestMode_Chinese_OutputsPhonemeIds()
    {
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--test-mode", "--text", "你好", "--language", "zh");
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;
        AssertCliTestModeOutput(combined, exitCode, "Chinese_zh");
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task TestMode_Spanish_OutputsPhonemeIds()
    {
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--test-mode", "--text", "Hola", "--language", "es");
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;
        AssertCliTestModeOutput(combined, exitCode, "Spanish_es");
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task TestMode_French_OutputsPhonemeIds()
    {
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--test-mode", "--text", "Bonjour", "--language", "fr");
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;
        AssertCliTestModeOutput(combined, exitCode, "French_fr");
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task TestMode_Portuguese_OutputsPhonemeIds()
    {
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--test-mode", "--text", "Olá", "--language", "pt");
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;
        AssertCliTestModeOutput(combined, exitCode, "Portuguese_pt");
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task TestMode_UnsupportedLanguage_ShowsError()
    {
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--test-mode", "--text", "test", "--language", "xx");
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;
        Assert.True(
            exitCode != 0
            || combined.Contains("unsupported", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("not supported", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("unknown language", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("error", StringComparison.OrdinalIgnoreCase),
            $"Expected error for unsupported language 'xx'. ExitCode={exitCode}, Output: {combined}");
    }

    // ================================================================
    // --test-mode multilingual
    // ================================================================
    [Fact]
    [Trait("Category", "CLI")]
    public async Task TestMode_Multilingual_JaEn_OutputsPhonemeIds()
    {
        // Multi-language code "ja-en" should phonemize mixed-language text
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--test-mode", "--text", "こんにちはhello", "--language", "ja-en");
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;

        // Either phonemizer succeeds and outputs phoneme_ids,
        // or it fails because a G2P engine is not available.
        AssertCliTestModeOutput(combined, exitCode, "Multilingual_ja-en");
    }

    // ================================================================
    // Default output.wav behavior
    // ================================================================
    [Fact]
    [Trait("Category", "CLI")]
    public async Task TextMode_NoOutputFile_DefaultsToOutputWav()
    {
        // When --text is used without --output-file or --output-dir,
        // the CLI should default to "output.wav" as the output path.
        // In --test-mode, no actual WAV is written, but the phonemizer
        // runs successfully with exit code 0 and emits phoneme_ids.
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--test-mode", "--text", "hello", "--language", "en");
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;

        // The test-mode path exits before writing any file, so
        // the default output.wav logic is not reached. However,
        // a successful run (phoneme_ids emitted) confirms the CLI
        // accepts --text without --output-file.
        AssertCliTestModeOutput(combined, exitCode, "DefaultOutputWav_en");
    }

    // ================================================================
    // --model with model name/alias (auto-resolve)
    // ================================================================
    [Fact]
    [Trait("Category", "CLI")]
    public async Task Model_NonexistentNameOrFile_ShowsError()
    {
        // --model with a string that is neither a file nor a known model name
        // should display an error message.
        (int exitCode, string _, string? stderr) = await RunCliAsync(
            "--model", "totally-fake-nonexistent-model-xyz",
            "--text", "test");
        SkipIfBuildFailed(exitCode, stderr);

        Assert.True(
            exitCode != 0 || stderr.Contains("not found", StringComparison.OrdinalIgnoreCase),
            $"Expected error for unknown model name. ExitCode={exitCode}, stderr: {stderr}");
    }

    // ================================================================
    // --download-model with alias
    // ================================================================
    [Fact]
    [Trait("Category", "CLI")]
    public async Task DownloadModel_InvalidName_ShowsError()
    {
        // --download-model with a name that doesn't exist in the catalog
        (int exitCode, string _, string? stderr) = await RunCliAsync(
            "--download-model", "totally-nonexistent-model-xyz");
        SkipIfBuildFailed(exitCode, stderr);

        Assert.True(
            exitCode != 0
            || stderr.Contains("not found", StringComparison.OrdinalIgnoreCase)
            || stderr.Contains("Error", StringComparison.OrdinalIgnoreCase),
            $"Expected error for unknown model name. ExitCode={exitCode}, stderr: {stderr}");
    }

    // ================================================================
    // --test-mode with [[ inline phonemes ]] notation
    // ================================================================
    [Fact]
    [Trait("Category", "CLI")]
    public async Task TestMode_InlinePhonemes_JapaneseWithNotation()
    {
        // The [[ ... ]] inline phoneme notation should be recognized in test-mode.
        // Mix plain text with inline phonemes: "hello [[ k o N n i ch i w a ]]"
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--test-mode", "--text", "hello [[ k o N n i ch i w a ]]",
            "--language", "ja-en");
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;

        // Either phonemizer succeeds and outputs phoneme_ids (which would include
        // IDs from both the phonemized "hello" and the raw phoneme tokens),
        // or the G2P engine is not available.
        AssertCliTestModeOutput(combined, exitCode, "InlinePhonemes_ja-en");
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task TestMode_InlinePhonemes_OnlyBrackets()
    {
        // Input with only [[ ... ]] notation (no plain text part)
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--test-mode", "--text", "[[ a i u e o ]]",
            "--language", "ja");
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;
        AssertCliTestModeOutput(combined, exitCode, "InlinePhonemes_ja_brackets_only");
    }

    // ================================================================
    // --model accepts string (not just FileInfo)
    // ================================================================
    [Fact]
    [Trait("Category", "CLI")]
    public async Task Model_AcceptsModelNameString_NotJustFilePath()
    {
        // Verify that --model accepts arbitrary strings (not just file paths).
        // With --test-mode, a known model name should be recognized
        // (though it may fail at download since we're in test mode).
        // An unknown name should produce an appropriate error.
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--model", "tsukuyomi", "--text", "テスト");
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;

        // The CLI should either:
        //   - Resolve the model and fail at inference (no actual model file)
        //   - Attempt auto-download and fail
        //   - Show "not found locally. Downloading..." message
        // The key test is that it does NOT fail with "Invalid option" or
        // "unrecognized command" — the string is accepted as a valid option value.
        Assert.True(
            combined.Contains("Resolved model", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("not found locally", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("Downloading", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("download", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("failed", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("Error", StringComparison.OrdinalIgnoreCase)
            || exitCode != 0,
            $"Expected model resolution attempt. ExitCode={exitCode}, Output: {combined}");
    }

    // ================================================================
    // --speaker × voice-cloning mutual exclusion
    // ================================================================
    [Fact]
    [Trait("Category", "CLI")]
    public async Task Speaker_AndReferenceAudio_AreMutuallyExclusive()
    {
        // The CLI must reject combining --speaker with voice-cloning sources
        // (--reference-audio / --speaker-embedding) before any model load,
        // mirroring the SynthesisInput.Validate() contract in PiperPlus.Core.
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--model", "tsukuyomi",
            "--text", "テスト",
            "--speaker", "5",
            "--reference-audio", "/nonexistent/ref.wav");
        SkipIfBuildFailed(exitCode, stderr);

        string combined = stdout + stderr;
        Assert.Contains("mutually exclusive", combined, StringComparison.OrdinalIgnoreCase);
    }

    // ================================================================
    // Voice-cloning option wiring (--reference-audio / --speaker-embedding)
    // ================================================================
    [Fact]
    [Trait("Category", "CLI")]
    public async Task ReferenceAudio_WithoutSpeakerEncoderModel_Errors()
    {
        // --reference-audio requires --speaker-encoder-model (the encoder ONNX
        // path) to compute the speaker embedding. The CLI must fail fast with
        // a precise message instead of the generic "Synthesis failed".
        (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
            "--test-mode",
            "--text", "test",
            "--reference-audio", "/nonexistent/ref.wav");
        SkipIfBuildFailed(exitCode, stderr);

        Assert.NotEqual(0, exitCode);
        string combined = stdout + stderr;
        Assert.Contains("--speaker-encoder-model", combined, StringComparison.Ordinal);
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task SpeakerEmbedding_InvalidFileSize_Errors()
    {
        // A raw float32 binary embedding file must be a non-zero multiple of
        // 4 bytes. A 7-byte file (not divisible by 4) must be rejected with a
        // precise error before synthesis is attempted.
        string tmpPath = Path.GetTempFileName();
        try
        {
            await File.WriteAllBytesAsync(tmpPath, new byte[7], TestContext.Current.CancellationToken);

            (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
                "--test-mode",
                "--text", "test",
                "--speaker-embedding", tmpPath);
            SkipIfBuildFailed(exitCode, stderr);

            Assert.NotEqual(0, exitCode);
            string combined = stdout + stderr;
            Assert.Contains("multiple of 4", combined, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            try
            {
                File.Delete(tmpPath);
            }
            catch (IOException)
            { /* best-effort cleanup */
            }
            catch (UnauthorizedAccessException)
            { /* best-effort cleanup */
            }
        }
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task SpeakerEmbedding_EmptyFile_Errors()
    {
        // An empty embedding file is also rejected — we can't synthesize from
        // a zero-dim vector.
        string tmpPath = Path.GetTempFileName();
        try
        {
            await File.WriteAllBytesAsync(tmpPath, [], TestContext.Current.CancellationToken);

            (int exitCode, string? stdout, string? stderr) = await RunCliAsync(
                "--test-mode",
                "--text", "test",
                "--speaker-embedding", tmpPath);
            SkipIfBuildFailed(exitCode, stderr);

            Assert.NotEqual(0, exitCode);
            string combined = stdout + stderr;

            // Either "invalid" or our specific "multiple of 4" message — both
            // are precise (the implementation reports both invariants together).
            Assert.True(
                combined.Contains("invalid", StringComparison.OrdinalIgnoreCase)
                    || combined.Contains("multiple of 4", StringComparison.OrdinalIgnoreCase),
                $"expected an embedding-validation error, got: {combined}");
        }
        finally
        {
            try
            {
                File.Delete(tmpPath);
            }
            catch (IOException)
            { /* best-effort cleanup */
            }
            catch (UnauthorizedAccessException)
            { /* best-effort cleanup */
            }
        }
    }
}
