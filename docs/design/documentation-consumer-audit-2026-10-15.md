# 文書から導入・実行・配布・CI をたどる第三次監査

調査日: 2026-10-15。対象ブランチ: `docs/update-documentation-20261015`。
対象コミット: `bf1903fb95554ef732d942f7d0bc4a64876a743e`。
本書の行番号・公開 metadata はこの時点の記録であり、修正後の状態を示すものではない。

## 結論

一次・二次監査で文書を同期した後にも、導入手順、実行入口、検査ツール、公開配布物の案内に対応漏れが残る。
確認できた新規所見は以下の 16 件。P1 は主要な導入・利用経路を妨げるもの、P2 は機能・検査範囲の不一致、P3 は補助案内のずれとした。
実行で再現したもの、依存解決の dry-run、ソース追跡、公開 metadata の照合を区別した。

| ID | 優先度 | 所見 | 証拠の種類 |
|---|---|---|---|
| A01 | P1 | 8 README のモデル管理・WebUI コマンドが uv 環境の Python を選ばない | CLI 実行、文書 |
| A02 | P1 | Python GPU 導入が CPU/GPU 両方の ORT distribution を同じ環境に残す | manifest、依存解決 dry-run |
| A03 | P2 | ハッシュ照合・自動更新の補助ツールが現在の artifact 階層を読めない | 小さな合成 fixture／コピーで実行 |
| A04 | P2 | 公開済み manifest entry の空ハッシュ・仮値・不正サイズを構造 gate が通す | メモリ上の変異入力で実行 |
| A05 | P1 | Rust JSONL 文書の text/speaker/language と実際の入力 schema が異なる | Deserialize 定義と呼出経路 |
| A06 | P2 | Rust `--phoneme-silence` が音声に適用されない | 明示 TODO と未使用変数 |
| A07 | P2 | Rust JSONL は出力先省略時、推論に成功しても音声を出力しない | 全出力分岐の追跡 |
| A08 | P2 | C# CLI の timing 出力は常に skip する | 全オプション参照の追跡 |
| A09 | P2 | Go timing 出力は text mode のみで batch／JSONL に接続されていない | 全 writer 呼出の追跡 |
| A10 | P2 | Go/Rust の SSML parser と通常の合成入口が接続されていない | parser の存在確認と合成経路 |
| A11 | P1 | 公開 Rust CLI を GPU 用に選ぶ案内と release の feature 設定が異なる | build recipe、公開 asset 一覧 |
| A12 | P2 | WebUI の直接 pip 導入が workspace の HF Hub 制約を外れる | 依存解決 dry-run |
| A13 | P2 | Swift G2P 公開 ZIP の取得サイズが案内と異なる | Release API metadata |
| A14 | P3 | npm `setup:wasm` が現行 Release にない asset pattern を案内する | script、Release API metadata |
| A15 | P2 | ONNX export 契約の「毎回の CI 動的検証済み」という説明が過大 | workflow、検査関数の変異入力 |
| A16 | P3 | Rust help の言語一覧に `sv` がない | help と入力 validation の比較 |

今回の変更は調査レポートの追加。製品コード、依存定義、既存ガイドの修正は実施していない。
公開モデルの破損、GPU 起動の必然的失敗、SSML の実音声、実機性能を確認した結果ではない。

## 調査方法と範囲

前回までの「文書ファイルと実装の記載が一致するか」から、次の 4 経路に視点を変えた。

1. README を新しい shell で順に実行し、実際に使われる Python と依存集合を確認する。
2. CLI/API の入口から parser、推論、writer まで追跡し、受理される引数が成果物に反映されるか確認する。
3. 意図的に小さく壊した入力を検査関数へ渡し、CI の成功が何を保証するか確認する。
4. source build の機能と公開 binary/package の URL・サイズ・build feature を照合する。

並列調査の結果は統合時に再確認し、Go SSML parser 不在という誤認、Android AAR 未公開という未確認の推測、意図した stale-only CLI gate の動作を不具合扱いする指摘は除外した。
既知の課題の再掲で新規件数を増やしていない。大モデル取得、学習、GPU 起動、Docker build、公開・push・PR 操作は行っていない。

