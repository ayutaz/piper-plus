using System;
using System.IO;
using PiperPlus.Cli;
using Xunit;

namespace PiperPlus.Cli.Tests;

/// <summary>
/// Tests for the CLI's fatal-error diagnostics (issue #735).
/// </summary>
/// <remarks>
/// `--version` intermittently exits 1 in CI with
/// <c>[ERR] Fatal error: Unable to find the specified file.</c> -- the
/// parameterless <see cref="FileNotFoundException"/> message, which names no
/// file and no location. The handler now prints the type, the file (when the
/// exception carries one), the stack trace and the inner-exception chain.
///
/// <para>
/// These tests exist because the failure is rare: if the format is wrong, the
/// next occurrence is wasted and the wait starts over. Asserting it here does
/// not need the failure to reproduce.
/// </para>
/// </remarks>
public sealed class FatalDiagnosticsTests
{
    [Fact]
    public void WriteFatalDiagnostics_IncludesTheExceptionType()
    {
        // The message alone did not say it was a FileNotFoundException; that
        // is what identified the defect class in #735.
        var writer = new StringWriter();

        Program.WriteFatalDiagnostics(new FileNotFoundException(), writer);

        string output = writer.ToString();
        Assert.Contains("System.IO.FileNotFoundException", output, StringComparison.Ordinal);
    }

    [Fact]
    public void WriteFatalDiagnostics_IncludesTheMissingFileNameWhenPresent()
    {
        // The whole point: FileNotFoundException's parameterless message is
        // "Unable to find the specified file." with no path in it.
        var writer = new StringWriter();

        Program.WriteFatalDiagnostics(
            new FileNotFoundException("not found", "/models/missing.onnx"), writer);

        string output = writer.ToString();
        Assert.Contains("Missing file: /models/missing.onnx", output, StringComparison.Ordinal);
    }

    [Fact]
    public void WriteFatalDiagnostics_OmitsMissingFileLineWhenTheExceptionHasNoFileName()
    {
        // Anti-vacuity for the case above: a handler that always printed the
        // line (empty) would satisfy it while telling the reader nothing.
        var writer = new StringWriter();

        Program.WriteFatalDiagnostics(new FileNotFoundException(), writer);

        string output = writer.ToString();
        Assert.DoesNotContain("Missing file:", output, StringComparison.Ordinal);
    }

    [Fact]
    public void WriteFatalDiagnostics_IncludesTheStackTrace()
    {
        // Whether the throw happened in BuildRootCommand() or inside
        // Parse()/Invoke() is exactly what #735 cannot currently tell.
        var writer = new StringWriter();
        Exception thrown;
        try
        {
            throw new InvalidOperationException("boom");
        }
        catch (InvalidOperationException ex)
        {
            thrown = ex;
        }

        Program.WriteFatalDiagnostics(thrown, writer);

        string output = writer.ToString();
        Assert.Contains("Stack trace:", output, StringComparison.Ordinal);
        Assert.Contains(
            nameof(WriteFatalDiagnostics_IncludesTheStackTrace),
            output,
            StringComparison.Ordinal);
    }

    [Fact]
    public void WriteFatalDiagnostics_WalksTheWholeInnerExceptionChain()
    {
        // A single "Caused by" would stop at the first level and hide the
        // root, which for a load failure is usually the interesting one.
        var writer = new StringWriter();
        var root = new FileNotFoundException("root cause", "/a/b.dll");
        var middle = new InvalidOperationException("middle", root);
        var outer = new ApplicationException("outer", middle);

        Program.WriteFatalDiagnostics(outer, writer);

        string output = writer.ToString();
        Assert.Contains("Caused by: System.InvalidOperationException: middle", output, StringComparison.Ordinal);
        Assert.Contains("Caused by: System.IO.FileNotFoundException", output, StringComparison.Ordinal);
    }

    [Fact]
    public void WriteFatalDiagnostics_KeepsTheOriginalMessageLineFirst()
    {
        // The existing line is what CI logs and issue reports already quote;
        // moving or dropping it would break the continuity of #735's record.
        var writer = new StringWriter();

        Program.WriteFatalDiagnostics(new FileNotFoundException(), writer);

        string first = writer.ToString()
            .Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries)[0];
        Assert.StartsWith("[ERR] Fatal error: ", first, StringComparison.Ordinal);
    }
}
