using PiperPlus.Core.Ssml;

namespace PiperPlus.Core.Tests.Ssml;

// =====================================================================
// Adversarial tests for PiperPlus.Core.Ssml.SsmlParser.
//
// These tests pin the *current* defensive behaviour against well-known
// XML attack vectors (XXE, billion-laughs, external DTD, processing
// instructions). The cases mirror analogous fixtures in the
// Python / Rust / Go runtimes so cross-runtime drift can be detected.
//
// Contract for each case:
//   1. The parser MUST NOT crash, segfault, OOM, or hang.
//   2. The parser MUST NOT expand external entities (file://, http:// ...).
//   3. Either the input is rejected by IsSsml() (DOCTYPE / xml prolog
//      precedes <speak>) and returned as a single plain-text segment,
//      OR XDocument.Parse throws XmlException, which the parser catches
//      and falls back to stripped plain text.
//
// The first line of defence is the IsSsml regex (^\s*<speak[\s>]). Any
// payload that prefixes a DOCTYPE / xml prolog / processing instruction
// fails the regex and bypasses XDocument.Parse entirely. Tests below
// cover both paths.
//
// XDocument.Parse default behaviour (.NET):
//   - DtdProcessing: tolerated (NOT Prohibit) — DOCTYPE is parsed.
//   - MaxCharactersFromEntities: 10_000_000 — billion laughs is capped.
//   - SYSTEM external IDs: not auto-fetched (no XmlResolver).
//   - Undeclared entity references: throw XmlException.
// =====================================================================

public class SsmlAttackXxeTests
{
    private static string AllText(IEnumerable<SsmlSegment> segments) =>
        string.Join(" ", segments.Select(s => s.Text));

    [Fact]
    public void XxeExternalEntity_Blocked()
    {
        // Standard XXE payload: DOCTYPE with SYSTEM file:// entity, then <speak>.
        var payload =
            "<?xml version=\"1.0\"?>" +
            "<!DOCTYPE foo [<!ENTITY xxe SYSTEM \"file:///etc/passwd\">]>" +
            "<speak>&xxe;</speak>";

        var segments = SsmlParser.Parse(payload);
        Assert.NotEmpty(segments);

        // No /etc/passwd content should leak into any segment.
        var full = AllText(segments);
        Assert.DoesNotContain("root:", full);
        Assert.DoesNotContain("/bin/bash", full);
        Assert.DoesNotContain("/bin/sh", full);
    }

    [Fact]
    public void XxeDoctypeOnly_NoXmlProlog_Blocked()
    {
        // DOCTYPE without xml prolog: same protection.
        var payload =
            "<!DOCTYPE foo [<!ENTITY xxe SYSTEM \"file:///etc/passwd\">]>" +
            "<speak>&xxe;</speak>";

        var segments = SsmlParser.Parse(payload);
        Assert.NotEmpty(segments);

        var full = AllText(segments);
        Assert.DoesNotContain("root:", full);
    }

    [Fact]
    public void XxeSpeakFirst_UndeclaredEntity_FallsBackSafely()
    {
        // <speak> first with undeclared entity: XDocument.Parse throws
        // XmlException, the parser catches and falls back to stripped text.
        var payload = "<speak>&xxe;</speak>";

        var segments = SsmlParser.Parse(payload);
        Assert.NotEmpty(segments);

        var full = AllText(segments);
        Assert.DoesNotContain("root:", full);
        Assert.DoesNotContain("/etc/passwd", full);
        Assert.DoesNotContain("/bin/", full);
    }
}

public class SsmlAttackBillionLaughsTests
{
    private static string AllText(IEnumerable<SsmlSegment> segments) =>
        string.Join(" ", segments.Select(s => s.Text));

    private static string BuildBillionLaughs(int depth, int fanout)
    {
        var decls = new System.Text.StringBuilder();
        decls.Append("<!ENTITY lol \"lol\">");
        var prev = "lol";
        for (int d = 2; d <= depth; d++)
        {
            var kids = new System.Text.StringBuilder();
            for (int i = 0; i < fanout; i++)
                kids.Append('&').Append(prev).Append(';');
            var name = $"lol{d}";
            decls.Append("<!ENTITY ").Append(name).Append(" \"").Append(kids).Append("\">");
            prev = name;
        }
        return $"<!DOCTYPE lolz [{decls}]><speak>&{prev};</speak>";
    }

    [Fact]
    public void BillionLaughs_Bounded()
    {
        // 9-deep, fan-out 10. Naive expansion = 10^9 = 1B chars. .NET caps
        // at MaxCharactersFromEntities=10_000_000 by default, but our
        // first-line defence is the IsSsml regex which rejects DOCTYPE-
        // prefixed payloads before they reach XDocument.Parse.
        var payload = BuildBillionLaughs(depth: 9, fanout: 10);

        var sw = System.Diagnostics.Stopwatch.StartNew();
        var segments = SsmlParser.Parse(payload);
        sw.Stop();

        Assert.True(sw.Elapsed.TotalSeconds < 5,
            $"billion laughs took too long: {sw.Elapsed}");
        Assert.NotEmpty(segments);

        // No expansion can have occurred — output bounded relative to input.
        var full = AllText(segments);
        Assert.True(full.Length <= payload.Length * 2,
            $"output ballooned: input={payload.Length}, output={full.Length}");
    }
}