## 初回導入・Python 環境

### A01: uv sync の後に裸の python を使う

**確認済み。** `README.md:186-188` は `uv sync --extra inference`、モデル管理の `:214-222` と WebUI の `:228-230` は `python -m piper_plus ...` を使う。
同じ構造が `README_EN.md:144-160`、`README_DE.md:193-209`、`README_ES.md:193-209`、`README_FR.md:134-150`、`README_KO.md:191-207`、`README_PT.md:191-207`、`README_ZH.md:191-207` にある。
最初の推論例には既に `uv run` があり、問題は後続のモデル管理・WebUI 手順。

```powershell
python -m piper_plus --help
# ...pythoncore-3.14-64/python.exe: No module named piper_plus
uv run --no-sync python -m piper_plus --help
# usage: __main__.py ...（成功）
```

`uv sync` は呼出元 shell の Python を activate しない。ホスト Python に同パッケージが入っていない本環境で失敗を再現した。
`docs/getting-started/windows-setup.md:82-90`、`docs/features/webui.md:17-33` の実行方法とそろえる必要がある。
WebUI の依存導入後のブラウザ起動は今回未確認。

### A02: CPU/GPU ONNX Runtime の同居

**依存定義と dry-run で確認。** `pyproject.toml:37` の無条件 CPU ORT、`:64-74` の GPU extra が併存する。
`src/python_run/requirements.txt:3` と `setup.py:28-41` も CPU ORT を要求し、`src/python/pyproject.toml:65-77` は GPU ORT を追加する。

```powershell
uv tree --locked --package piper-plus --depth 2
# onnxruntime v1.30.0
# onnxruntime-gpu v1.25.1 (extra: gpu)
uv sync --dry-run --locked --extra inference-gpu --no-dev
# + onnxruntime-gpu==1.25.1
# CPU onnxruntime の除去は計画されない
```

