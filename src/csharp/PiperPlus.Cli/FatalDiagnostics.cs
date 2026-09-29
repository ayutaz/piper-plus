// Fatal-error diagnostics for the CLI's top-level catch.
//
// In its own file, not in Program.cs, so PiperPlus.Cli.Tests can source-link
// it. Program.cs cannot be source-linked: its Main would collide with the
// test host's entry point. Source-linking is the pattern this test project
// already uses for DotNetG2PEngine, and it keeps the method `internal`
// instead of widening the CLI's API surface.

using System;
using System.IO;

namespace PiperPlus.Cli;

internal static partial class Program
{
    /// <summary>
    /// Writes a fatal exception's type, missing-file name, stack trace and
    /// inner-exception chain, not just its message.
    /// </summary>
    /// <remarks>
    /// Issue #735: `--version` intermittently exits 1 in CI with
    /// <c>[ERR] Fatal error: Unable to find the specified file.</c> -- the
    /// parameterless <see cref="System.IO.FileNotFoundException"/> message,
    /// which names no file. With only <c>ex.Message</c> there is no way to
    /// tell WHICH file, nor whether the throw happened in
    /// <see cref="BuildRootCommand"/> or inside <c>Parse()</c>/<c>Invoke()</c>.
    /// The failure is rare, so the next occurrence has to carry both or the
    /// wait starts over.
    ///
    /// <para>
    /// <c>internal</c> and taking a <see cref="TextWriter"/> so
    /// PiperPlus.Cli.Tests can assert the format. Left inline in
    /// <c>Main</c>'s catch it would have been unreachable from any test --
    /// the same defect class as issue #703.
    /// </para>
    /// </remarks>
    internal static void WriteFatalDiagnostics(Exception ex, TextWriter output)
    {
        ArgumentNullException.ThrowIfNull(ex);
        ArgumentNullException.ThrowIfNull(output);

        output.WriteLine($"[ERR] Fatal error: {ex.Message}");
        output.WriteLine($"[ERR] Exception type: {ex.GetType().FullName}");

        // FileNotFoundException.FileName is the whole point here: the
        // parameterless message does not include it.
        if (ex is System.IO.FileNotFoundException fnf
            && !string.IsNullOrEmpty(fnf.FileName))
        {
            output.WriteLine($"[ERR] Missing file: {fnf.FileName}");
        }

        output.WriteLine($"[ERR] Stack trace:{Environment.NewLine}{ex.StackTrace}");

        for (Exception? inner = ex.InnerException;
             inner is not null;
             inner = inner.InnerException)
        {
            output.WriteLine(
                $"[ERR] Caused by: {inner.GetType().FullName}: {inner.Message}");
        }
    }
}
