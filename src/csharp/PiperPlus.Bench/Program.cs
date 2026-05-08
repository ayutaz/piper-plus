// Issue #383 Phase 1 — C# 実機ベンチハーネス。
// 直列 (PIPER_G2P_PARALLELISM=1) と auto 並列 (未設定) の synthesize 全体
// time を比較する。CLI ではなく PiperPlus.Core API を直接叩いて
// プロセス起動コストを除外する。

using System.Diagnostics;
using Microsoft.ML.OnnxRuntime;
using PiperPlus.Cli;
using PiperPlus.Core.Config;
using PiperPlus.Core.Inference;
using PiperPlus.Core.Phonemize;

string repoRoot = FindRepoRoot();
string modelPath = args.ElementAtOrDefault(0)
    ?? Path.Combine(repoRoot, "test", "models", "multilingual-test-medium.onnx");
string seedFile = args.ElementAtOrDefault(1)
    ?? Path.Combine(repoRoot, "tools", "benchmark", "texts", "ja.txt");
int[] ns = { 1, 2, 5, 10, 20 };
int repeats = 3;
int warmups = 1;

string configPath = modelPath + ".json";
if (!File.Exists(modelPath) || !File.Exists(configPath))
{
    Console.Error.WriteLine($"Missing model/config: {modelPath} / {configPath}");
    return 2;
}

Console.WriteLine($"[bench] model: {modelPath}");
var sw0 = Stopwatch.StartNew();
var config = PiperConfig.LoadFromFile(configPath);
var session = SessionFactory.Create(modelPath);
using var model = new PiperModel(session, config);
SessionFactory.Warmup(session);
var piperSession = new PiperSession(model);
sw0.Stop();
Console.WriteLine($"[bench] model loaded + warmup in {sw0.Elapsed.TotalMilliseconds:F1} ms");

// multilingual-test-medium is ja-en-zh-es-fr-pt.
var phonemizer = BuildMultilingualPhonemizer();

string[] seeds = File.ReadAllLines(seedFile)
    .Select(l => l.Trim())
    .Where(l => l.Length > 0)
    .ToArray();
Console.WriteLine($"[bench] {seeds.Length} seed sentences");

// Global warmup so the JITted hot path / DotNetG2P caches are warm before
// per-N measurement begins.
for (int i = 0; i < 3; i++)
{
    RunOnce(BuildText(seeds, 2));
}

// Per-config × per-N median latency.
var results = new List<(string Cfg, int N, double MedianMs, double MeanMs)>();
foreach (var cfg in new[] { "serial", "parallel" })
{
    if (cfg == "serial")
    {
        Environment.SetEnvironmentVariable("PIPER_G2P_PARALLELISM", "1");
    }
    else
    {
        Environment.SetEnvironmentVariable("PIPER_G2P_PARALLELISM", null);
    }

    Console.WriteLine($"\n[bench] === {cfg} ===");
    foreach (var n in ns)
    {
        var text = BuildText(seeds, n);
        bool warmupCrashed = false;
        for (int w = 0; w < warmups; w++)
        {
            try
            {
                RunOnce(text);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  N={n} warmup={w}: CRASH ({ex.GetType().Name}: {ex.Message})");
                warmupCrashed = true;
                break;
            }
        }
        if (warmupCrashed)
        {
            results.Add((cfg, n, double.NaN, double.NaN));
            continue;
        }

        var samples = new List<double>(repeats);
        bool crashed = false;
        for (int r = 0; r < repeats; r++)
        {
            try
            {
                var sw = Stopwatch.StartNew();
                int sentenceCount = RunOnce(text);
                sw.Stop();
                samples.Add(sw.Elapsed.TotalMilliseconds);
                Console.WriteLine($"  N={n} rep={r}: {sw.Elapsed.TotalMilliseconds,8:F1} ms ({sentenceCount} sentences)");
            }
            catch (Exception ex)
            {
                // Phase 1 の重要な発見: JapanesePhonemizer 経由で
                // DotNetG2P.MeCab.MeCabTokenizer を並列呼び出しすると
                // ViterbiDecoder.Decode で NullReference を吐く
                // (MeCab の Lattice 内部状態が共有されているため)。
                crashed = true;
                Console.WriteLine($"  N={n} rep={r}: CRASH ({ex.GetType().Name}: {ex.Message})");
                break;
            }
        }

        if (samples.Count == 0)
        {
            results.Add((cfg, n, double.NaN, double.NaN));
            continue;
        }

        samples.Sort();
        double median = samples.Count % 2 == 1
            ? samples[samples.Count / 2]
            : (samples[samples.Count / 2 - 1] + samples[samples.Count / 2]) / 2.0;
        double mean = samples.Average();
        results.Add((cfg, n, median, mean));
        if (crashed)
        {
            Console.WriteLine($"  N={n}: incomplete ({samples.Count}/{repeats} reps survived before crash)");
        }
    }
}

