// --text mode phonemizer selection for the CLI.
//
// In its own file, not in Program.cs, so PiperPlus.Cli.Tests can source-link
// it and compare the phonemes a CLI user gets with the Python golden
// (G2pGoldenParityTests). Program.cs cannot be source-linked: its Main would
// collide with the test host's entry point. Same pattern as FatalDiagnostics.cs.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Cli;

internal static partial class Program
{
    /// <summary>
    /// Resolve an <see cref="IPhonemizer"/> for the given language in --text mode.
    /// <para>
    /// Currently supported languages:
    /// <list type="bullet">
    ///   <item><c>ja</c> — Japanese (requires <c>JapanesePhonemizer</c> + <c>IJapaneseG2PEngine</c>)</item>
    ///   <item><c>en</c> — English (requires <c>EnglishPhonemizer</c> + <c>IEnglishG2PEngine</c>)</item>
    ///   <item><c>zh</c> — Chinese (requires <c>ChinesePhonemizer</c> + <c>BundledChineseG2PEngine</c>,
    ///         and the English phonemizer for embedded English letters)</item>
    ///   <item><c>es</c> — Spanish (requires <c>SpanishPhonemizer</c> + <c>DotNetSpanishG2PEngine</c>)</item>
    ///   <item><c>fr</c> — French (requires <c>FrenchPhonemizer</c> + <c>FrenchG2PEngine</c>)</item>
    ///   <item><c>pt</c> — Portuguese (requires <c>PortuguesePhonemizer</c> + <c>DotNetPortugueseG2PEngine</c>)</item>
    ///   <item>Combined codes (e.g. <c>ja-en-zh-es-fr-pt</c>) — returns a
    ///         <see cref="MultilingualPhonemizer"/> that auto-detects language per segment.</item>
    /// </list>
    /// </para>
    /// </summary>
    /// <param name="language">Language code.</param>
    /// <returns>An <see cref="IPhonemizer"/> instance.</returns>
    /// <exception cref="NotSupportedException">When the language or its dependencies are unavailable.</exception>
    [RequiresUnreferencedCode(
        "G2P engine types are resolved via reflection. When publishing trimmed, " +
        "ensure DotNetG2PEngine/DotNetEnglishG2PEngine are preserved.")]
    internal static IPhonemizer ResolveTextModePhonemizer(string language)
    {
        // Multi-language code: "ja-en", "ja-en-zh-es-fr-pt", etc.
        if (language.Contains('-'))
        {
            var parts = language.Split('-');
            var phonemizers = new Dictionary<string, IPhonemizer>();
            foreach (var part in parts)
            {
                // MultilingualPhonemizer rewrites the CJK punctuation of Latin
                // segments itself, so it gets the plain phonemizers.
                phonemizers[part] = ResolveSingleLanguagePhonemizer(part);
            }

            // Determine default Latin language (prefer en, then es, pt, fr)
            string defaultLatin = "en";
            foreach (var lat in new[] { "en", "es", "pt", "fr", "sv" })
            {
                if (phonemizers.ContainsKey(lat))
                {
                    defaultLatin = lat;
                    break;
                }
            }

            return new MultilingualPhonemizer(phonemizers, defaultLatin);
        }

        // A single language goes through MultilingualPhonemizer with that
        // language as the Latin default, as Python's golden does, so that
        // English letters in a Chinese sentence get the ZH-EN loanword reading
        // (Issue #384, #833) and CJK punctuation in Latin text is read as
        // ASCII (Issue #823, docs/spec/cjk-punctuation-contract.toml).
        // Chinese registers en next to it: the letters are read as pinyin when
        // they touch Chinese text and as English otherwise. Japanese and Korean
        // read the whole text themselves.
        return language switch
        {
            "zh" => new MultilingualPhonemizer(
                new Dictionary<string, IPhonemizer>
                {
                    ["zh"] = ResolveSingleLanguagePhonemizer("zh"),
                    ["en"] = ResolveSingleLanguagePhonemizer("en"),
                },
                "en"),
            "en" or "es" or "fr" or "pt" or "sv" => new MultilingualPhonemizer(
                new Dictionary<string, IPhonemizer> { [language] = ResolveSingleLanguagePhonemizer(language) },
                language),
            _ => ResolveSingleLanguagePhonemizer(language),
        };
    }

    [RequiresUnreferencedCode(
        "G2P engine types are resolved via reflection. When publishing trimmed, " +
        "ensure DotNetG2PEngine/DotNetEnglishG2PEngine are preserved.")]
    private static IPhonemizer ResolveSingleLanguagePhonemizer(string language)
    {
        switch (language)
        {
            case "ja":
                return new JapanesePhonemizer(new DotNetG2PEngine());

            case "en":
                return new EnglishPhonemizer(new DotNetEnglishG2PEngine());

            case "zh":
                return new ChinesePhonemizer(new BundledChineseG2PEngine());

            case "ko":
                return new KoreanPhonemizer(new DotNetKoreanG2PEngine());

            case "es":
                return new SpanishPhonemizer(new DotNetSpanishG2PEngine());

            case "fr":
                return new FrenchPhonemizer(new FrenchG2PEngine());

            case "pt":
                return new PortuguesePhonemizer(new DotNetPortugueseG2PEngine());

            case "sv":
                return new SwedishPhonemizer(new DotNetSwedishG2PEngine());

            default:
                throw new NotSupportedException(
                    $"Unsupported language for --text mode: {language}. " +
                    "Supported languages: ja, en, zh, ko, es, fr, pt, sv, or combined (e.g. ja-en-zh-ko-es-fr-pt).");
        }
    }
}