public class SsmlAttackDtdTests
{
    private static string AllText(IEnumerable<SsmlSegment> segments) =>
        string.Join(" ", segments.Select(s => s.Text));

    [Fact]
    public void ExternalDtd_NotFetched()
    {
        // XDocument.Parse does not have an XmlResolver set by default,
        // so external SYSTEM IDs are not auto-fetched. The IsSsml regex
        // also rejects DOCTYPE-prefixed input as a first defence.
        var payload =
            "<!DOCTYPE speak SYSTEM \"http://example.invalid/external.dtd\">" +
            "<speak>Hello</speak>";

        var sw = System.Diagnostics.Stopwatch.StartNew();
        var segments = SsmlParser.Parse(payload);
        sw.Stop();

        // No network fetch — must complete fast.
        Assert.True(sw.ElapsedMilliseconds < 1000);
        Assert.NotEmpty(segments);

        var full = AllText(segments);
        // "Hello" should be reachable (parsed or in fallback plain text).
        Assert.True(full.Contains("Hello") || full.Contains("speak"));
    }

    [Fact]
    public void ExternalDtdWithXmlProlog_NotFetched()
    {
        var payload =
            "<?xml version=\"1.0\"?>" +
            "<!DOCTYPE speak SYSTEM \"http://example.invalid/external.dtd\">" +
            "<speak>Hello</speak>";

        var segments = SsmlParser.Parse(payload);
        Assert.NotEmpty(segments);
    }
}

public class SsmlAttackProcessingInstructionTests
{
    private static string AllText(IEnumerable<SsmlSegment> segments) =>
        string.Join(" ", segments.Select(s => s.Text));

    [Fact]
    public void XmlStylesheetPi_Ignored()
    {
        // <?xml-stylesheet?> must not trigger any XSL fetching. The
        // IsSsml regex rejects input that starts with `<?` (not <speak).
        var payload =
            "<?xml-stylesheet type=\"text/xsl\" href=\"evil.xsl\"?>" +
            "<speak>Hello</speak>";

        var sw = System.Diagnostics.Stopwatch.StartNew();
        var segments = SsmlParser.Parse(payload);
        sw.Stop();

        Assert.True(sw.ElapsedMilliseconds < 1000);
        Assert.NotEmpty(segments);

        var full = AllText(segments);
        Assert.Contains("Hello", full);
    }
}

public class SsmlAttackAttributeEntityTests
{
    private static string AllText(IEnumerable<SsmlSegment> segments) =>
        string.Join(" ", segments.Select(s => s.Text));

    [Fact]
    public void AttributeWithAmpEntity_DoesNotCrash()
    {
        // &amp; is a predefined entity (always valid).
        var payload = "<speak><break time=\"&amp;500ms\"/></speak>";

        // Should not crash. The attr value resolves to "&500ms" which
        // the break-time parser rejects as invalid (-> 0ms), filtered
        // out by Merge. We only assert no exception escapes.
        var segments = SsmlParser.Parse(payload);
        Assert.NotNull(segments);
    }

    [Fact]
    public void AttributeWithUndeclaredEntity_FallsBackSafely()
    {
        // <speak> first; undeclared entity in attr triggers XmlException;
        // the parser catches and falls back to stripped text.
        var payload = "<speak><break time=\"&xxe;\"/></speak>";

        var segments = SsmlParser.Parse(payload);
        Assert.NotEmpty(segments);

        var full = AllText(segments);
        Assert.DoesNotContain("root:", full);
        Assert.DoesNotContain("/etc/passwd", full);
    }

    [Fact]
    public void AttributeWithXxeEntity_DoctypePrefix_FallsBackSafely()
    {
        // DOCTYPE+entity in attribute. IsSsml rejects → plain text.
        var payload =
            "<!DOCTYPE foo [<!ENTITY xxe SYSTEM \"file:///etc/passwd\">]>" +
            "<speak><break time=\"&xxe;\"/></speak>";

        var segments = SsmlParser.Parse(payload);
        Assert.NotEmpty(segments);

        var full = AllText(segments);
        Assert.DoesNotContain("root:", full);
    }
}

public class SsmlAttackDriftSentinelTests
{
    [Fact]
    public void DoctypePrefix_TreatedAsPlainText()
    {
        // The IsSsml regex (^\s*<speak[\s>]) is identical across all
        // four runtimes. If this test changes, double-check Python /
        // Rust / Go analogues for drift.
        var cases = new[]
        {
            "<!DOCTYPE speak><speak>Hi</speak>",
            "<!DOCTYPE foo [<!ENTITY x 'y'>]><speak>Hi</speak>",
            "<?xml version='1.0'?><speak>Hi</speak>",
            "<?xml-stylesheet href='x.xsl'?><speak>Hi</speak>",
        };
        foreach (var payload in cases)
        {
            Assert.False(SsmlParser.IsSsml(payload),
                $"unexpected IsSsml=true for {payload}");
            var segments = SsmlParser.Parse(payload);
            Assert.Single(segments);
            Assert.Equal(payload, segments[0].Text);
        }
    }
}