tree は optional dependency も表示するため、それだけでは実インストールの証拠にならない。base の無条件依存と GPU extra の dry-run を併せて判断した。
[ONNX Runtime の公式導入案内](https://onnxruntime.ai/docs/get-started/with-python) は同一環境には CPU/GPU のどちらか一方だけを入れるよう要求している。
GPU wheel のインストール、CUDA provider のロード、音声生成は未実施。「必ず GPU 起動に失敗する」とは断定しない。

### A12: WebUI の直接 pip 導入が workspace 制約外へ変更する

**dry-run で確認。** `README.md:225-231`、`docs/features/webui.md:17-21` は root 環境へ `requirements_webui.txt` を直接入れる。
`pyproject.toml:17` は `huggingface-hub>=0.36.2,<1.0`。

```powershell
uv pip install --dry-run -r src/python_run/requirements_webui.txt
# - huggingface-hub==0.36.2
# + huggingface-hub==1.33.0
# - numpy==2.4.6
# + numpy==2.2.6
```

HF Hub の予定値は root 制約外。numpy の変更自体は root の範囲内であり、独立した制約違反ではない。
Gradio の pin 一致を調べる検査が成功しても、workspace 全体の依存整合性は保証されない。
これはインストール計画の結果であり、変更後の WebUI や学習の実行失敗を再現したものではない。

## モデル manifest と検査の実効性

### A03: 現在の artifact 階層に未対応の補助ツール

**実行で確認。** 現在の `docs/spec/model-sha256-manifest.toml` は `[[models.artifacts]]` に hash/bytes を持つ。
`scripts/verify_model_checksums.py:54-60,76-90` は model 直下の `sha256` を読む。

```powershell
uv run --no-project python -X utf8 scripts/verify_model_checksums.py --print-manifest
# multilingual-6lang-base: <missing>
# ... 全 8 model が <missing>
```

同じ nested schema の小さな manifest をメモリ上で渡す実験では、正しい fixture と破損 fixture の両方が「No matching manifest entry」の warning と exit 0 になった。
正しい hash は `a21231df3b44d6dc067d406f0b20003bfa6d7a492c0be8898ce6266ae6f6f4df`、破損後は `5a13e8eb545510dfc8d1f3b2a6cc9937ae644e40a9235e5a1d012b4cfff002a1`。
未知の利用者モデルを warning にする既存方針とは別に、公式 artifact さえ現在の schema では照合対象にできない。

`scripts/auto_update_model_manifest.py:56-79,158-195` も旧 model 直下の field を想定する。
実 manifest のコピーを `MANIFEST` に指定して `--name zero-shot-base-zs-v1 --onnx <15-byte-fixture> --force` を呼んだ結果は次のとおり。

```text
field sha256= not found in block
field bytes= not found in block
exit=0, manifest_text_unchanged=true
```

**影響の限界。** `.github/workflows/model-quality-gate.yml:95-97` は `--print-manifest` のみを呼び、`continue-on-error: true`。
更新 helper が現行 HF publisher に接続されている証拠は見つからなかった。
`scripts/tsukuyomi_release/publish_bundle.py:109-128,319` と `scripts/public_base_runtime.py:60-73` は独自に size/hash を照合する。これらまで無検査とは結論しない。

### A04: published entry の hash/size 条件を構造 gate が強制しない

**変異入力で確認。** `scripts/check_model_sha256_manifest.py:96-114` は空 hash と placeholder を許容し、bytes と publish_status の組合せを検査しない。
一方、manifest `:28-29` は published entry の hash/size を検査すると説明している。

実 manifest を deepcopy し、`tsukuyomi-zs-v1` の `publish_status="published"` を保ったまま artifact を変更して `check_manifest()` に渡した。

| 変更 | errors | 判定 |
|---|---|---|
| `sha256=""` | `[]` | 成功 |
| `sha256="<computed-on-publish>"` | `[]` | 成功 |
| `bytes=-1` | `[]` | 成功 |
| bytes を削除 | `[]` | 成功 |
| 対照: `sha256="invalid"` | 不正 digest の error | 失敗 |

現在の manifest にこの変異を保存したものではない。実 entry の破損を発見したのではなく、回帰を止められない条件を再現した。

### A15: ONNX export の CI 保証と実際の検査範囲

**記載と対応 gate の不一致。** `docs/spec/onnx-export-contract.toml:191-224,263-266` は export ごとの roundtrip、ORT session、warmup、FP16 parity を CI で実行済みとする。
対応する `.github/workflows/model-quality-gate.yml:68` が呼ぶ `scripts/check_onnx_export_contract.py:36-49` は、opset の正規表現と `checker.check_model`／`shape_inference.infer_shapes` の文字列存在を検査する。
次の内容しかない scratch source でも `check_opset(...,15,...)` の結果は `[]` だった。

```python
OPSET_VERSION = 15
# onnx.checker.check_model
# onnx.shape_inference.infer_shapes
```

この検査の成功は artifact の生成・ロード・推論・FP16 比較の証拠にならない。
workflow 全体を検索しても、契約どおりの「毎 export に対応する一連の動的検証」への接続は確認できなかった。
ただし `public-base-runtime.yml` や `runtime-parity-deep.yml` 等の実モデル推論経路は別に存在する。リポジトリに動的推論 CI がないという指摘ではない。

## CLI・合成入口から成果物まで

以下 A05～A10 は parser・dispatch・writer のソース追跡による所見。今回これらの実モデル音声生成は行っていない。

### A05: Rust JSONL の文書と必須入力が異なる

`src/rust/piper-cli/README.md:79-84` は `text`, `speaker`, `language` を案内する。
実際の `src/rust/piper-core/src/input.rs:8-27` は `phoneme_ids: Vec<i64>` を必須とし、話者・言語は `speaker_id`／`language_id`。
`main.rs:764-789` はこれを `to_request()` へ渡す。
`{"text":"hello","speaker":1,"language":"en"}` は schema 上 `phoneme_ids` が欠落する。
未定義 field はテキスト音素化へ接続されていない。実 binary の error 文面を測った結果ではない。

### A06: Rust phoneme-silence は parse だけ

`src/rust/piper-cli/src/main.rs:344-355` は `_phoneme_silence_map` を parse/log するだけで、ログにも `parsed but not yet applied to audio` とある。
help `docs/reference/cli-help/rust.txt:38-40` と `docs/getting-started/binary-selection.md:21` は利用可能な無音制御として案内する。
format が正しくても、設定を音声に適用する経路がない。

### A07: Rust JSONL の出力先省略時に書き込み分岐がない

`main.rs:24-32` の出力引数は任意。JSONL の `:804-819` は stdout、output_dir、output_file の 3 分岐しかない。
すべて省略した場合の default 出力・error がなく、推論に成功すれば最後の `Ok(())` へ進む。
record に output_file があっても、directory 分岐に入らなければ使用されない。
text mode の default 動作を JSONL にも期待する利用者が、WAV を取得できない経路がある。

### A08: C# CLI の timing 出力は常に skip

`README.md:109` と help は音素 timing を機能として案内する。
`src/csharp/PiperPlus.Cli/Program.cs:1092-1100,1494-1501` は `--output-timing` 指定時に常に次の warning を出す。

```text
Warning: --output-timing specified but phoneme timing data is not available from this model. Skipping timing output.
```

`outputTimingPath` の参照は宣言とこの 2 分岐のみで、CLI から TimingWriter へ接続されていない。
Core の formatter が存在することと、CLI が timing file を出力することを分けて記載する必要がある。

### A09: Go timing は text mode のみ

`src/go/cmd/piper-plus/main.go:387` が唯一の `writeTiming` 呼出。
batch `:390-432` と JSONL `:435-476` は WAV を出力するが timing writer を呼ばない。
`src/go/README.md:18` と help は mode の制限を示していない。全 mode で対応するか、制限・非対応指定時の error を明記する必要がある。

### A10: Go/Rust の SSML parser と合成入口が未接続

`README.md:113,118` は Go/Rust の SSML 合成対応を案内する。
**両方に parser 自体は存在する。** Go は `src/go/piperplus/ssml/parser.go`、Rust は `src/rust/piper-core/src/lib.rs:47-50` の re-export。
通常の Go 合成 `src/go/piperplus/synthesize.go:146-171` は text を `PhonemizeWithProsody` へ直接渡す。
Rust `src/rust/piper-core/src/voice.rs:414-450` も同様で、コメントが SSML wrapper を G2P へ渡すとタグまで読み上げる問題を説明している。
通常 CLI／合成入口から SSML の segment・break・rate を適用する接続が確認できなかった。
自作 caller が parser を使用できることを否定する所見ではない。

### A16: Rust help の sv 欠落

`docs/reference/cli-help/rust.txt:31-33` は 7 言語を列挙し、`sv` がない。
`src/rust/piper-cli/src/main.rs:12-13,333-341` の実際の validation は `sv` を含む。
入力を拒否する不具合ではなく、help の案内漏れ。

## 公開配布物と consumer 案内

### A11: Rust 公開 binary の GPU 推奨が build feature と合わない

`docs/getting-started/binary-selection.md:21,49` は公開 Rust CLI を CUDA/CoreML/DirectML 用として勧める。
`src/rust/piper-cli/Cargo.toml:13-14` の core dependency は `naist-jdic`, `dict-download`, `onnx` のみ。
`.github/workflows/release-rust.yml:266` は次の build で GPU feature を追加しない。

```text
cargo build --release -p piper-plus-cli --target ${{ matrix.target }}
```

`src/rust/piper-core/Cargo.toml:36-39` と `gpu.rs` の provider は feature-gated。
v2.0.1 の公開 asset は Linux x64／macOS arm64／Windows x64 の各 1 種で、provider 別 variant はない。
したがって公開 binary を GPU 対応として選ばせる根拠が build recipe と一致しない。
`docs/guides/development/building-from-source.md:127-133` の feature を付けた source build は別経路として案内できる。
公開 binary を GPU 実機でロードする検証は未実施。

### A13: Swift G2P の ZIP サイズ

Release API の v2.0.1 asset metadata は次の値だった。

```text
libpiper_plus_g2p-apple-v2.0.1.xcframework.zip
size = 149575363 bytes = 約 142.6 MiB
```

`docs/guides/platform/swift-g2p-integration.md:25,55-56,89`、`examples/swift-g2p/README.md:60`、`docs/reference/swift-g2p.md:112` は約 3～5 MB、`docs/guides/platform/ios-integration.md:13,36` は約 6 MB と案内する。
Package.swift の URL/version と release checksum の対応には不一致を見つけていない。
ZIP は取得・解凍していないため、この値からアプリ増分、各 slice のサイズ、App Clip 制限超過を推測しない。

### A14: npm setup helper の古い asset 案内

`src/wasm/openjtalk-web/package.json:61` の `setup:wasm` は次を echo する。

```text
gh release download --repo ayutaz/piper-plus --pattern piper-plus-wasm-* -D dist/rust-wasm
```

v2.0.1 の公開 asset 一覧には該当 pattern がない。script 自体はダウンロードせず、メッセージと directory 作成だけを行う。
`README.npm.md` の npm 同梱 WASM を使う通常の consumer 経路が壊れているという所見ではない。

## 新規不具合としなかったもの

| 候補 | 採用しなかった理由 |
|---|---|
| ONNX input gate が dtype/rank/shape まで確認しない | 実際に誤った mask/prosody metadata を持つ 306-byte ONNX が names-only gate を通った。ただし workflow は input set 検査と明記し、契約も shape/type を ORT へ委譲する。追加検査候補であり、隠れた対応保証の違反とは数えない |
| CLI docs gate が新 flag や allowlisted flag 削除を通す | stale-only／C++ 文書と Python help の差を許す方針が workflow に明記されている。Python は text が positional なので `--text` の allowlist 自体は妥当 |
| CPU inference 用 uv sync が training/CUDA torch も解決する | 開発 workspace の現構成として確認。最小 CPU 環境の保証ではなく、依存分割は設計改善に当たるため今回の必須修正に含めない |
| 通常 uv run が以前の GPU extra を消す | 最小 project で反証。通常 run は残し、明示的 sync は extra を除く |
| Android full TTS AAR が未公開 | README は local build と `When published to GitHub Packages` を区別。Release に AAR がない事実だけで認証付き registry の不存在を判定できない |
| ホストで Go help／Python HTTP test が失敗 | 前者は CGO/ORT、後者は slowapi 未導入の環境条件。必要依存を持つ環境での製品不具合としては確認できない |

既知の Training Tab 旧引数、WASM 診断ページ ORT/PUA metadata、Python resolver の css10/flat-cache、C++ reference-audio 抽出未実装、mutation tool pin、native G2P／人手品質の検証範囲は新規所見に含めていない。

## 修正順序と受入条件

今回の目的は調査。以下は修正に進む場合の順序であり、実装完了の記録ではない。
新機能実装を必要としない文書修正で、公開済み機能と未接続機能の区別を先に正せる。

| 順序 | 対象 | 最小の対応 | 受入条件 |
|---|---|---|---|
| 1 | A01/A05/A11 | 正しい Python 呼出、実 JSONL schema、公開 CPU build と GPU source build の区別に案内を修正 | venv 未 activate の shell、parser、release build feature を使った例の照合 |
| 2 | A06～A10/A16 | 対応 mode・parser 単体・未実装 flag を明示し、過大な機能案内を除く | オプションの受理と成果物の生成を別々に確認。文書だけで実装済みに見せない |
| 3 | A02/A12 | GPU/WebUI の依存を矛盾なく解決する手順を用意 | 別の clean env で CPU/GPU ORT が一方だけ、HF Hub 制約内、uv pip check 成功。GPU 実起動は別証拠 |
| 4 | A03/A04 | artifact 階層を扱い、公式 artifact の不一致と published の未確定値を検出する | 正常・破損 hash、missing/negative bytes、published placeholder の各 negative test が意図どおり失敗 |
| 5 | A13/A14/A15 | 配布サイズ・入手先・CI が検証する範囲を現物へ合わせる | 固定 release metadata、存在する取得先、CI job と成果物の対応を明示 |

実装を増やす場合の試験は、Rust JSONL の出力先省略、各 CLI の timing 成果物、SSML break/rate、phoneme-silence の音声差分を対象にする。
名前・flag・formatter の存在だけを見る検査では代替しない。

## 再現コマンドと証拠保管

root checkout での主な確認コマンド。dry-run は環境変更を実施しない。

```powershell
uv lock --check
python -m piper_plus --help
uv run --no-sync python -m piper_plus --help
uv tree --locked --package piper-plus --depth 2
uv sync --dry-run --locked --extra inference-gpu --no-dev
uv pip install --dry-run -r src/python_run/requirements_webui.txt
uv run --no-project python -X utf8 scripts/verify_model_checksums.py --print-manifest
$auditRelease = Invoke-RestMethod 'https://api.github.com/repos/ayutaz/piper-plus/releases/tags/v2.0.1'
$auditRelease.assets | Select-Object name,size,browser_download_url
```

schema 互換・変異試験は tracked ファイルを変更せず、Python 関数 import、deepcopy、scratch copy で行った。
ローカルの追加証拠は ignored directory `output/docs-audit-20261015/third/` に保存した。これらは Git 配布物に含まれない。

| 証拠ファイル | 内容 |
|---|---|
| `checksum_probe.py` / `checksum-probe.json` | nested schema、正常／破損の小さい artifact、exit と warning |
| `manifest_update_probe.py` / `manifest-update-probe.json` | コピーだけを対象に更新 helper が無変更で exit 0 |
| `published_manifest_probe.py` / `published-manifest-probe.json` | published entry の 4 変異と不正 digest の対照実験 |
| `onnx_metadata_probe.py` / `onnx-metadata-probe.json` | 有効 ONNX だが誤った TTS metadata を names-only gate が受理 |
| `onnx-export-fake-source.py` | コメントの token だけで export 構造検査が通る入力 |
| `real-manifest-print.log` / `bare-python.log` | 実 manifest の missing、ホスト Python の import 失敗 |
| `gpu-sync-dry-run.log` / `webui-install-dry-run.log` | GPU と WebUI の依存変更計画 |
| `ort-dependency-tree.log` / `release-assets.json` | dependency tree、固定 release の asset metadata |
| `clean-install.md` / `entrypoints.md` / `ci-effectiveness.md` / `distribution.md` | 独立調査の一次メモ。採否・優先度は本書を正とする |

主な外部一次資料は [ONNX Runtime Python 導入案内](https://onnxruntime.ai/docs/get-started/with-python)、[GitHub v2.0.1 Release](https://github.com/ayutaz/piper-plus/releases/tag/v2.0.1)、[固定 tag の Release API](https://api.github.com/repos/ayutaz/piper-plus/releases/tags/v2.0.1)。いずれも調査日現在の内容を使用した。

## 未確認の範囲

- 実 GPU での ORT provider ロード、追加依存導入後の WebUI 操作。
- A05～A10 を実モデルで実行した音声・timing file の実測。
- 公開 Rust binary の GPU 実行、Swift archive の解凍サイズとアプリ組み込み後の容量。
- npm tarball 全内容の digest、認証付き Android GitHub Packages の full TTS AAR の有無。
- Raspberry Pi／Android／iOS 実機、音声品質・性能。今回 ARM64 の過去の QEMU 検証を再実行したものではない。

従って「全プラットフォームの全機能に漏れがない」という保証にはしない。ここで確認した案内と接続の不一致を解消した後、対象を絞った consumer 実行試験で確認する。
