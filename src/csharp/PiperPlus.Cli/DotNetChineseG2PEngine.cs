using PiperPlus.Core.Phonemize;
using DotNetG2P.Chinese;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="ChineseG2PEngine"/> from the DotNetG2P.Chinese
/// NuGet package to implement <see cref="IChineseG2PEngine"/>.
/// </summary>
internal sealed class DotNetChineseG2PEngine : IChineseG2PEngine
{
    private readonly ChineseG2PEngine _engine = new();

    public ChineseG2PResult Convert(string text)
    {
        var result = _engine.ToIpaWithProsody(text);

        // DotNetG2P returns a paired (Phonemes, Prosody) structure where
        // Prosody is IReadOnlyList<ChineseProsodyInfo>.  Flatten into the
        // separate A1/A2/A3 arrays that piper-plus expects.
        int count = result.Phonemes.Count;
        var a1 = new int[count];
        var a2 = new int[count];
        var a3 = new int[count];

        for (int i = 0; i < count; i++)
        {
            var p = result.Prosody[i];
            a1[i] = p.A1;
            a2[i] = p.A2;
            a3[i] = p.A3;
        }

        return new ChineseG2PResult(
            Phonemes: result.Phonemes,
            A1: a1,
            A2: a2,
            A3: a3);
    }
}
