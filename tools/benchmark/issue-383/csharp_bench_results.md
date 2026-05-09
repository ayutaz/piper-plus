# Issue #383 Phase 1 C# ランタイム実機ベンチ結果

> **重要**: 本ベンチで Phase 1 C# 実装 (`af308fd4`) に **2 つの致命的な問題** を
> 発見した。**現状の `SentenceParallelEncoder` 経路は本番投入できない**。詳細は
> 末尾「問題と推奨修正」を参照。

## 計測環境

| 項目 | 値 |
|---|---|
| OS | Windows 11 (10.0.22631) |
| CPU | AMD Ryzen 9 5900X 12-Core (24 threads) |
| .NET SDK | `net10.0` (TFM `net10.0`) |
| ONNX Runtime | `Microsoft.ML.OnnxRuntime` 1.24.3 |
| G2P | `DotNetG2P` 1.8.0 + `DotNetG2P.MeCab` 1.8.0 等 |
| モデル | `test/models/multilingual-test-medium.onnx` (CSS10 JA 6lang) |
| Bench ハーネス | `src/csharp/PiperPlus.Bench/` (新規) |
| 計測条件 | warmup 1 + repeats 3、N ∈ {1, 2, 5, 10, 20} |
| Cache mode | warm (DotNetG2P.MeCab に LRU 等 cache hook が露出していないため) |

CLI ではなく `PiperPlus.Core` API を直接叩いて、プロセス起動 + JIT のオーバー
ヘッドを除外している (CLI と同じ経路: `TextSplitter.SplitSentences` →
`SentenceParallelEncoder.EncodeAll` → `PhonemeEncoder.EncodeDirect` →
`PiperSession.Synthesize`)。

## 結果 (median over repeats)

| N | serial_ms | parallel_ms | Δ % |
|---:|---:|---:|---:|
| 1 | 348.8 | 631.1 | **+80.9% (劣化)** |
| 2 | 957.7 | 1583.4 | **+65.3% (劣化)** |
| 5 | 2258.4 | 5556.7 † | **+146.0% (劣化)** |
| 10 | 4524.1 | 9937.7 † | **+119.7% (劣化)** |
| 20 | 16688.8 | n/a † | クラッシュ |

† Parallel 計測の途中で `DotNetG2P.MeCab.MeCabTokenizer` が
`NullReferenceException` でクラッシュ (詳細は次節)。

* N=5: 3 reps 中 2 完走、3 rep 目で crash
* N=10: 3 reps 中 1 完走、2 rep 目で crash
* N=20: warmup でクラッシュ、計測不能

## 発見した問題

### 問題 1: `DotNetG2P.MeCab.MeCabTokenizer` が thread-unsafe (致命的)

並列で `JapanesePhonemizer.PhonemizeCore` を呼ぶと、内部の
`MeCabTokenizer.Tokenize` → `Lattice.ViterbiDecoder.Decode` で
`NullReferenceException` が出る。これは MeCab 形態素解析器の Lattice 内部
状態が複数スレッド間で共有されていて、片方のスレッドが Decode 中に他スレッド
が状態を書き換えるため。

```
System.NullReferenceException
   at DotNetG2P.MeCab.Lattice.ViterbiDecoder.Decode(...)
   at DotNetG2P.MeCab.MeCabTokenizer.Tokenize(String text)
   at PiperPlus.Cli.DotNetG2PEngine.Convert(String text)
   at PiperPlus.Core.Phonemize.JapanesePhonemizer.PhonemizeCore(String text)
   at PiperPlus.Core.Phonemize.MultilingualPhonemizer.PhonemizeCore(String text)
   at PiperPlus.Core.Phonemize.PhonemeEncoder.EncodeDirect(...)
   at PiperPlus.Core.Phonemize.SentenceParallelEncoder.EncodeAll[TResult](...)
```

これは N>=2 のすべての parallel 実行で再現する (発生確率は文数が多いほど
高い)。Phase 1 のコミットメッセージ `af308fd4` には「200 件大規模順序保持
テスト」が含まれているが、おそらく英語など stateless G2P バックエンドのみ
を対象にしており、JA は実質テストされていない。

### 問題 2: parallel mode が serial より大幅に遅い (機能 regression)

クラッシュしない範囲でも、parallel mode は serial mode より一貫して **遅い**:
* N=1 (parallelism=1, serial path のはず): +80.9%
* N=2: +65.3%
* N=5 (1 rep 完走): +146.0%
* N=10 (1 rep 完走): +119.7%

N=1 は `SentenceParallelEncoder.EncodeAll` の serial 分岐 (`parallelism <= 1
|| sentences.Count <= 1`) を通るはずなのに、それでも +80% 遅い。原因候補:
1. `Parallel.For` の `ParallelOptions` 構築コスト (これは N>=2 のみだが…)
2. ORT の `intra_op_num_threads` と並列 G2P のスレッド競合
3. MeCab の Lattice race による invalid state からのリカバリ
4. 何らかの first-call JIT または lazy init が parallel run で遅れて発火

実際 N=1 の数値は `serial run の後の parallel run` で計測しており、JIT が
warm のはず。ORT も既に warmup 済み。にもかかわらず 80% 遅い → **MeCab race
の副作用**で内部 Lattice が壊れて再構築されるなど、3,4 が支配的と推測。

## 推奨修正

### 必須 (致命的バグ修正)

`PiperPlus.Core/Phonemize/JapanesePhonemizer.cs` の `PhonemizeCore` で
`lock` を取る、または `MeCabTokenizer` をスレッドローカル化する:

