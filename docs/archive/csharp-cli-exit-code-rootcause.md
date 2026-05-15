# C# CLI exit code propagation — root cause analysis

## 症状 (PR #401 で観測)

`PiperPlus.Cli` の voice-cloning validation が `LogError(...) + Environment.ExitCode = 1 + return;` を実行しても、 `--test-mode` 経路では process exit code が 0 のまま (validation 由来の non-zero が伝搬しない)。

CI で fail した test:

- `CliIntegrationTests.ReferenceAudio_WithoutSpeakerEncoderModel_Errors`
- `CliIntegrationTests.SpeakerEmbedding_InvalidFileSize_Errors`
- `CliIntegrationTests.SpeakerEmbedding_EmptyFile_Errors`

すべて `Assert.NotEqual(0, exitCode)` で `Expected: Not 0 / Actual: 0` で fail。

## 仮説検証

| # | 仮説 | 検証結果 |
|---|------|----------|
| 1 | `Action<ParseResult>` lambda の `Environment.ExitCode = 1` は `Invoke()` 戻り値に伝搬しない | **確定** |
| 2 | `--test-mode` が validation を bypass | 否定 — voice-cloning validation block (Program.cs:587-644) に `if (testMode)` gate なし、 line 649 の test-mode 早期 exit は validation の **後** にある |
| 3 | `parseResult.GetValue(referenceAudioOption)` が `--test-mode` 経路で null を返す | 否定 — option は line 285-287 で root command に登録、 closure capture は他 option と同等で問題なし |
| 4 | `dotnet run` subprocess が `Environment.ExitCode` を伝搬しない | 否定 — `dotnet run` は target program の Main return value をそのまま exit code として返す。 `Speaker_AndReferenceAudio_AreMutuallyExclusive` test は exit code を assert していないため、 validation 経由でも exit 0 でも pass する |
| 5 | 既存 mutex test は別 path で exit 1 になっていて、 mutex check は実は到達していない | 否定 — `Speaker_AndReferenceAudio_AreMutuallyExclusive` は `Assert.Contains("mutually exclusive")` のみで exit code を assert しないため、 mutex validation 由来の `Environment.ExitCode = 1` が実は伝搬していなくても test pass する |

## Root cause (仮説 1 の詳細)

`Program.cs:71`:

```csharp
return rootCommand.Parse(args).Invoke();
```

Main の return value が process exit code。 `Invoke()` の戻り値は SetAction で登録した lambda の signature 次第:

- **`SetAction(Action<ParseResult>)` overload**: lambda は void return、 `Invoke()` は **エラーなし完了で 0 を返す**。 lambda 内の `Environment.ExitCode = 1` は static property を設定するが、 Main が int を明示的に return するため上書きされる (Environment.ExitCode は void Main 時のみ honored)。
- **`SetAction(Func<ParseResult, int>)` overload**: lambda の int return 値が `Invoke()` 戻り値となり Main 経由で process exit code に。

現状の `Program.cs:290`:

```csharp
rootCommand.SetAction((parseResult) =>
    {
        // ...
        Environment.ExitCode = 1;
        return;          // ← void return → Action<ParseResult> overload
        // ...
    });
```

`return;` (void) のため C# は `Action<ParseResult>` overload を選択、 `Invoke()` は 0 を返す → exit code 0。

## なぜ 既存テストでは見えなかったか

PR #401 以前の CLI には voice-cloning validation がなく、 すべての validation の `Environment.ExitCode = 1; return;` パターン (~28 箇所) が同じバグを抱えていた。 ただし全ての既存 test は **stderr message のみを assert** し、 exit code を `Assert.NotEqual(0, ...)` で assert する test がなかった (`SkipIfBuildFailed` も build failure pattern を check するのみで non-zero を期待しない)。

PR #401 で 3 新規 test (`ReferenceAudio_WithoutSpeakerEncoderModel_Errors` etc) が **初めて** `Assert.NotEqual(0, exitCode)` を assert したことで、 latent bug が顕在化した。

## Fix

`SetAction((parseResult) =>` lambda の signature を `Func<ParseResult, int>` に変更:

1. lambda 末尾に `return Environment.ExitCode;` を追加 (success case で 0 を返す)
2. lambda 内の **全** `return;` を `return Environment.ExitCode;` に変更 (28 箇所)
3. これにより `Environment.ExitCode = 1; return;` は実質的に `return 1;` 相当となる
4. C# overload resolution は lambda の int return から `Func<ParseResult, int>` を選択 → `Invoke()` が int を返す → Main の exit code に伝搬

`return Environment.ExitCode;` (vs `return 1;` の直接置換) を採用する理由:

- 既存 28 箇所の `Environment.ExitCode = 1; return;` の直前 set を保持 → 振る舞い等価で diff 最小
- 既存 success path (`return;` のみ) は `Environment.ExitCode` 初期値 0 を返す → 等価

## 影響範囲

- `Program.cs:290-1445` の SetAction lambda body 内 34 箇所の `return;` を refactor
- helper void method (line 1660+ 以降の `WriteTextModeOutput` etc) は触らない
- 既存全 1339+ test は exit code を assert しないため regression なし
- 新規 3 voice-cloning tests は Skip 解除後 pass する
