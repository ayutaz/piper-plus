namespace PiperPlus.Core.Ssml;

/// <summary>
/// A segment produced by SSML parsing.
/// </summary>
/// <param name="Text">
/// Text to phonemize. Empty string indicates a silence-only segment.
/// </param>
/// <param name="BreakMs">
/// Silence duration in milliseconds to insert after this segment.
/// </param>
/// <param name="Rate">
/// Speech rate multiplier. Maps to <c>length_scale</c> at synthesis time.
/// Values &gt; 1.0 mean slower speech; values &lt; 1.0 mean faster speech.
/// </param>
public record SsmlSegment(string Text, int BreakMs = 0, float Rate = 1.0f);
