namespace PiperPlus.Core.Tests;

// Changing cwd affects the entire test host. Run this collection without any
// other collections, then always restore cwd before reporting assertions.
[CollectionDefinition(nameof(ProcessWorkingDirectoryCollection), DisableParallelization = true)]
public sealed class ProcessWorkingDirectoryCollection
{
}

[Collection(nameof(ProcessWorkingDirectoryCollection))]
public sealed class CliWorkingDirectoryTests
{
    [Fact]
    [Trait("Category", "CLI")]
    public async Task Version_FromDeletedParentDirectory_Succeeds()
    {
        if (!OperatingSystem.IsLinux())
        {
            Assert.Skip("The Linux getcwd/ENOENT regression requires unlinking the current directory.");
        }

        string originalDirectory = Directory.GetCurrentDirectory();
        string doomedDirectory = Path.Combine(Path.GetTempPath(), $"piper-cwd-{Guid.NewGuid():N}");
        Directory.CreateDirectory(doomedDirectory);
        (int ExitCode, string StdOut, string StdErr) result;
        try
        {
            Directory.SetCurrentDirectory(doomedDirectory);
            Directory.Delete(doomedDirectory);

            // Use the same launcher as every CLI integration test. The CLI
            // must not inherit the parent's now-unlinked working directory.
            result = await CliIntegrationTests.RunCliAsync("--version");
        }
        finally
        {
            Directory.SetCurrentDirectory(originalDirectory);
            if (Directory.Exists(doomedDirectory))
            {
                Directory.Delete(doomedDirectory);
            }
        }

        Assert.True(
            result.ExitCode == 0,
            $"CLI failed from a deleted parent cwd. stdout={result.StdOut}; stderr={result.StdErr}");
        Assert.Matches(@"\d+\.\d+\.\d+", result.StdOut);
        Assert.DoesNotContain("Fatal error", result.StdErr, StringComparison.OrdinalIgnoreCase);
    }
}
