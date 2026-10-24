using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// English G2P engine implementing <see cref="IEnglishG2PEngine"/>: g2p_en's
/// text normalization, the CMU dictionary and fallbacks for words missing
/// from it.
/// <para>
/// A port of the English G2P of the other runtimes (Rust
/// <c>src/rust/piper-plus-g2p/src/english.rs</c>, Go
/// <c>src/go/phonemize/english.go</c>, C++ <c>english_phonemize.cpp</c>),
/// which follow Python's <c>src/python/g2p/piper_plus_g2p/english.py</c>:
/// <list type="number">
///   <item>Normalize and tokenize the text like g2p_en
///         (<see cref="EnglishTextNormalizer"/>: numbers spelled out, accents
///         stripped, <c>i.e.</c> / <c>e.g.</c> expanded, nltk
///         <c>TweetTokenizer</c>).</item>
///   <item>Look up each word in the CMU dictionary, then its stem with a
///         common suffix (-ing, -ed, -s/-es/-ies, -er, -ly/-ily, -est)
///         removed.</item>
///   <item>Python reads the remaining words with g2p_en's neural guesser,
///         which is not ported. Such a word is split at <c>-</c> / <c>.</c>,
///         retried without apostrophes, split at CamelCase boundaries, and
///         finally spelled letter by letter, so no word is dropped.</item>
/// </list>
/// </para>
/// <para>
/// The output follows the <see cref="IEnglishG2PEngine"/> conventions: one
/// group of ARPAbet tokens per word, and a word without a letter (<c>,</c>
/// <c>.</c> <c>'</c> <c>-</c> <c>...</c>) as a group of itself, which
/// <see cref="EnglishPhonemizer"/> emits one character per phoneme as Python
/// does. ARPAbet to IPA, stress and prosody are left to
/// <see cref="EnglishPhonemizer"/>.
/// </para>
/// <para>
/// The dictionary is the shared <c>cmudict_data.json</c>
/// (<c>{"hello": "HH AH0 L OW1"}</c>, canonical copy in
/// <c>src/rust/piper-plus-g2p/data</c>); load it with <see cref="FromJson"/>.
/// The engine is immutable and safe to share between threads.
/// </para>
/// </summary>
public sealed class EnglishG2PEngine : IEnglishG2PEngine
{
    private static readonly char[] WordSeparators = ['-', '.'];

    private readonly IReadOnlyDictionary<string, string> _dictionary;

    /// <summary>
    /// Initializes a new instance of the <see cref="EnglishG2PEngine"/> class.
    /// </summary>
    /// <param name="dictionary">
    /// Lowercase word to space-separated ARPAbet (<c>"HH AH0 L OW1"</c>).
    /// </param>
    public EnglishG2PEngine(IReadOnlyDictionary<string, string> dictionary)
    {
        _dictionary = dictionary ?? throw new ArgumentNullException(nameof(dictionary));
    }

    /// <summary>
    /// Load the CMU dictionary from its JSON form,
    /// <c>{"hello": "HH AH0 L OW1"}</c>. Entries whose value is not a string
    /// are skipped.
    /// </summary>
    /// <param name="dictionary">Stream of <c>cmudict_data.json</c>.</param>
    /// <returns>The engine.</returns>
    public static EnglishG2PEngine FromJson(Stream dictionary)
    {
        ArgumentNullException.ThrowIfNull(dictionary);

        using JsonDocument doc = JsonDocument.Parse(dictionary);
        var entries = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (JsonProperty entry in doc.RootElement.EnumerateObject())
        {
            if (entry.Value.ValueKind == JsonValueKind.String)
            {
                entries[entry.Name] = entry.Value.GetString()!;
            }
        }

        return new EnglishG2PEngine(entries);
    }

    /// <inheritdoc />
    public List<List<string>> ConvertToArpabet(string text)
    {
        ArgumentNullException.ThrowIfNull(text);

        var result = new List<List<string>>();
        foreach (string word in EnglishTextNormalizer.NormalizeAndTokenize(text))
        {
            if (!HasLetter(word))
            {
                // Punctuation and other symbols are kept as they are.
                result.Add([word]);
            }
            else if (WordArpabet(word) is { } arpabet)
            {
                result.Add([.. arpabet.Split(' ', StringSplitOptions.RemoveEmptyEntries)]);
            }
        }

        return result;
    }

