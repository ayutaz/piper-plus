using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// English text normalization, ported from Python's g2p_en.
/// <para>
/// Python's English G2P (<c>g2p_en.G2p.__call__</c>) rewrites the text before
/// its dictionary lookup. This class ports those steps, 1:1 with the Rust
/// <c>english_normalize.rs</c> and the Go <c>english_normalize.go</c>, so
/// <see cref="EnglishG2PEngine"/> sees the same words:
/// <list type="number">
///   <item><see cref="NormalizeNumbers"/> spells numbers out the way inflect
///         does (<c>123</c> → <c>one hundred twenty-three</c>, <c>1984</c> →
///         <c>nineteen eighty-four</c>, <c>$5</c> → <c>five dollars</c>,
///         <c>2nd</c> → <c>second</c>);</item>
///   <item>accents are stripped (NFD, combining marks removed);</item>
///   <item>every character other than <c>a-z A-Z ' . , ? ! -</c> and the
///         ASCII space is removed;</item>
///   <item><c>i.e.</c> / <c>e.g.</c> become <c>that is</c> / <c>for example</c>
///         (ignoring case);</item>
///   <item>the subset of nltk's <c>TweetTokenizer</c> that this character set
///         can reach splits the text into words.</item>
/// </list>
/// </para>
/// <para>
/// Python lowercases at step 2; the port keeps the case because the fallback
/// for words missing from the dictionary splits CamelCase words. Unlike
/// g2p_en, any whitespace becomes a space instead of being removed, as in the
/// other ports (see <see cref="StripAccentsAndFilter"/>).
/// <c>EnglishNormalizeTests</c> checks both steps against
/// <c>tests/fixtures/g2p/english_normalize_cases.json</c>, generated from
/// Python.
/// </para>
/// </summary>
internal static partial class EnglishTextNormalizer
{
    // =================================================================
    // Number expansion (g2p_en expand.py + inflect number_to_words)
    // =================================================================
    [GeneratedRegex("([0-9][0-9,]+[0-9])", RegexOptions.CultureInvariant)]
    private static partial Regex CommaNumberRegex();

    [GeneratedRegex("£([0-9,]*[0-9]+)", RegexOptions.CultureInvariant)]
    private static partial Regex PoundsRegex();

    [GeneratedRegex(@"\$([0-9.,]*[0-9]+)", RegexOptions.CultureInvariant)]
    private static partial Regex DollarsRegex();

    [GeneratedRegex(@"([0-9]+\.[0-9]+)", RegexOptions.CultureInvariant)]
    private static partial Regex DecimalNumberRegex();

    [GeneratedRegex("[0-9]+(st|nd|rd|th)", RegexOptions.CultureInvariant)]
    private static partial Regex OrdinalRegex();

    [GeneratedRegex("[0-9]+", RegexOptions.CultureInvariant)]
    private static partial Regex NumberRegex();

    // inflect's post-processing of the joined groups.
    [GeneratedRegex(@"\s+,", RegexOptions.CultureInvariant)]
    private static partial Regex WhitespacesCommaRegex();

    [GeneratedRegex(@", (\S+)\s+\z", RegexOptions.CultureInvariant)]
    private static partial Regex CommaWordRegex();

    [GeneratedRegex(@"\s+", RegexOptions.CultureInvariant)]
    private static partial Regex WhitespacesRegex();