// Summary
Console.WriteLine("\n=== SUMMARY (median over repeats) ===");
Console.WriteLine($"{"cfg",-10} {"N",4} {"median_ms",10} {"mean_ms",10}");
foreach (var r in results)
{
    Console.WriteLine($"{r.Cfg,-10} {r.N,4} {r.MedianMs,10:F1} {r.MeanMs,10:F1}");
}

// serial vs parallel deltas
Console.WriteLine("\n=== DELTA serial -> parallel ===");
Console.WriteLine($"{"N",4} {"serial_ms",10} {"parallel_ms",12} {"delta_%",8}");
foreach (var n in ns)
{
    var s = results.First(r => r.Cfg == "serial" && r.N == n);
    var p = results.First(r => r.Cfg == "parallel" && r.N == n);
    if (double.IsNaN(p.MedianMs) || double.IsNaN(s.MedianMs))
    {
        Console.WriteLine($"{n,4} {s.MedianMs,10:F1} {p.MedianMs,12:F1}    n/a");
        continue;
    }
    double pct = (p.MedianMs - s.MedianMs) / s.MedianMs * 100;
    Console.WriteLine($"{n,4} {s.MedianMs,10:F1} {p.MedianMs,12:F1} {pct,+7:F1}%");
}

return 0;


// ---- helpers ----

int RunOnce(string text)
{
    var sentences = TextSplitter.SplitSentences(text);
    if (sentences.Count == 0)
    {
        sentences = new List<string> { text };
    }

    var encoded = SentenceParallelEncoder.EncodeAll(
        sentences,
        sentence =>
        {
            var (ids, prosody) =
                PhonemeEncoder.EncodeDirect(phonemizer, sentence, config.PhonemeIdMap);
            if (!model.HasProsody)
            {
                prosody = null;
            }
            return (Ids: ids, Prosody: prosody);
        });

    foreach (var entry in encoded)
    {
        var input = new SynthesisInput(
            entry.Ids,
            SpeakerId: 0,
            LanguageId: 0,
            ProsodyFeatures: entry.Prosody);
        _ = piperSession.Synthesize(input);
    }
    return sentences.Count;
}

static string BuildText(string[] seeds, int n)
{
    var sb = new System.Text.StringBuilder();
    for (int i = 0; i < n; i++)
    {
        sb.Append(seeds[i % seeds.Length]);
    }
    return sb.ToString();
}

static IPhonemizer BuildMultilingualPhonemizer()
{
    var dict = new Dictionary<string, IPhonemizer>
    {
        ["ja"] = new JapanesePhonemizer(new DotNetG2PEngine()),
        ["en"] = new EnglishPhonemizer(new DotNetEnglishG2PEngine()),
        ["zh"] = new ChinesePhonemizer(new DotNetChineseG2PEngine()),
        ["es"] = new SpanishPhonemizer(new DotNetSpanishG2PEngine()),
        ["fr"] = new FrenchPhonemizer(new DotNetFrenchG2PEngine()),
        ["pt"] = new PortuguesePhonemizer(new DotNetPortugueseG2PEngine()),
    };
    return new MultilingualPhonemizer(dict, defaultLatinLanguage: "en");
}

static string FindRepoRoot()
{
    var dir = new DirectoryInfo(AppContext.BaseDirectory);
    while (dir is not null)
    {
        if (File.Exists(Path.Combine(dir.FullName, "CLAUDE.md")))
        {
            return dir.FullName;
        }
        dir = dir.Parent;
    }
    // Fallback: 6 levels up from bin/Debug/net10.0
    return Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", ".."));
}