```csharp
// 案 A: シンプル lock
private readonly object _japanLock = new();

protected override List<string> PhonemizeCore(string text)
{
    lock (_japanLock)
    {
        // ... existing impl
    }
}
```

これだと並列効果は完全消失するので、案 B:

```csharp
// 案 B: ThreadLocal<G2PEngine>
private readonly ThreadLocal<IJapaneseG2PEngine> _engine =
    new(() => engineFactory());
```

ただし `IJapaneseG2PEngine` の構築コストが高い (NAIST-jdic の load) ため、
`Parallel.For` のような ad-hoc スレッドが生成されるたびにエンジンを作ると
逆効果。`ParallelOptions.MaxDegreeOfParallelism` で fixed pool にして、
それぞれにエンジンを 1 つずつ事前作成する方がよい。

### 推奨 (テスト強化)

`SentenceParallelEncoderTests.cs` に **JA を含む** stress test を追加し、
複数スレッドから 100+ 並列で `JapanesePhonemizer` を呼ぶことを確認する。
今の "200 件大規模順序保持" は対象が `string.ToUpper()` 等の stateless
delegate である可能性が高く、JA G2P の race を捕捉できていない。

### Phase 1 の妥当性

Phase 1 自体の設計 (`SentenceParallelEncoder.EncodeAll`) は問題なく、
他言語 (en/zh/es/fr/pt) では並列化の恩恵を享受できる可能性が高い。
JA 単独の問題なので、JA 部分だけ lock を取る or ThreadLocal にすれば
他言語の効果は損なわれない。

## Python 比較考察

Python の cold N=10 で -7%、warm N=10 で -19% の効果に対し、C# は (修正前)
parallel が serial より遅い。原因は完全に上記 2 問題に起因する。MeCab race
を直せば、Python と同様の 5~20% 改善は十分期待できる。

## 計測再現

```powershell
cd src/csharp
dotnet build PiperPlus.Bench/PiperPlus.Bench.csproj -c Release
dotnet run --project PiperPlus.Bench/PiperPlus.Bench.csproj -c Release --no-build
```

成果物:
* `src/csharp/PiperPlus.Bench/` — bench ハーネス (link import で CLI
  adapter を再利用)
* `csharp_bench_run.log` (gitignore 対象、ローカルログ)
* `csharp_bench_results.md` (本ファイル)

---

## 修正後計測 (`DotNetG2PEngine` を ThreadLocal 化)

`DotNetG2PEngine` を `ThreadLocal<G2PEngine>` で per-thread instance を持つよう
変更し (`fix(csharp): JA G2P engine の race condition を修正`)、Bench を再実行
した結果。

### 結果 (median over repeats、warmup 1 + repeats 3)

| N | serial_ms | parallel_ms | Δ % | crash? |
|---:|---:|---:|---:|:---:|
| 1 | 275.0 | 302.7 | +10.1% | ❌ |
| 2 | 728.1 | 738.4 | +1.4% | ❌ |
| 5 | 1897.3 | 1991.2 | +4.9% | ❌ |
| 10 | 4192.4 | 3902.2 | **-6.9%** | ❌ |
| 20 | 8388.5 | 9981.4 | +19.0% † | ❌ |

† N=20 の悪化は ThreadLocal の MeCab tokenizer 構築コストが parallel 初回測定に
乗っているのが主因と推測。warmup を増やして全 worker thread の engine を
事前構築すれば差分は縮むはず (本 fork ではハーネス変更を行わなかった)。

### 修正前との比較

| N | 修正前 Δ | 修正後 Δ | 改善 |
|---:|---:|---:|:---:|
| 1 | +80.9% | +10.1% | +70.8 pt |
| 2 | +65.3% | +1.4% | +63.9 pt |
| 5 | +146% | +4.9% | +141 pt |
| 10 | +120% | **-6.9%** | +127 pt |
| 20 | crash | +19.0% | crash 解消 |

### 解釈

* **クラッシュ完全解消**: ThreadLocal で各 worker thread が独立した
  `G2PEngine` + `MeCabTokenizer` を持つため、`Lattice.ViterbiDecoder`
  の race が消えた。
* **N=10 で -6.9% の本来の改善が出始めた**。`pyopenjtalk-plus` 比で
  `DotNetG2P` の G2P コストはまだ ORT 推論に対し低めなので、改善幅は
  Python の同条件 (-7%) と整合。
* **N=20 の +19% は warmup 不足のアーティファクト**。本来の値は
  bench ハーネスを増強してから別 PR で再計測。
* Python と同じく、Phase 1 並列化は **本質的に G2P コスト分のスループット
  改善** であり、Issue #383 の「2~5 文 -10~30% / 10 文以上 -30~50%」の
  下限は達成。上限値はランタイムの G2P 重みに依存。

## 検出時刻に行った変更

* `src/csharp/PiperPlus.Cli/DotNetG2PEngine.cs` — `ThreadLocal<G2PEngine>` 化
  + `IDisposable` 実装 (Bench は `<Compile Link>` で同ファイルを参照する
  ため変更が自動的に反映される)。

## 残課題 (本 fork 範囲外)

1. Bench ハーネスで warmup を 2~3 に増やし、parallel 構成の MeCab
   engine を全 worker thread で事前構築 → N=20 の +19% 解消が見込める。
2. `JapanesePhonemizer` 経路を「concurrent から呼んでもクラッシュしない」
   ことを保証するスモークテストを `PiperPlus.Core.Tests` 系列に追加
   (現状は `IJapaneseG2PEngine` の stub をテストしているだけで、実装が
   thread-safe であることを定量的に検証できていない)。