    private static readonly string[] Unit =
        [string.Empty, "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];

    private static readonly string[] Teen =
        ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"];

    private static readonly string[] Ten =
        [string.Empty, string.Empty, "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];

    /// <summary>
    /// Group scales. inflect goes on to decillion; the port stops at
    /// quintillion and reads longer digit runs digit by digit.
    /// </summary>
    private static readonly string[] Mill =
        [" ", " thousand", " million", " billion", " trillion", " quadrillion", " quintillion"];

    private static readonly string[] DigitNames =
        ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];

    /// <summary>Ordinal endings, tried at the end of the last word (inflect <c>ordinal</c>).</summary>
    private static readonly (string Suffix, string Replacement)[] OrdinalSuffixes =
    [
        ("ty", "tieth"),
        ("one", "first"),
        ("two", "second"),
        ("three", "third"),
        ("five", "fifth"),
        ("eight", "eighth"),
        ("nine", "ninth"),
        ("twelve", "twelfth"),
    ];

    /// <summary>
    /// Expand numbers in <paramref name="text"/> to English words, like
    /// g2p_en's <c>normalize_numbers</c>. The regex substitutions run in
    /// Python's order.
    /// </summary>
    /// <param name="text">Input text.</param>
    /// <returns>The text with every digit run spelled out.</returns>
    public static string NormalizeNumbers(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        string s = CommaNumberRegex().Replace(text, m => m.Groups[1].Value.Replace(",", string.Empty, StringComparison.Ordinal));
        s = PoundsRegex().Replace(s, "$1 pounds");
        s = DollarsRegex().Replace(s, m => ExpandDollars(m.Groups[1].Value));
        s = DecimalNumberRegex().Replace(s, m => m.Groups[1].Value.Replace(".", " point ", StringComparison.Ordinal));
        s = OrdinalRegex().Replace(s, m => ExpandOrdinal(m.Value));
        return NumberRegex().Replace(s, m => ExpandNumber(m.Value));
    }

    /// <summary>
    /// The decimal digits of <paramref name="s"/> without leading zeros
    /// (<c>"0"</c> when there are none). Matches Python's <c>str(int(s))</c>;
    /// non-digits (a stray comma) are ignored.
    /// </summary>
    private static string CanonicalDigits(string s)
    {
        var digits = new StringBuilder(s.Length);
        foreach (char ch in s)
        {
            if (char.IsAsciiDigit(ch))
            {
                digits.Append(ch);
            }
        }

        string trimmed = digits.ToString().TrimStart('0');
        return trimmed.Length == 0 ? "0" : trimmed;
    }

    /// <summary><c>$D.C</c> → <c>D dollar(s), C cent(s)</c> (g2p_en <c>_expand_dollars</c>).</summary>
    private static string ExpandDollars(string amount)
    {
        string[] parts = amount.Split('.');
        if (parts.Length > 2)
        {
            return amount + " dollars"; // Unexpected format
        }

        string dollars = CanonicalDigits(parts[0]);
        string cents = CanonicalDigits(parts.Length > 1 ? parts[1] : string.Empty);
        string dollarUnit = dollars == "1" ? "dollar" : "dollars";
        string centUnit = cents == "1" ? "cent" : "cents";
        return (dollars != "0", cents != "0") switch
        {
            (true, true) => $"{dollars} {dollarUnit}, {cents} {centUnit}",
            (true, false) => $"{dollars} {dollarUnit}",
            (false, true) => $"{cents} {centUnit}",
            _ => "zero dollars",
        };
    }

    /// <summary><c>21st</c> → <c>twenty-first</c> (inflect <c>number_to_words</c> with an ordinal suffix).</summary>
    private static string ExpandOrdinal(string matched)
    {
        string digits = CanonicalDigits(matched[..^2]);
        return ToOrdinal(NumberWords(digits, "and"));
    }

    /// <summary>Cardinal numbers, read as years between 1001 and 2999 (g2p_en <c>_expand_number</c>).</summary>
    private static string ExpandNumber(string matched)
    {
        string digits = CanonicalDigits(matched);
        if (digits.Length == 4)
        {
            int n = int.Parse(digits, CultureInfo.InvariantCulture);
            if (n > 1000 && n < 3000)
            {
                return YearWords(n);
            }
        }

        return NumberWords(digits, string.Empty);
    }

    private static string YearWords(int n)
    {
        if (n == 2000)
        {
            return "two thousand";
        }

        if (n > 2000 && n < 2010)
        {
            return "two thousand " + NumberWords((n % 100).ToString(CultureInfo.InvariantCulture), "and");
        }

        if (n % 100 == 0)
        {
            return NumberWords((n / 100).ToString(CultureInfo.InvariantCulture), "and") + " hundred";
        }

        // inflect group=2 with zero="oh": two digits at a time.
        int low = n % 100;
        string lowWords = low < 10 ? "oh " + Unit[low] : TensWords(low / 10, low % 10, 0).TrimEnd();
        int high = n / 100;
        return $"{TensWords(high / 10, high % 10, 0).TrimEnd()} {lowWords}";
    }

    /// <summary>inflect <c>tenfn</c>: 0-99 followed by the scale of group <paramref name="mill"/>.</summary>
    private static string TensWords(int tens, int units, int mill)
    {
        if (tens == 1)
        {
            return Teen[units] + Mill[mill];
        }

        string hyphen = tens > 0 && units > 0 ? "-" : string.Empty;
        return Ten[tens] + hyphen + Unit[units] + Mill[mill];
    }

    /// <summary>inflect <c>hundfn</c>: one full group of three digits.</summary>
    private static string HundredsWords(int hundreds, int tens, int units, int mill, string and)
    {
        if (hundreds > 0)
        {
            string andWord = tens > 0 || units > 0 ? $" {and} " : string.Empty;
            return $"{Unit[hundreds]} hundred{andWord}{TensWords(tens, units, 0)}{Mill[mill]}, ";
        }

        if (tens > 0 || units > 0)
        {
            return $"{TensWords(tens, units, 0)}{Mill[mill]}, ";
        }

        return string.Empty;
    }

    /// <summary>
    /// inflect <c>number_to_words(digits, andword=and)</c> for a canonical
    /// digit string. Groups are joined with ", " except that a last group of
    /// 1-99 is joined with <paramref name="and"/> (" " when it is empty):
    /// <c>one million one</c>.
    /// </summary>
    private static string NumberWords(string digits, string and)
    {
        switch (digits)
        {
            case "0":
                return "zero";
            case "1":
                return "one";
        }

        int[] d = new int[digits.Length];
        for (int i = 0; i < digits.Length; i++)
        {
            d[i] = digits[i] - '0';
        }

        if (d.Length > 3 * Mill.Length)
        {
            // Beyond quintillion: read each digit.
            var names = new string[d.Length];
            for (int i = 0; i < d.Length; i++)
            {
                names[i] = DigitNames[d[i]];
            }

            return string.Join(' ', names);
        }

        int groups = d.Length / 3;
        int lead = d.Length % 3;
        var sb = new StringBuilder();
        if (lead == 2)
        {
            sb.Append(TensWords(d[0], d[1], groups)).Append(", ");
        }
        else if (lead == 1)
        {
            sb.Append(Unit[d[0]]).Append(Mill[groups]).Append(", ");
        }

        for (int g = 0; g < groups; g++)
        {
            int i = lead + (3 * g);
            sb.Append(HundredsWords(d[i], d[i + 1], d[i + 2], groups - 1 - g, and));
        }

        string s = sb.ToString();
        if (s.EndsWith(", ", StringComparison.Ordinal))
        {
            s = s[..^2];
        }

        s = WhitespacesCommaRegex().Replace(s, ",");
        s = CommaWordRegex().Replace(s, m => $" {and} {m.Groups[1].Value}", 1);
        return WhitespacesRegex().Replace(s, " ").Trim();
    }

    /// <summary>inflect <c>_sub_ord</c>: the ordinal of the last word.</summary>
    private static string ToOrdinal(string words)
    {
        foreach ((string suffix, string replacement) in OrdinalSuffixes)
        {
            if (words.EndsWith(suffix, StringComparison.Ordinal))
            {
                return words[..^suffix.Length] + replacement;
            }
        }

        return words + "th";
    }

    // =================================================================
    // Accent stripping and character filter
    // =================================================================

    /// <summary>
    /// Base letter of each code point in U+00C0..U+024F whose NFD form is an
    /// ASCII letter followed by combining marks; <c>-</c> where there is none.
    /// Generated with Python's <c>unicodedata</c> (same table as Rust).
    /// </summary>
    private const string LatinBase00C0 =
        "AAAAAA-CEEEEIIII-NOOOOO--UUUUY--aaaaaa-ceeeeiiii-nooooo--uuuuy-y"
        + "AaAaAaCcCcCcCcDd--EeEeEeEeEeGgGgGgGgHh--IiIiIiIiI---JjKk-LlLlLl-"
        + "---NnNnNn---OoOoOo--RrRrRrSsSsSsSsTtTt--UuUuUuUuUuUuWwYyYZzZzZz-"
        + "--------------------------------Oo-------------Uu---------------"
        + "-------------AaIiOoUuUuUuUuUu-AaAa----GgKkOoOo--j---Gg--NnAa----"
        + "AaAaEeEeIiIiOoOoRrRrUuUuSsTt--Hh------AaEeOoOoOoOoYy------------"
        + "----------------";

    /// <summary>The same for U+1E00..U+1EFF (Latin Extended Additional).</summary>
    private const string LatinBase1E00 =
        "AaBbBbBbCcDdDdDdDdDdEeEeEeEeEeFfGgHhHhHhHhHhIiIiKkKkKkLlLlLlLlMm"
        + "MmMmNnNnNnNnOoOoOoOoPpPpRrRrRrRrSsSsSsSsSsTtTtTtTtUuUuUuUuUuVvVv"
        + "WwWwWwWwWwXxXxYyZzZzZzhtwy------AaAaAaAaAaAaAaAaAaAaAaAaEeEeEeEe"
        + "EeEeEeEeIiIiOoOoOoOoOoOoOoOoOoOoOoOoUuUuUuUuUuUuUuYyYyYyYy------";

    /// <summary>
    /// The ASCII letter left after NFD and removing combining marks, for a
    /// non-ASCII character. Combining marks themselves and every other
    /// character give <c>null</c>: the character filter would remove them anyway.
    /// </summary>
    private static char? FoldAccent(char ch)
    {
        static char? FromTable(string table, int offset) =>
            offset < table.Length && table[offset] != '-' ? table[offset] : null;

        return ch switch
        {
            >= 'À' and <= 'ɏ' => FromTable(LatinBase00C0, ch - 'À'),
            >= 'Ḁ' and <= 'ỿ' => FromTable(LatinBase1E00, ch - 'Ḁ'),
            'K' => 'K', // KELVIN SIGN
            'Å' => 'A', // ANGSTROM SIGN
            _ => null,
        };
    }

    private static bool IsKept(char ch) =>
        char.IsAsciiLetter(ch) || ch is ' ' or '\'' or '.' or ',' or '?' or '!' or '-';

    /// <summary>
    /// Steps 2-3: strip accents and keep <c>a-z A-Z ' . , ? ! -</c> and the
    /// ASCII space. The result is ASCII. Unlike g2p_en, any whitespace (tab,
    /// newline, no-break space, ...) becomes a space instead of being removed:
    /// removing it joins the words around it, and Python reads the joined word
    /// with a neural predictor this port does not have.
    /// </summary>
    private static string StripAccentsAndFilter(string text)
    {
        var sb = new StringBuilder(text.Length);
        foreach (char ch in text)
        {
            char? c;
            if (char.IsWhiteSpace(ch))
            {
                c = ' ';
            }
            else
            {
                c = char.IsAscii(ch) ? ch : FoldAccent(ch);
            }

            if (c is { } kept && IsKept(kept))
            {
                sb.Append(kept);
            }
        }

        return sb.ToString();
    }

    /// <summary>
    /// Python's <c>str.replace</c> (left to right, non-overlapping), ignoring
    /// ASCII case. <paramref name="text"/> and <paramref name="pattern"/> are ASCII.
    /// </summary>
    private static string ReplaceIgnoreAsciiCase(string text, string pattern, string replacement)
    {
        var sb = new StringBuilder(text.Length);
        int i = 0;
        while (i < text.Length)
        {
            if (text.Length - i >= pattern.Length
                && text.AsSpan(i, pattern.Length).Equals(pattern, StringComparison.OrdinalIgnoreCase))
            {
                sb.Append(replacement);
                i += pattern.Length;
            }
            else
            {
                sb.Append(text[i]);
                i++;
            }
        }

        return sb.ToString();
    }

    // =================================================================
    // TweetTokenizer subset
    // =================================================================

    /// <summary>nltk <c>HANG_RE</c>: 4+ copies of a non-letter, non-digit character become 3.</summary>
    private static string ShortenHang(string text)
    {
        var sb = new StringBuilder(text.Length);
        int i = 0;
        while (i < text.Length)
        {
            char c = text[i];
            int j = i + 1;
            while (j < text.Length && text[j] == c)
            {
                j++;
            }

            int run = char.IsAsciiLetterOrDigit(c) ? j - i : Math.Min(j - i, 3);
            sb.Append(c, run);
            i = j;
        }

        return sb.ToString();
    }

    private static int LetterRunEnd(string b, int start)
    {
        int j = start;
        while (j < b.Length && char.IsAsciiLetter(b[j]))
        {
            j++;
        }

        return j;
    }

    /// <summary>
    /// Naked domain: <c>[a-z]+([.-][a-z]+){0,126}\.[a-z]{2,13}</c> not
    /// followed by a letter. Like the backtracking regex, it takes the most
    /// labels for which the next separator is '.' and the label after it has
    /// 2-13 letters.
    /// </summary>
    private static int? MatchDomain(string b, int start)
    {
        int pos = LetterRunEnd(b, start);
        if (pos == start)
        {
            return null;
        }

        // (separator, label start, label end) for each label after the first run.
        var labels = new List<(char Sep, int Start, int End)>();
        while (pos + 1 < b.Length && (b[pos] is '.' or '-') && char.IsAsciiLetter(b[pos + 1]))
        {
            int end = LetterRunEnd(b, pos + 1);
            labels.Add((b[pos], pos + 1, end));
            pos = end;
        }

        for (int k = Math.Min(labels.Count - 1, 126); k >= 0; k--)
        {
            (char sep, int s, int e) = labels[k];
            if (sep == '.' && e - s >= 2 && e - s <= 13)
            {
                return e;
            }
        }

        return null;
    }

    /// <summary>Word with apostrophes or dashes: <c>[a-z]([a-z]|['-])+[a-z]</c>.</summary>
    private static int? MatchHyphenatedWord(string b, int start)
    {
        if (!char.IsAsciiLetter(b[start]))
        {
            return null;
        }

        int end = start + 1;
        while (end < b.Length && (char.IsAsciiLetter(b[end]) || b[end] is '\'' or '-'))
        {
            end++;
        }

        for (int i = end - 1; i >= start + 2; i--)
        {
            if (char.IsAsciiLetter(b[i]))
            {
                return i + 1;
            }
        }

        return null;
    }

    /// <summary>Ellipsis: <c>\.( *\.)+</c>.</summary>
    private static int? MatchEllipsis(string b, int start)
    {
        if (b[start] != '.')
        {
            return null;
        }

        int? end = null;
        int j = start + 1;
        while (true)
        {
            int k = j;
            while (k < b.Length && b[k] == ' ')
            {
                k++;
            }

            if (k < b.Length && b[k] == '.')
            {
                end = k + 1;
                j = k + 1;
            }
            else
            {
                return end;
            }
        }
    }

    /// <summary>
    /// The part of nltk's <c>TweetTokenizer</c> that the filtered character
    /// set (<c>a-z A-Z ' . , ? ! -</c> and space) can reach. At each position
    /// the first matching alternative wins, in nltk's order; spaces only
    /// separate words.
    /// </summary>
    private static List<string> TweetTokenize(string text)
    {
        string b = ShortenHang(text);
        var words = new List<string>();
        int i = 0;
        while (i < b.Length)
        {
            if (b[i] == ' ')
            {
                i++;
                continue;
            }

            int letterEnd = LetterRunEnd(b, i);
            int end = MatchDomain(b, i)
                ?? MatchHyphenatedWord(b, i)
                ?? (letterEnd > i ? (int?)letterEnd : null)
                ?? MatchEllipsis(b, i)
                ?? i + 1;
            words.Add(b[i..end]);
            i = end;
        }

        return words;
    }

    /// <summary>
    /// All of g2p_en's preprocessing: number expansion, accent stripping, the
    /// character filter, the i.e./e.g. replacement and tokenization. The words
    /// keep their case; Python's are these words lowercased.
    /// </summary>
    /// <param name="text">Input text.</param>
    /// <returns>The words, each one ASCII.</returns>
    public static List<string> NormalizeAndTokenize(string text)
    {
        string s = StripAccentsAndFilter(NormalizeNumbers(text));
        s = ReplaceIgnoreAsciiCase(s, "i.e.", "that is");
        s = ReplaceIgnoreAsciiCase(s, "e.g.", "for example");
        return TweetTokenize(s);
    }
}