    private static bool HasLetter(string word)
    {
        foreach (char ch in word)
        {
            if (char.IsAsciiLetter(ch))
            {
                return true;
            }
        }

        return false;
    }

    // =================================================================
    // Words missing from the dictionary
    // =================================================================

    /// <summary>The dictionary entry of <paramref name="word"/>, or of its stem (morphological fallback).</summary>
    private string? Lookup(string word)
    {
        string lower = word.ToLowerInvariant();
        return _dictionary.TryGetValue(lower, out string? arpabet) ? arpabet : MorphologicalFallback(lower);
    }

    /// <summary>
    /// ARPAbet for a word; never <c>null</c> when the word has a letter. A word
    /// missing from the dictionary is split at <c>-</c> and <c>.</c>, retried
    /// without apostrophes, split at CamelCase boundaries, and finally spelled
    /// letter by letter. The parts are joined into one word.
    /// </summary>
    private string? WordArpabet(string word)
    {
        if (Lookup(word) is { } arpabet)
        {
            return arpabet;
        }

        if (word.AsSpan().IndexOfAny(WordSeparators) >= 0)
        {
            return Join(word.Split(WordSeparators, StringSplitOptions.RemoveEmptyEntries));
        }

        if (word.Contains('\'', StringComparison.Ordinal))
        {
            return WordArpabet(word.Replace("'", string.Empty, StringComparison.Ordinal));
        }

        List<string> parts = SplitCamelCase(word);
        if (parts.Count > 1)
        {
            return Join(parts);
        }

        var spelled = new List<string>(word.Length);
        foreach (char ch in word)
        {
            if (LetterNameArpabet(ch) is { } name)
            {
                spelled.Add(name);
            }
        }

        return spelled.Count > 0 ? string.Join(' ', spelled) : null;
    }

    private string? Join(IEnumerable<string> parts)
    {
        var arpabets = new List<string>();
        foreach (string part in parts)
        {
            if (WordArpabet(part) is { } arpabet)
            {
                arpabets.Add(arpabet);
            }
        }

        return arpabets.Count > 0 ? string.Join(' ', arpabets) : null;
    }

    /// <summary>The name of a letter, used to spell words that cannot be read otherwise.</summary>
    private static string? LetterNameArpabet(char ch) => char.ToLowerInvariant(ch) switch
    {
        'a' => "EY1",
        'b' => "B IY1",
        'c' => "S IY1",
        'd' => "D IY1",
        'e' => "IY1",
        'f' => "EH1 F",
        'g' => "JH IY1",
        'h' => "EY1 CH",
        'i' => "AY1",
        'j' => "JH EY1",
        'k' => "K EY1",
        'l' => "EH1 L",
        'm' => "EH1 M",
        'n' => "EH1 N",
        'o' => "OW1",
        'p' => "P IY1",
        'q' => "K Y UW1",
        'r' => "AA1 R",
        's' => "EH1 S",
        't' => "T IY1",
        'u' => "Y UW1",
        'v' => "V IY1",
        'w' => "D AH1 B AH0 L Y UW0",
        'x' => "EH1 K S",
        'y' => "W AY1",
        'z' => "Z IY1",
        _ => null,
    };

