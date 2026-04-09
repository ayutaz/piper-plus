using System.Text.RegularExpressions;
using System.Xml.Linq;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace PiperPlus.Core.Ssml;

/// <summary>
/// Parser for a basic subset of SSML (Speech Synthesis Markup Language).
/// <para>
/// Supports:
/// <list type="bullet">
///   <item><c>&lt;speak&gt;</c> root element</item>
///   <item><c>&lt;break time="500ms"/&gt;</c> or <c>&lt;break time="1s"/&gt;</c> for silence</item>
///   <item><c>&lt;break strength="medium"/&gt;</c> for predefined silence durations</item>
///   <item><c>&lt;prosody rate="slow"&gt;text&lt;/prosody&gt;</c> for speech rate control</item>
/// </list>
/// </para>
/// <para>
/// Unknown tags are gracefully degraded by extracting their text content.
/// XML syntax errors cause a fallback to plain-text processing.
/// </para>
/// </summary>
public static partial class SsmlParser
{
    private static readonly ILogger Logger =
        NullLoggerFactory.Instance.CreateLogger("SsmlParser");

    /// <summary>
    /// Predefined break strength levels (W3C SSML spec) mapped to milliseconds.
    /// </summary>
    internal static readonly Dictionary<string, int> BreakStrengthMs = new(StringComparer.OrdinalIgnoreCase)
    {
        ["none"] = 0,
        ["x-weak"] = 100,
        ["weak"] = 200,
        ["medium"] = 400,
        ["strong"] = 700,
        ["x-strong"] = 1000,
    };

    /// <summary>
    /// Named prosody rate values mapped to length-scale multipliers.
    /// </summary>
    internal static readonly Dictionary<string, float> RateNames = new(StringComparer.OrdinalIgnoreCase)
    {
        ["x-slow"] = 1.5f,
        ["slow"] = 1.25f,
        ["medium"] = 1.0f,
        ["fast"] = 0.8f,
        ["x-fast"] = 0.6f,
    };

    // Regex: starts with optional whitespace then <speak followed by whitespace or >
    [GeneratedRegex(@"^\s*<speak[\s>]", RegexOptions.Singleline)]
    private static partial Regex SsmlDetectionRegex();

    // Regex for stripping XML tags in fallback path
    [GeneratedRegex(@"<[^>]*>")]
    private static partial Regex XmlTagRegex();

    /// <summary>
    /// Return <c>true</c> if <paramref name="text"/> looks like an SSML document.
    /// Detection is based on the presence of a <c>&lt;speak</c> opening tag
    /// near the start of the string.
    /// </summary>
    public static bool IsSsml(string text)
    {
        if (string.IsNullOrEmpty(text))
            return false;

        return SsmlDetectionRegex().IsMatch(text);
    }

    /// <summary>
    /// Parse an SSML string into a list of <see cref="SsmlSegment"/>.
    /// <para>
    /// If <paramref name="ssmlText"/> is not valid XML the entire string is
    /// returned as a single plain-text segment (graceful fallback).
    /// </para>
    /// </summary>
    /// <param name="ssmlText">SSML markup or plain text.</param>
    /// <returns>Ordered segments ready for phonemization.</returns>
    public static List<SsmlSegment> Parse(string ssmlText)
    {
        if (!IsSsml(ssmlText))
        {
            // Plain text -- return as a single segment.
            return [new SsmlSegment(ssmlText)];
        }

        XDocument doc;
        try
        {
            doc = XDocument.Parse(ssmlText);
        }
        catch (System.Xml.XmlException)
        {
            Logger.LogWarning(
                "SSML parse error; falling back to plain text: {Ssml}",
                ssmlText.Length > 120 ? ssmlText[..120] : ssmlText);

            // Strip XML tags heuristically so the user still gets audio output.
            var stripped = XmlTagRegex().Replace(ssmlText, "").Trim();
            return [new SsmlSegment(string.IsNullOrEmpty(stripped) ? ssmlText : stripped)];
        }

        if (doc.Root is null)
            return [new SsmlSegment(ssmlText)];

        var segments = new List<SsmlSegment>();
        Walk(doc.Root, rate: 1.0f, segments);

        var merged = Merge(segments);
        return merged.Count > 0 ? merged : [new SsmlSegment("")];
    }

    // ------------------------------------------------------------------
    // Internal helpers
    // ------------------------------------------------------------------

