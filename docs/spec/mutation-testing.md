# Mutation Testing Specification

> 3 runtime (Python / Rust / C#) で mutation testing を導入し、
> 「unit test がバグを検出できる強度 (mutation kill-rate)」を測定する。
> 重い (~30 min - 数時間) ため **manual + weekly cron 専用**で、 push 毎には走らせない。

## 動機 (Why mutation testing?)

通常の line/branch coverage は「実行されたか」しか見ないため、 assert が
無い test でも 100% 取れる。 mutation testing は source に小さな変異
(`+` → `-`, `==` → `!=`, `True` → `False` 等) を注入し、 test suite が
それを fail させるかを測ることで **test の検出力** を直接測る。

`piper-plus` は G2P / SSML / text splitter / timing といった **pure logic
で分岐が多い**モジュールに高い test カバレッジを持っており、 mutation testing
の費用対効果が最も高い対象。 ONNX 推論や I/O は対象外 (mutation の意味が薄い)。

## Target module の選定基準

1. **Pure logic (deterministic)**: 入力 → 出力が決定的で、 mock や fixture が
   軽量に組める。
2. **High existing coverage (>= 80%)**: line coverage が低い場所で mutation
   を回しても、 大半が "no test reaches this" になるだけで意味が薄い。
3. **High-impact**: regression が起きると user-visible (発音の崩れ、
   SSML 解釈ミス、 splitter の文末判定ミス等)。

## Runtime 別構成

### Python (`mutmut`)

| 項目 | 値 |
|------|-----|
| Tool | [`mutmut`](https://github.com/boxed/mutmut) >= 2.4 (stable、 pytest 互換) |
| 候補比較 | `cosmic-ray` は機能豊富だが設定が重い。 `mutmut` は CLI が簡潔で `paths_to_mutate` に絞れる |
| 設定ファイル | `.mutmut.toml` (repo root) |
| Target | `src/python/g2p/piper_plus_g2p/multilingual.py`, `ssml.py`, `base.py` / `src/python_run/piper/text_splitter.py`, `timing.py` |
| Test runner | `uv run pytest src/python/g2p/tests src/python_run/tests -x -q --no-cov` |
| Cache | `.mutmut-cache` (`.gitignore` 済) |

#### Install / run

```bash
# install (dev group に pin 済み — uv sync 済みなら不要)
pip install 'mutmut>=2.4,<3'   # or: uvx mutmut --version

# 全 module を実行 (manual; 数十分 - 1 時間オーダー)
uvx mutmut run

# 特定 file のみ
uvx mutmut run --paths-to-mutate src/python_run/piper/text_splitter.py

# 結果確認
uvx mutmut results        # survived/killed の summary
uvx mutmut html           # html/index.html を生成 (CI artifact 化)
uvx mutmut show <id>      # 個別 mutant の diff
```

### Rust (`cargo-mutants`)

| 項目 | 値 |
|------|-----|
| Tool | [`cargo-mutants`](https://github.com/sourcefrog/cargo-mutants) (stable Rust 対応) |
| 候補比較 | `mutagen` は nightly compiler 必須で CI コスト過大。 `cargo-mutants` は stable で動き、 `--file` で対象を絞れる |
| 設定 | CLI フラグで指定 (workspace 全体に config file は置かない)。 `--file` で対象モジュールを限定 |
| Target | `src/rust/piper-plus-g2p/src/ssml.rs`, `src/rust/piper-core/src/text_splitter.rs` |
| Cache | `mutants.out/` (`.gitignore` 済) |

#### Install / run

```bash
# install (CI と同様 — latest stable)
cargo install --locked cargo-mutants
# or pinned (再現性が必要な場合; 現在の stable に合わせて随時更新):
# cargo install --locked cargo-mutants@25.3.1
#
# CI workflow 側は `--locked` で十分 (Cargo.lock 相当の挙動)、 docs で
# pin 例を示すに留め、 workflow は最新 stable を取り続ける運用。
# version drift で結果が変わった場合は本 doc の Baseline 章 + pin を更新。

# piper-plus-g2p の ssml.rs を変異 (manual)
cd src/rust
cargo mutants -p piper-plus-g2p --file src/ssml.rs --no-shuffle

# piper-core の text_splitter.rs
cargo mutants -p piper-plus --file src/text_splitter.rs --no-shuffle

# 結果は mutants.out/ 配下に diff + log として残る。
# `cargo mutants --list-files` で対象 ファイルを事前確認できる。
```

参考 (将来 `.cargo/config-mutants.toml` を導入する場合の雛形):

```toml
# src/rust/.cargo/config-mutants.toml — 参考のみ (実体は CLI で渡す)
# cargo-mutants v25+ では `--in-place=false` がデフォルト。
# build profile を mutants 専用に分けたい場合に活用する:
# [profile.mutants]
# inherits = "test"
# debug = "line-tables-only"
```

### C# (`Stryker.NET`)

| 項目 | 値 |
|------|-----|
| Tool | [`Stryker.NET`](https://stryker-mutator.io/docs/stryker-net/introduction/) (stable、 .NET 9 / 10 対応) |
| 候補比較 | 実質一強。 NuGet ではなく `dotnet tool install --global dotnet-stryker` で導入 |
| 設定ファイル | `src/csharp/stryker-config.json` |
| Target | `Phonemize/MultilingualPhonemizer.cs`, `InlinePhonemeParser.cs`, `IpaTokenizer.cs`, `ArpabetToIPAConverter.cs`, `Ssml/SsmlParser.cs` |
| Test project | `PiperPlus.Core.Tests/` |
| Cache | `StrykerOutput/` (`.gitignore` 済) |

#### Install / run

```bash
# install (global tool)
dotnet tool install --global dotnet-stryker

# 実行 (config file を参照)
cd src/csharp
dotnet stryker -c stryker-config.json
# → StrykerOutput/<timestamp>/reports/mutation-report.html
```

## 閾値ポリシー (high / low / break)

Stryker.NET の慣習に従い、 3 runtime 全体で同じ運用にする:

| 閾値 | 値 | 意味 |
|------|-----|------|
| `high` | **80** | 良好。 これ以上を target にする (新規 PR で逆行させない) |
| `low` | **60** | 許容下限。 これ未満で warn |
| `break` | **50** | これ未満で CI fail |

ただし **初期 (baseline 確立まで) は `break = 0`** で warn-only 運用する。
理由: 初回は survived mutant の多くが「テスト不足」ではなく「mutmut/Stryker
の semantic-equivalent mutation」「timing 依存」「言語固有の挙動」等の
ノイズである可能性があり、 まず実値を観測して baseline を決める必要がある。

数週間 (3-4 回) 走らせて分布が安定したら、 各 runtime の中央値 - 5pt 程度を
break として昇格する。

### Mutant 状態の解釈

| 状態 | 意味 | 対応 |
|------|------|------|
| `killed` | テストが mutant を検出 (期待動作) | OK |
| `survived` | テストが mutant を見逃した | テスト追加 or assertion 強化 |
| `timeout` | mutant がテストを停止させた (無限ループ等) | killed とみなす (Stryker default) |
| `no_coverage` | mutant が test 実行で touch されない | 対象範囲外 — 設定で除外推奨 |
| `compile_error` | mutant が compile に失敗 | tool が自動除外 |

kill rate = `killed / (killed + survived)` (timeout を分子に含める実装もある)。

## CI cadence

`.github/workflows/mutation-testing.yml`:

- **Trigger**:
  - `workflow_dispatch`: 手動実行 (PR 検証や ad-hoc 実験用)
  - `schedule: cron '0 0 * * 0'`: **毎週日曜 00:00 UTC** (= 09:00 JST 月曜)
- **Matrix**: `[python, rust, csharp]` (各々 1 job、 合計 3 並列)
- **Artifact**: mutation report (HTML / JSON) を 30 日 retention で upload
- **Push to main**: しない (artifact を見るだけで OK、 result は read-only)
- **PR への影響**: ゼロ。 PR-time CI は走らない。

### 想定実行時間

| Runtime | 想定 | 備考 |
|---------|------|------|
| Python | 30 - 60 min | 5 files × ~数百 mutant × test suite |
| Rust | 20 - 45 min | `cargo-mutants` は build cache を毎回 invalidate するので長め |
| C# | 30 - 90 min | 5 files、 xUnit v3 が ~1000 test |

合計でも 90 分以内に収まる想定 (parallel 3 job)。 GitHub Actions の
6 時間 job timeout に対して十分マージンあり。

## 初回 baseline の確立フロー

1. PR で本 spec / config / workflow をマージ
2. `workflow_dispatch` で初回手動実行 (各 runtime)
3. 各 runtime の kill-rate を本 doc の "Baseline" 章に記録 (本 PR の follow-up)
4. 週次 cron で安定運用、 3-4 回後に `break` 閾値を実値に基づき設定
5. その後の新規 PR で kill-rate が下がったら CI fail (regression gate として機能)

### Baseline 昇格 (warn-only → break 強制) の運用ルール

| 項目 | 値 |
|------|-----|
| 決定権者 | **Team maintainer** (本リポジトリの管理者 1 名が最終承認。 周辺担当者の review 推奨) |
| 観測期間 | **4 週間** (= weekly cron 4 回ぶんのサンプル) |
| 判定指標 | 4 週間の **median kill-rate** (外れ値を排除するため mean ではなく median を採用) |
| `break` 閾値 | **median − 5pt** (整数に round-down)。 例: median 72% なら `break = 67` |
| `low` / `high` | `low = median − 5pt`、 `high = max(80, median)` を目安に同時更新 |
| 適用方法 | C# は `src/csharp/stryker-config.json` の `thresholds.break` を編集。 Rust/Python は本 doc に閾値表を維持し、 workflow の `continue-on-error: true` を `false` に切り替え |
| PR タイトル convention | `chore(quality-gates): mutation baseline 昇格 (week N)` (N は累計 cron 実行回数) |
| Rollback | 昇格後に regression PR が頻発した場合、 同じ convention で `(rollback)` を付けて閾値を 5pt 下げる |

### Baseline JSON 出力 path (各 runtime)

CI artifact から直接 baseline 値を再現できるよう、 報告書 JSON の正規 path
を以下で固定する。 本 doc の "Baseline" 表更新時は、 これらの JSON を一次
ソースとして数値を引用する:

| Runtime | JSON 出力 path (CI artifact 内) | 抽出キー |
|---------|--------------------------------|---------|
| Python (`mutmut`) | `html/mutmut.json` (※`uvx mutmut html` で生成。 環境により `html/index.html` のみの場合あり、 その際は `mutmut results` 出力を保存) | `killed` / `survived` / `timeout` の counts |
| Rust (`cargo-mutants`) | `src/rust/mutants.out/outcomes.json` | `outcomes[].summary` (caught / missed / timeout / unviable) |
| C# (`Stryker.NET`) | `src/csharp/StrykerOutput/<timestamp>/reports/mutation-report.json` | `files.*.mutants[].status` を集計 (`Killed` / `Survived` / `Timeout`) |

## Baseline (TBD)

> 初回実行後に follow-up PR で記入する。

| Runtime | Date | Killed | Survived | Timeout | Kill rate |
|---------|------|-------:|---------:|--------:|----------:|
| Python  | TBD  | -      | -        | -       | - |
| Rust    | TBD  | -      | -        | -       | - |
| C#      | TBD  | -      | -        | -       | - |

## 関連ファイル

- `.mutmut.toml` — Python mutmut 設定
- `src/csharp/stryker-config.json` — C# Stryker 設定
- `.github/workflows/mutation-testing.yml` — 週次 / 手動 CI
- `pyproject.toml` (dev group) — `mutmut>=2.4,<3` を pin
- `.gitignore` — 中間ファイル除外