    /// <summary>
    /// Splits a word at CamelCase boundaries, like Python
    /// <c>re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+", word)</c>:
    /// <c>ChatGPT</c> → <c>Chat</c> + <c>GPT</c>, <c>HTMLParser</c> →
    /// <c>HTML</c> + <c>Parser</c>.
    /// </summary>
    /// <param name="word">An ASCII word.</param>
    /// <returns>The parts; characters other than ASCII letters are dropped.</returns>
    internal static List<string> SplitCamelCase(string word)
    {
        int RunEnd(int from, Func<char, bool> predicate)
        {
            int j = from;
            while (j < word.Length && predicate(word[j]))
            {
                j++;
            }

            return j;
        }

        var parts = new List<string>();
        int i = 0;
        while (i < word.Length)
        {
            if (char.IsAsciiLetterUpper(word[i]))
            {
                int upperEnd = RunEnd(i, char.IsAsciiLetterUpper);
                bool lowerFollows = upperEnd < word.Length && char.IsAsciiLetterLower(word[upperEnd]);
                if (lowerFollows && upperEnd - i >= 2)
                {
                    // The last capital starts the next part.
                    parts.Add(word[i..(upperEnd - 1)]);
                    i = upperEnd - 1;
                }
                else if (lowerFollows)
                {
                    int end = RunEnd(upperEnd, char.IsAsciiLetterLower);
                    parts.Add(word[i..end]);
                    i = end;
                }
                else
                {
                    parts.Add(word[i..upperEnd]);
                    i = upperEnd;
                }
            }
            else if (char.IsAsciiLetterLower(word[i]))
            {
                int end = RunEnd(i, char.IsAsciiLetterLower);
                parts.Add(word[i..end]);
                i = end;
            }
            else
            {
                i++;
            }
        }

        return parts;
    }

    // =================================================================
    // Morphological fallback (C++ tryMorphologicalFallback)
    // =================================================================

    /// <summary>
    /// Strips a common English suffix and looks up the base form. Returns the
    /// base ARPAbet with the suffix phonemes appended, or <c>null</c>.
    /// Supported suffixes: -ing, -ed, -s/-es/-ies, -er, -ly/-ily, -est.
    /// </summary>
    private string? MorphologicalFallback(string word)
    {
        int len = word.Length;

        string? TryBase(string stem, string suffixArpabet) =>
            _dictionary.TryGetValue(stem, out string? arpabet) ? arpabet + " " + suffixArpabet : null;

        // Doubled final consonant: sitting -> sit, stopped -> stop, runner -> run.
        string? TryUndoubled(string stem, string suffixArpabet) =>
            stem.Length >= 2 && stem[^1] == stem[^2] ? TryBase(stem[..^1], suffixArpabet) : null;

        // ----- -ing (running->run, making->make, sitting->sit) -----
        if (len > 4 && word.EndsWith("ing", StringComparison.Ordinal))
        {
            string stem = word[..^3];
            if ((TryBase(stem, "IH0 NG") ?? TryUndoubled(stem, "IH0 NG") ?? TryBase(stem + "e", "IH0 NG")) is { } r)
            {
                return r;
            }
        }

        // ----- -ed (walked->walk, stopped->stop, loved->love) -----
        if (len > 3 && word.EndsWith("ed", StringComparison.Ordinal))
        {
            string stem = word[..^2];
            if ((TryBase(stem, "D") ?? TryUndoubled(stem, "D") ?? TryBase(word[..^1], "D")) is { } r)
            {
                return r;
            }
        }

        // ----- -s / -es / -ies (cats->cat, boxes->box, countries->country) -----
        if (len > 2 && word.EndsWith('s'))
        {
            if (len > 4 && word.EndsWith("ies", StringComparison.Ordinal) && TryBase(word[..^3] + "y", "Z") is { } ies)
            {
                return ies;
            }

            if (len > 3 && word.EndsWith("es", StringComparison.Ordinal) && TryBase(word[..^2], "IH0 Z") is { } es)
            {
                return es;
            }

            if (TryBase(word[..^1], "Z") is { } s)
            {
                return s;
            }
        }

        // ----- -er (faster->fast, runner->run) -----
        if (len > 3 && word.EndsWith("er", StringComparison.Ordinal))
        {
            string stem = word[..^2];
            if ((TryBase(stem, "ER0") ?? TryUndoubled(stem, "ER0")) is { } r)
            {
                return r;
            }
        }

        // ----- -ly / -ily (quickly->quick, happily->happy) -----
        if (len > 3 && word.EndsWith("ly", StringComparison.Ordinal))
        {
            if (TryBase(word[..^2], "L IY0") is { } ly)
            {
                return ly;
            }

            if (len > 4 && word[len - 3] == 'i' && TryBase(word[..^3] + "y", "L IY0") is { } ily)
            {
                return ily;
            }
        }

        // ----- -est (fastest->fast) -----
        if (len > 4 && word.EndsWith("est", StringComparison.Ordinal))
        {
            return TryBase(word[..^3], "AH0 S T");
        }

        return null; // Truly OOV
    }
}