    /// <summary>
    /// Recursively walk the element tree and populate <paramref name="segments"/>.
    /// </summary>
    private static void Walk(XElement element, float rate, List<SsmlSegment> segments)
    {
        var tag = LocalTag(element.Name);

        if (tag == "break")
        {
            var breakMs = ResolveBreak(element);
            segments.Add(new SsmlSegment("", breakMs, rate));

            // Handle tail text after <break/> (content following in parent)
            // In XDocument model this is not directly on the element; handled by parent iteration.
            return;
        }

        // Determine rate for this scope
        if (tag == "prosody")
        {
            var rateAttr = (string?)element.Attribute("rate");
            if (rateAttr is not null)
                rate = ParseRate(rateAttr);
        }

        // Process mixed content: text nodes and child elements interleaved.
        // XElement nodes contain text as XText children and elements as XElement children,
        // accessible via element.Nodes() in document order.
        foreach (var node in element.Nodes())
        {
            switch (node)
            {
                case XText textNode:
                    {
                        var text = textNode.Value.Trim();
                        if (!string.IsNullOrEmpty(text))
                            segments.Add(new SsmlSegment(text, Rate: rate));
                        break;
                    }
                case XElement childElement:
                    Walk(childElement, rate, segments);
                    break;
            }
        }
    }

    /// <summary>
    /// Compute break duration in ms from a <c>&lt;break&gt;</c> element.
    /// </summary>
    private static int ResolveBreak(XElement element)
    {
        var timeAttr = (string?)element.Attribute("time");
        if (timeAttr is not null)
            return ParseBreakTime(timeAttr);

        var strengthAttr = (string?)element.Attribute("strength");
        if (strengthAttr is not null)
            return BreakStrengthMs.TryGetValue(strengthAttr, out var ms) ? ms : 400;

        // Default break with no attributes -> medium
        return BreakStrengthMs["medium"];
    }

    /// <summary>
    /// Convert <c>"500ms"</c> or <c>"1s"</c> to milliseconds.
    /// Returns 0 for unparseable values.
    /// </summary>
    internal static int ParseBreakTime(string timeStr)
    {
        timeStr = timeStr.Trim().ToLowerInvariant();

        if (timeStr.EndsWith("ms"))
        {
            return double.TryParse(timeStr[..^2], out var val) ? (int)val : 0;
        }

        if (timeStr.EndsWith("s"))
        {
            return double.TryParse(timeStr[..^1], out var val) ? (int)(val * 1000) : 0;
        }

        // Bare number -- assume milliseconds
        return double.TryParse(timeStr, out var bare) ? (int)bare : 0;
    }

    /// <summary>
    /// Convert a rate specification to a float multiplier.
    /// <para>
    /// Accepted formats:
    /// <list type="bullet">
    ///   <item>Named: <c>"slow"</c>, <c>"fast"</c>, etc.</item>
    ///   <item>Percentage: <c>"120%"</c> (120% speaking rate -> length_scale 0.833)</item>
    ///   <item>Bare float: treated as direct length_scale multiplier</item>
    /// </list>
    /// </para>
    /// The returned value is the length_scale multiplier: &gt; 1.0 is slower, &lt; 1.0 is faster.
    /// </summary>
    internal static float ParseRate(string rateStr)
    {
        rateStr = rateStr.Trim().ToLowerInvariant();

        // Named rate
        if (RateNames.TryGetValue(rateStr, out var named))
            return named;

        // Percentage
        if (rateStr.EndsWith('%'))
        {
            if (float.TryParse(rateStr[..^1], out var pct))
            {
                if (pct <= 0)
                {
                    Logger.LogWarning("Invalid rate percentage: {Rate}", rateStr);
                    return 1.0f;
                }
                // 120% speaking rate means faster -> length_scale = 100/120
                return 100.0f / pct;
            }

            Logger.LogWarning("Invalid rate percentage: {Rate}", rateStr);
            return 1.0f;
        }

        // Bare float (treat as direct multiplier for length_scale)
        if (float.TryParse(rateStr, out var val))
        {
            if (val <= 0)
            {
                Logger.LogWarning("Invalid rate value: {Rate}", rateStr);
                return 1.0f;
            }
            return val;
        }

        Logger.LogWarning("Unrecognized rate: {Rate}", rateStr);
        return 1.0f;
    }

    /// <summary>
    /// Strip XML namespace prefix if present.
    /// </summary>
    private static string LocalTag(XName name) => name.LocalName;

    /// <summary>
    /// Remove empty-text segments with zero break (no-ops).
    /// </summary>
    private static List<SsmlSegment> Merge(List<SsmlSegment> segments) =>
        segments.Where(s => !string.IsNullOrWhiteSpace(s.Text) || s.BreakMs > 0).ToList();
}
