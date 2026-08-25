# Changelog

All notable changes to piper-plus will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

<!--
  Breaking changes must be listed under `### Breaking` and each entry must
  include at least one `[label](docs/migration/v<X>-to-v<Y>.md#anchor)`
  link. See `docs/migration/README.md` for the anchor slug rules.
  `scripts/check_migration_xref.py` (workflow `Migration Guide Lint`)
  enforces this automatically.
-->

### Security

- WebUI: `src/python_run/requirements_webui.txt` の Gradio を `6.14.0` → `6.21.0` に更新し、 **CVE-2026-48545** (Gradio < 6.15.0 の Cookie Injection via Shared Proxy Client) を解消した。 同ファイルは README 5 言語版が `uv pip install -r` で直接案内しているユーザー向けの導入手順であり、 `docker/webui/Dockerfile:23` も同じファイルを COPY するため、 1 箇所の修正で手動導入と Docker イメージの双方に効く。 学習環境への影響は**なし** (`gradio` は `uv.lock` に含まれず学習クロージャ外)。 6.21.0 は `huggingface-space/requirements.txt` が既に採用済みで、 WebUI が使う Gradio API は `Blocks` / `Audio` / `Slider` 等のコアコンポーネントのみ。 既存の numpy 制約 (`>=1.26.4,<2.3`) のままで解決できることを `uv pip compile` で確認済み (numpy 2.2.6 に解決)
- CI: `Required Status Check Gate` (`.github/workflows/required_status_check_gate.yml`) に script injection があったのを修正。 `workflow_run` イベント経路で fork 側の branch 名 (`github.event.workflow_run.head_branch`) を `run:` ブロックへ直接展開しており、 git の ref 名は `$( )` や backtick を含められるため任意コマンドが実行可能だった。 `workflow_run` は fork PR 由来でも base repo の write context で発火し、 当 job は `pull-requests: write` を持つ。 さらに直前の `actions/checkout` が `persist-credentials: false` を指定していなかったため、 注入されたコマンドから `.git/config` 経由で `GITHUB_TOKEN` を回収できる状態だった (pwn-request パターン)。 同 repo 内の `pr-title-check.yml` / `pr-body-validate.yml` が既に採っている `env:` 経由で shell 変数として参照する形に統一し、 併せて checkout に `persist-credentials: false` を追加して多層防御とした (`check_required_gate.py` は stdlib `urllib` のみで `GITHUB_TOKEN` env から認証しており git credential helper を使わないことを確認済み)。 `.github/workflows/*.yml` の `run:` ブロック全件を走査し、 外部から制御可能な `github.event.*` フィールドを展開している箇所が他に無いことを確認済み

### Fixed

- CI: CodeQL の `py/log-injection` / `go/log-injection` を `query-filters` で除外した。 open だった 11 件を実コードで全数確認した結果、 いずれも untrusted 入力がログへ素通りする経路ではなかった。 (a) `voice.py` 5 件はログ対象が `cache_path` / `sentinel_path` で `--model` 由来の**起動時ローカルパス**、 リクエストデータではない (既に除外済みの `py/path-injection` と同じ「CLI tool only」の前提)。 (b) `multilingual.py` 3 件は `_LOGGER.debug("... %r ...", text)` の **repr 経由**で、 repr が改行を `\n` にエスケープするため log injection の主要ベクタ (偽ログ行の差し込み) が成立せず、 かつ DEBUG レベル。 (c) `training_manager.py` 2 件は CLI subprocess ラッパーで、 ユーザーは同じ CLI を直接起動できる立場 (既に除外済みの `py/command-line-injection` と同じ前提)。 (d) `server.go:147` は唯一の HTTP 経路だが **既に `req.Text` ではなく `len(req.Text)` を記録**しており、 `fmt.Errorf` を全数確認しても入力テキストを埋めるものは無く `slog` の structured logging が値を quote する。 個別 dismiss ではなくルール除外にしたのは、 同 config の `cpp/loop-variable-changed` が記録している経緯 (PR #434 で 87 件 bulk dismiss → PR #476 / #477 で同型パターンが再発 → ルール suppress へ切替) と同じ理由。 **トレードオフ**: 将来 `http_server.py` / `server.go` に本物の log injection が入っても検出しないため、 リクエスト由来の値をログへ出す変更は code review で担保する旨を config に明記した
- CI: `build-piper.yml` の OpenJTalk 辞書ダウンロードが **2 経路で silent failure** していたのを修正。 (1) Unix 側 `if curl -L -o naist-jdic.tar.gz "<sourceforge>"; then ... fi` は curl が非 0 で終わると (DNS 失敗 / TLS / 接続リセット / タイムアウト) install ブロック全体が skip され、 step は緑のまま `tar -czf` に到達する (`bash -e` 下で再現: 旧経路 exit 0 でアーカイブ step まで到達 / 新経路 exit 6 で停止)。 (2) HTTP 200 + 空ボディの場合、 bsdtar は 0 バイトの .tar.gz を **exit 0 で受理**するため `[ -d open_jtalk_dic_utf_8-1.11 ]` ガードが黙って copy を skip する (実測で `tar -xzf` の exit 0 と展開ディレクトリ不在を確認)。 Windows 側も curl / tar の終了状態を見ず、 展開失敗時に `Write-Host "Warning: Failed to extract..."` で続行していた。 **これがないと何が起きるか**: 辞書欠落パッケージがそのまま `piper-plus-cpp-*.tar.gz` / `.zip` になり、 `dev-build-all.yml` 経由で GitHub Release アセットとして公開される
- CI: 対策として `if` ラッパーを除去し、 取得元を他 4 ランタイム (`openjtalk_dictionary_manager.c` / `dictionary_manager.rs` / `DictionaryManager.cs` / `dict-loader.js`) と同じ canonical ミラー (`r9y9/open_jtalk` GitHub Releases) に統一、 同じ sha256 (`fe6ba0e4...`) を検証するようにした。 SourceForge はリクエストごとにランダムミラーへ 302 する chronic flake 源で、 かつリポジトリが 4 ランタイムで pin している sha256 と突合できなかった。 `--retry-all-errors` は付けていない (`-f` と併用すると 404 のような恒久エラーまでリトライして一過性 flake に偽装するため)。 Windows 側は `curl.exe` / `tar.exe` を明示し (PowerShell 5.1 fallback 時の `curl` → `Invoke-WebRequest` alias 衝突回避)、 `Write-Host "Warning"` を `throw` に置き換えた
- CI: アーカイブ作成直前に **packaged artifact manifest 検査**を追加した。 同 step には `|| true` / `2>/dev/null` / else なしの if が **13 箇所**あり、 コピー失敗はすべて緑のまま通る。 個別に潰すのではなく「入っているべきものが入っているか」を出荷直前に一度検査する (判定基準は `tools/build-openjtalk-dict-archive.sh:39-43` の既存慣行 — sys.dic / unk.dic が無ければ stripped とみなして exit — を踏襲)。 なお **espeak-ng-data は意図的に必須リストへ入れていない**: 上の copy ブロックは else なしの if/elif で silent skip するが、 C++ CLI は自前の 8 言語 G2P を使っており espeak にリンクしていない (`src/cpp` の espeak 参照はコメントのみ、 v1.13.0 の実配布バイナリ内の espeak 文字列は **0 件**、 同アセットに espeak-ng-data は同梱されていないが日本語以外も動作している)。 必須にすると実態と乖離して即座に赤くなる
- CI: `build-piper.yml` の Unix パッケージ step に `shell: bash` を追加し `-o pipefail` を有効化した。 既定 (shell 未指定) は `bash -e` で pipefail が無く、 `echo "<sha>  <file>" | sha256sum -c -` のようなパイプは右端の終了状態しか見ないため checksum 検証を取りこぼしうる (実測: `-e` のみでは継続到達 / `-eo pipefail` では exit 1)。 同 step 内の他のパイプも併せて硬化する。 `build-all-platforms.yml` の matrix に `fail-fast: false` を追加 (`dev-build-all.yml:213` と同じ理由 — Unix は `bash -eo pipefail`、 Windows は pwsh の throw と失敗の出方が OS で異なるため、 1 プラットフォームの一過性失敗で残り 2 job がキャンセルされると切り分け不能になる)
- CI: OpenSSF Scorecard の `Pinned-Dependencies` 所見のうち **GitHub Actions の pin 形式に関する部分**を code scanning へ上げないようにした (`scripts/filter_scorecard_sarif.py` を新設し `scorecard.yml` の upload 前に適用)。 Scorecard は action 参照が 40-hex SHA でなければ score 0 とするが、 本リポジトリは `scripts/check_action_pins.py` がフル SemVer (`@v1.2.3`) を「許可された pin 形式」と明文で定義し、 sliding major (`@v1`) のみを hard fail としている。 双方それぞれ一貫した基準だが両立せず、 結果として Scorecard の 937 所見中 **789 件 (84%) が「決着済みの方針差分」の反復**となり、 判断が必要な所見 — CodeQL 41 件と、 本リポジトリに方針が存在しない pip / container / npm pinning の 148 件 — を埋没させていた。 dismiss では解決しない: Scorecard の `partialFingerprints` は `primaryLocationLineHash` (行内容のハッシュ) であるため、 Dependabot が `actions/checkout@v6.1.0` → `@v6.2.0` と bump するだけで fingerprint が変わり GitHub が新規 alert を起票する。 実測でも 2026-05 に 679 件を `won't fix` で dismiss 済みだったにもかかわらず、 2026-08 時点で **321 箇所が同一 `path:line` で再 open** していた。 落とすのは `GitHubAction` 系のみで、 `pipCommand` / `containerImage` / `npmCommand` / `nugetCommand` / `goCommand` / `downloadThenRun` は本リポジトリに方針が無く Scorecard が唯一の追跡手段のため残す (方針の不在を沈黙で既成事実化しない)。 action pin の追跡は Scorecard ではなく `action-pin-gate` が担う — sliding major を hard fail にできる点で Scorecard より厳格で、 baseline 済みの例外も毎 run 報告する。 フィルタ自身が #628 / #629 と同じ「検査対象が消えたときに限って緑になる」欠陥にならないよう 4 つのガードを実装した: (1) `PinnedDependenciesID` が `tool.driver.rules` に宣言されていること (upstream の rule rename 検出)、 (2) 全 `PinnedDependenciesID` 所見が既知の message 書式に一致すること (書式変更で分類不能になった所見を無言で通さない)、 (3) 対象 rule 以外の所見が減っていないこと、 (4) フィルタ後に所見が 0 件になったら書き出しを拒否すること (空 SARIF は全 alert を一括 close させ、 クリーンなスキャンと区別が付かない)。 drop 0 件はエラーにしない (完全 SHA pin 済みリポジトリの正常な姿であり、 ガード 1-2 が drift と区別する)。 scorecard.dev へ publish される公開スコアは action 内部で算出されるため本フィルタの影響を受けない。 未フィルタの SARIF は従来どおり artifact として保持し、 何が落ちたかを監査できるようにしている
- CI: `Security Audit` の `pip-audit (Python)` job で、 コメントと doc が実挙動と食い違っていたのを訂正 (実行内容の変更はゼロ、 コメントと doc のみ)。 (1) `Audit root requirements` の直上に `# PR は warning、schedule/push は fail。` とあったが、 同 step は 26 行下で無条件 `continue-on-error: true`。 これは #401 (`692cb3f6`, 2026-05-10) 当時の tier 記述が、 root を informational へ移した #628 (`df2d3f94`) で取り残されたもの。 (2) torch `PYSEC-2025-194` を「`last_affected: 2.6.0-NA` の上流データ不整合で解決版 2.11.0 は本来この範囲外」と説明していたが、 alias の `GHSA-rrmf-rvhw-rf47` が 2026-07-17 に `fixed: 2.13.0` へ更新され (OSV API の `modified` で確認)、 OSV 経由ではこちらの range が採られるため現在は**実際に報告されている**。 PYSEC レコード自体は `last_affected: 2.6.0-NA` のままなので、 PYSEC だけを見ると陳腐化に気付けない
- CI: 同 job の「blocking へ戻す条件」が **達成不能だった**のを撤回し、 実測値と実際の前提条件に置き換えた。 旧記述は「transformers / hf-hub 移行が完了し findings が解消した時点で blocking へ戻す」だったが、 2026-08-25 に CI と同条件 (linux / py3.13) で実測すると root クロージャは `Found 77 known vulnerabilities, ignored 2 in 8 packages` (aiohttp 28 / pillow 26 / nltk 10 / transformers 7 / setuptools 2 / msgpack 2 / torch 1 / click 1) で、 transformers を上げても 7 件しか減らない。 **これがないと何が起きるか**: 書かれた条件を信じて `continue-on-error` を外すと dev への push が初日から恒久 red になる。 実際に blocking 化するには (a) 監査対象を `uv pip compile` の再解決から `uv export --locked` (= `uv sync` が実際に入れるもの) へ変える、 (b) 8 パッケージの実 finding を bump で潰す、 の両方が要り、 後者は学習環境の依存に波及する
- CI: 上記に関連して、 本 step が `uv.lock` を読まず実行時に PyPI から再解決する事実を job レベルコメントに明記した。 findings がリポジトリ無変更のまま増減する (#628 執筆時点の 5 advisory から本コメント執筆時点の 77 findings へ) ため、 件数が動いたときにまず疑うべきは上流 advisory であってコード変更ではない
- Docs: `docs/getting-started/troubleshooting.md` の `Security Audit / pip-audit` 節が「job は push で fail する」と書いていたのを、 fail するのは `Audit src/python_run` step のみで `Audit root requirements` はどのイベントでも job を落とさないことが分かるよう訂正
- CI: `scripts/check_ort_version_drift.py` が **一度も機能したことがなかった**のを修正。 3 層で無効化されていた。 (1) `SPEC` が `docs/spec/ort-versions.md` を指す一方、 ファイルは `ea994a2c` (#493) で `docs/reference/` へリネーム済みで、 実行すると `WARNING: spec missing` → **exit 0**。 (2) パスを直しても、 pattern がマッチしない target を無言で `continue` していた。 6 target のうち 2 つはマッチしようがなく (`src/python_run/setup.py` は Issue #418 で pin が消え、 `src/rust/piper-wasm/Cargo.toml` はそもそも `ort` に依存しない)、 残り 4 つだけを検査しながら成功を報告していた。 (3) `model-quality-gate.yml` 側も `continue-on-error: true` を持ち、 しかもこれは workflow 初 commit `692cb3f6` (#401) から付いていたため **この step は原理的に job を落とせたことがない**。 **これがないと何が起きるか**: doc の Python 2 行が `>=1.20.0` のまま凍結し、 実 pin `>=1.26.0` との乖離が誰にも検出されない (doc 内の `1.26.0` 出現数は **0** だった)。 修正後の gate は実際にこの drift を 4 件検出する
- CI: 同 gate の比較ロジックが **不健全だった**のを、 doc 表の行単位パースに作り直した。 旧実装は `version not in spec_text`、 すなわち 140 行の doc 全文に対する素の部分文字列一致で、 実測すると `'2.0.0-rc.1' in doc` → True (rc.13 → rc.1 の downgrade が通る)、 `'1.20.0' in doc` → True (C++ canonical 行が 6 行あるため **どの runtime を 1.20.0 に落としても通る**)、 `'1.24.3' in doc` → True (Go を C# の値にしても通る)、 `'1.2' in doc` → True (切り詰めた版でも通る)。 実質「その文字列が doc のどこかにある」ことしか見ていなかった。 新実装は `## Current versions` 表を行ラベルで引き、 その行の `ORT Version` セル内にトークンとして完全一致で含まれることを要求する
- CI: 同 gate から `return 0` の逃げ道を全廃した。 spec 不在 / 表が見つからない / 行ラベルが表に無い / target ファイル不在 / **pattern が 1 件もマッチしない** / `ROW_CHECKS` の件数が `EXPECTED_CHECK_COUNT` と不一致、 のいずれも exit 1。 特に「pattern がマッチしない」は #628 / #629 と同じ「守っている対象が消えたときに限って緑になる」経路そのものだった。 併せて `model-quality-gate.yml` の `continue-on-error: true` を削除し、 同 job に gate 自身の self-test step を追加した
- CI: `model-quality-gate.yml` の `on.pull_request.paths` に実 pin サイト 6 件 (`src/python/pyproject.toml` / `src/python_run/requirements{,_gpu}.txt` / `src/go/go.mod` / `PiperPlus.Core.csproj` / `openjtalk-web/package.json`) と gate の test を追加。 特に `src/go/go.mod` が無いと、 `dependabot.yml` の gomod ecosystem による `onnxruntime_go` bump が PR で本 gate を起動せずに merge され、 その push で初めて dev が赤くなる遅延経路が残る
- Docs: `docs/reference/ort-versions.md` の Python 2 行を実 pin (`>=1.26.0`、 gpu extra は `onnxruntime-gpu>=1.20.1,<1.26`) に更新し、 Package/Source 欄から `setup.py` を削除 (Issue #418 以降 pin を持たない)。 `scripts/check_ort_versions.py` の docstring と `src/python_run/pyproject.toml` の `gpu` extra コメント (`>=1.26.0,<2` と書きつつ実体は `>=1.20.1,<1.26`) も実態に合わせた。 いずれもコメント・doc のみで、 `uv pip compile --all-extras` の解決結果 143 パッケージが変更前後で完全一致することを確認済み
- CI: CodeQL の `paths-ignore` (`.github/codeql/codeql-config.yml` の `build/**` / `**/build/**`) が **build-mode: manual の compiled language には仕様上まったく効かない**まま、 効いているつもりの除外として置かれていたのを修正。 GitHub Docs は paths / paths-ignore が使えるのを interpreted language と「コードを build しない」compiled language に限り、 build する場合は "you must specify appropriate build steps in the workflow" と明記している。 本 repo の matrix では cpp / csharp / kotlin の 3 つが `build-mode: manual`。 **これがないと何が起きるか**: `codeql.yml` の in-tree build (`-B build`) が展開する vendored fmt (`cmake/ExternalDeps.cmake` の `PREFIX "${CMAKE_CURRENT_BINARY_DIR}/f"`) と、 CodeQL の C# tracer が強制注入する `-p:EmitCompilerGeneratedFiles=true` の出力 (`obj/**/generated/*.g.cs`) が解析対象になる。 実測で CodeQL alert 全 851 件 (open 41 / dismissed 664 / fixed 146) のうち **256 件 (30%) がビルド生成物由来**で、 その大半は手動 dismiss で処理されていた
- CI: 対策として rule 全体の suppress ではなく **生成物を source root の外へ出す** 方式を採った (CodeQL は source root 外の結果を drop する)。 C++ は build tree を `${RUNNER_TEMP}/codeql-cpp-build` へ、 C# は `-p:ArtifactsPath` で obj/bin ごと外へ出す。 `ArtifactsPath` は `CompilerGeneratedFilesOutputPath` より広く、 `GlobalUsings.g.cs` / `AssemblyInfo.cs` / `XunitAutoGeneratedEntryPoint.cs` も同時に外へ出る (worktree 上の実ビルドで source tree の obj/bin が 0 件、 生成 `.g.cs` 4 件がすべて ArtifactsPath 側に出ることを確認済み)。 なお `ArtifactsPath` は **`codeql.yml` のコマンドラインでのみ**渡す — `src/csharp/Directory.Build.props` に置くと bin/ も移動し、 `cli-help-extract.yml:116,180` と `multi-runtime-rtf.yml:200` が hard-code する `bin/Release/net10.0/PiperPlus.Cli.dll` が壊れる
- CI: 再発防止に 2 段の assert を追加。 (1) ビルド生成物が source root に残っていないことを確認する step (ディレクトリ名に依存せず `CMakeCache.txt` / `obj|bin` の実在で判定し、 「ビルドが走った」positive assertion も併せて行うため、 ビルド未実行を「漏れなし」と取り違えない)。 (2) **SARIF の `artifactLocation.uri` に `build/` / `/obj/` / `android/**/build/` が現れたら fail する outcome ベースの guard**。 filesystem チェックは proxy にすぎず、 tracer の injection 追加・新規 source generator・Kotlin 経路の変化のいずれで壊れても SARIF 側なら赤くなる。 kotlin job も対象に含めた (gradle が `android/*/build/generated/` に生成ソースを吐く同型の潜在欠陥)
- CI: `.github/codeql/codeql-config.yml` のコメントから hedge を排除し、 効かないものを「効かない」と明記した。 `src/cpp/json.hpp` の除外は build-mode: manual では効かず、 in-source の vendored single-header なので build tree の out-of-tree 化でも救済されない (該当 137 件は dismiss 済み、 恒久対策は別途)。 `build/**` / `**/build/**` は tracked が `build-*.sh` の 3 件のみで CodeQL の解析対象言語に該当せず実質 inert である一方、 `**/dist/**` は tracked 7 件に対して有効。 実在しないパス `src/cpp/openjtalk/**` (git 履歴上も存在しない) は削除した。 併せて、 build tree 側に first-party コードが移動した場合に解析カバレッジが無警告で消える **逆方向の false-negative** を SARIF guard が検知しないことも明記した
- G2P (npm): `@piper-plus/g2p` の辞書自動ダウンロードの既定 URL (`src/wasm/g2p/src/dict-loader.js`) が **HTTP 404** だったのを修正。 `https://github.com/ayutaz/piper-plus/releases/download/dict-v1.0.0/open_jtalk_dic_utf_8-1.11.tar.gz` を指していたが、 `dict-v1.0.0` タグ自体が存在しない (`api.github.com/repos/ayutaz/piper-plus/releases/tags/dict-v1.0.0` → 404、 アセット URL も 404)。 **これがないと何が起きるか**: 辞書を明示指定せずに `@piper-plus/g2p` の日本語 G2P を使うと、 辞書取得が必ず失敗する。 同ファイルの `DICT_SHA256` は canonical (`fe6ba0e4...`) と既に一致しており、 他 3 ランタイム (`dictionary_manager.rs` / `DictionaryManager.cs` / `openjtalk_dictionary_manager.c`) はすべて r9y9 の canonical URL を使っていた — **URL のこの 1 行だけが取り残されていた**。 canonical URL に揃え、 実 DL して sha256 が定数と一致すること・アーカイブ内の `TAR_ROOT_DIR` と 8 ファイルが `DICT_FILES` と一致することを確認済み
- CI: `Required Status Check Gate` が **監視対象 spoke の実行中を hard fail として扱っていた**のを修正 (`scripts/check_required_gate.py`)。 本 gate は監視対象 5 spoke の `workflow_run: completed` ごとに発火するため、 構造上「他の spoke がまだ走っている」瞬間に必ず起動する。 `run.status != "completed"` を `bad` に積んで exit 1 していたので、 1 push あたり最後の 1 回を除く全発火が赤くなっていた (修正直前の 60 run で failure 38 / success 22、 dev の SHA ごとに failure 2〜7 + success 1。 `f14b8f76` は 7 赤 + 1 緑)。 最終発火は権威があり緑なので merge は妨げないが、 Actions タブが常時赤で埋まり **本物の gate 失敗が見分けられない**状態だった。 未完了 spoke を `pending` として `bad` から分離し、 `pending` のみなら deferred (exit 0) として報告する。 最後に完了する監視対象 spoke が必ず最終発火を起こし、 その時点で他の全監視対象 spoke は完了済みなので権威ある評価は常に行われる (既存の `--branch-for-supersede` が「head_sha が古い」ケースだけを救っていたのと同じ理屈を、 「spoke が実行中」ケースにも適用した)。 `bad` / `missing` が 1 件でもあれば pending の有無に関わらず即座に fail するため、 本物の失敗の検出は遅れない
- CI: `Ruff Version Sync Gate` が **6 サイトを検査すると謳いながら 5 サイトしか見ていなかった**のを修正 (`scripts/check_ruff_version_sync.py`)。 site 一覧に残っていた `.github/workflows/ci.yml` は PR #462 (`36e40904`) が「python-lint.yml と重複」として ruff job を削除済みで、 `ruff==` を 1 つも含まない。 `mode == "single"` はマッチ 0 件を無言で読み飛ばす実装だったため、 gate は `Found 5 ruff pin site(s)` / `OK all sites pin ruff==0.15.15` と出して exit 0 していた。 同じ沈黙は `python-lint.yml` が `pip install ruff==` を失った場合にも起き、 **守っている pin が消えたときに限って gate が緑になる**。 実測: `python-lint.yml` から ruff 行だけを落とした fixture に対し 修正前 exit 0 (`OK all sites pin ruff==0.15.15`) / 修正後 exit 1。 stale な ci.yml サイトを削除し、 各サイトに期待マッチ数 (`EXPECTED_PIN_COUNT`) を宣言させて 過不足を hard fail にする。 workflow の job 名 (`6 ruff pin sites agree` → `5 ...`)、 paths filter、 CLAUDE.md の「6 箇所」記述も 5 に揃えた
- CI: `.github/labels.yml` が宣言する label が **1 件もリポジトリに存在しない**まま、 CI 設定が 13 個の label を文字列参照していたのを修正。 `scripts/check_label_references.py` (`Extended contract gates` の `label-refs`) を新設し、 `.github/dependabot.yml` / workflow / `scripts/first_pr_fast_lane.py` が名指しする label が全て `.github/labels.yml` に宣言済みであることを検査する (40 参照 / 13 宣言)。 実害: (1) dependabot が 11 ecosystem 全てで `dependencies` / `automated` を要求しており、 直近 5 件の bot PR (#607 / #609 / #611 / #614 / #615) は全て label ゼロで着弾していた。 (2) `security-issue-routing.yml` は `set -euo pipefail` 下で `gh issue edit --add-label "needs-triage,roadmap"` を実行するが、 `gh` は未知 label でエラーを返すため security issue の routing step 自体が落ちる。 (3) `stale.yml` の `exempt-issue-labels` が `help-wanted` と綴っていた一方 実在 label は `help wanted` (空白区切り) で、 この exemption は一度もマッチしていなかった (label 名は大小文字・空白を区別する)。 (4) `first_pr_fast_lane.py` の `run-full-gate` (contract gate を blocker に戻す唯一の脱出口) も不在だった。 参照 0 件になった場合も fail させ、 抽出ルールの陳腐化が緑で通らないようにしている
- CI: `.github/labels.yml` が適用手順として案内していた `gh label sync -f` が **存在しないサブコマンド**だったのを修正 (`gh label` は list / create / edit / delete / clone のみ)。 カタログが一度もリポジトリへ適用されなかった原因。 `python scripts/check_label_references.py --emit-create-commands` が `gh label create --force` 行を生成する形に置き換えた (`--force` は既存 label を上書き更新するため再実行可能、 削除は一切行わない)
- CI: codespell の pin が `.pre-commit-config.yaml` (`rev: v2.3.0`) と `.github/workflows/codespell.yml` (`codespell==2.4.2`) で ずれていたのを 2.4.2 に統一。 codespell は版によって辞書エントリが増減するため、 drift は「ローカル pre-push は緑 / CI は赤」を生む。 workflow 側のコメントが `.pre-commit-config.yaml currently uses codespell 2.4.x` と 事実と異なる記述をしていたのも訂正した
- CI: `Security Audit` の `pip-audit (Python)` job が、 独立した 2 つの欠陥によって「dev への push を毎回赤くしながら、 root が宣言する依存は 1 パッケージも audit していない」状態になっていたのを修正。 (1) `Audit src/python_run` step の `run:` がプレーンスカラーだったため、 継続行の `\` が YAML の folding で畳まれ、 先頭にスペースの付いた 1 語 `" --ignore-vuln"` としてリテラルに pip-audit へ渡っていた。 argparse はこれを positional (`project_path`) と解釈し `argument project_path: not allowed with argument -r/--requirement` (exit 2) で毎回失敗する。 `--ignore-vuln` を 2 行目として追加した #589 (2026-06-30) からの回帰で、 PR では `continue-on-error: ${{ github.event_name == 'pull_request' }}` により job が緑に見えるため約 8 週間表面化しなかった。 `run: |` の block scalar に変更する。 (2) job に `uv` を install する step が存在せず (ubuntu-24.04 runner image に uv は同梱されていない)、 `Audit root requirements` step の `pip-audit --requirement <(uv pip compile pyproject.toml 2>/dev/null)` が **常に空の requirements を audit** していた。 command-not-found → `2>/dev/null` でエラー破棄 → process substitution が空を返す → pip-audit が 0 件に対して `No known vulnerabilities found` を出して exit 0、 という経路のため `||` 右側の引数なし `pip-audit --strict` へのフォールバックは一度も発火していない。 v1.12.0 (#375、 2026-05-04) で本 step が導入されて以来 約 3.5 ヶ月、 root の依存クロージャは CI で一度も audit されていなかった (silent false-negative)
- CI: 上記に伴い `Audit root requirements` から「失敗を握り潰す」3 層 (`2>/dev/null` / process substitution / `|| pip-audit --strict`) を削除し、 `astral-sh/setup-uv@v6.8.0` の追加と `${RUNNER_TEMP}` 上の実ファイル経由に置き換えた。 実ファイル経路であれば default shell (`bash -e`) が uv の失敗時点で step を止める (uv を PATH から外した再現で exit 127)。 併せて workspace member 3 件を `--no-emit-package` で除外し (`-e file:///...` 行は pip-audit が版を決定できず `--strict` が落ちる)、 `--disable-pip --no-deps` を付けた (compile 出力は `torch==2.11.0+cu128` を含む一方 per-package index は requirements.txt 形式で emit されないため、 pip resolve 経路に落とすと PyPI から解決できず hard fail する)。 なお引数なし `pip-audit --strict` は working-directory に依存せず runner のグローバル Python 環境を audit する挙動で、 同 job の `Audit src/python_run` 側コメントが PR #447 後の実例を挙げて明示的に避けているものだった
- CI: 上記 2 件の修正により `Audit root requirements` が実際に失敗しうるようになった結果、 GitHub Actions の既定動作 (step 失敗時に後続 step を skip) で **配布 wheel を監査する `Audit src/python_run` が丸ごと実行されなくなる** 経路が生じたため、 同 step に `if: ${{ !cancelled() }}` を付与した。 root 側 (非頒布の train/dev クロージャ) の advisory 1 件で production 依存の監査が消えるのは、 本 PR が塞いでいる「監査が黙って 実行されない」欠陥と同じクラスにあたる。 workflow_dispatch 実測で root step 失敗時に step 5 が `skipped` になることを確認済み
- CI: `pip-audit (Python)` の tier を **監査対象が頒布物かどうか** で分け直した。 従来は「PR は warning / push・schedule は block」というイベント基準の 2 階層だったが、 上記修正で root step が実際に依存を解決するようになった結果、 **publish されない workspace meta (`[tool.uv] package = false`) の dev/train クロージャが dev push を block する**構図になった。 CONTRIBUTING.md の License Policy と `Audit src/python_run` 側のコメントはいずれも規制/監査のスコープを piper-plus が頒布する ものに限ると明記しているため、 配布 wheel を監査する `Audit src/python_run` は blocking の まま残し、 `Audit root requirements` を informational (`continue-on-error: true`) に変更した。 findings はログに全件出るため `--ignore-vuln` による抑止とは異なり何も隠さない。 現在 root が報告するのは setuptools PYSEC-2026-3447 (torch 2.11 が `setuptools<82` を課す 一方 fix は 83.0.0、 cu128 index の torch 上限も 2.11.0 のため構造的に解けない)、 transformers PYSEC-2026-2288 / 2289 / 2290 / PYSEC-2025-217 (fix の `transformers>=5.3.0` が `huggingface-hub>=1.3.0` を要求し hf-hub の major 移行を伴う)、 および torch PYSEC-2025-194 (`last_affected: 2.6.0-NA` という PEP 440 不正値による上流データ不整合で、 解決版 2.11.0 は 本来この範囲外) の 6 件。 移行完了後に blocking へ戻す
- CI: GitHub Actions の pin 安全ゲート (`scripts/check_action_pins.py`) が、 検査対象の `uses:` 行の **52% を素通りしていた**問題を修正。 `USES_RE` が `^\s*uses:` だったため YAML のリスト形式 (`- uses: foo/bar@v1`、 step の書き方としては圧倒的多数) にマッチせず、 806 行中 388 行しか分類されていなかった。 結果として 17 workflow に散らばる 38 件の sliding-major 参照 (`Swatinem/rust-cache@v2` × 23 等) が不可視のまま、 ゲートは `OK no new sliding-tag references.` を出して exit 0 していた。 これは本ゲートの存在理由である PR #414 の事故 (`sigstore/cosign-installer@v4` が upstream で削除され 7 job が同時に落ちた) と同じクラスの参照である。 併せて (1) 値が quote されている場合に version が `v6'` と読まれ hard FAIL が WARN に無言で降格する経路を封じ、 (2) 探索対象を `*.yaml` と `.github/actions/**/action.yml` (pre-commit hook の `files:` が以前からカバーを主張していたが実装が伴っていなかった) へ拡張し、 (3) `run: |` 等の block scalar 内の `uses:` を誤検出しないようにした。 新たに可視化された 5 参照は `scripts/action_pins_baseline.txt` へ根拠付きで grandfather している (SemVer への移行は別 PR)
- CI: 上記ゲートが「探索結果 0 件」を「違反なし」として exit 0 していた fail-open を閉じた。 workflows ディレクトリが存在しない / リネームされている場合や、 正規表現が壊れて 1 件も収集できない場合に `OK ... (0 total uses)` と表示して成功扱いになっており、 本ゲートが塞ごうとしている「盲目を成功として報告する」欠陥そのものを再現していた。 併せて `tests/scripts/test_check_action_pins.py` を新規追加し、 `Action Pin Safety Gate` workflow から実行するようにした (`tests/scripts/` は `pytest.ini` の `testpaths` に含まれず、 従来どの CI job からも実行されていなかった)
- CI: Trivy コンテナスキャンの CRITICAL ゲートが構造上 no-op で、 一度も発火できていなかった問題を修正。 `trivy-container-scan.yml` の 2 箇所 (`scan` / `scan-heavy`) にあった inline python heredoc は severity を `runs[].results[].properties.tags` から読んでいたが、 Trivy は severity tag を `runs[].tool.driver.rules[].properties.tags` 側に置き、 `results[].properties` には `github/alertNumber` / `github/alertUrl` しか載せない。 実 SARIF 3 本で確認したところ tag を持つ result は 188 件中 0 件、 rule 側は 46 件中 46 件で、 CRITICAL カウンタは常に 0 に固定されていた。 解析ロジックを `scripts/check_trivy_sarif.py` に集約し、 rule join (`ruleId` / `rule.id` → `ruleIndex` / `rule.index`、 `tool.driver.rules` と `tool.extensions[].rules` の双方) と severity 解決 (rule tags → result tags → message.text → CVSS band) を実装したうえで、 severity 別 breakdown を必ず出力するようにした (CRITICAL=0 の run でも「ゲートが実際に数えた」ことがログで監査できる)。 併せて SARIF の欠損 / 破損を exit 2 の明示エラーに変更した (SARIF は直前の step が生成するため、 欠損は「所見なし」ではなくスキャン破損を意味する)
- CI: 上記ゲートの単体テスト (`tests/scripts/test_check_trivy_sarif.py`、 21 ケース) を追加し、 `Trivy Container Scan` workflow に専用 job として登録した。 `tests/scripts/` は `pytest.ini` の `testpaths` に含まれておらず、 従来どの CI job からも実行されていなかった。 旧実装の読み方 (result 側 tags) への回帰と、 index join 経路の欠落を検出する
- 学習ツール: `piper_train.tools.batch_spectrograms._save_spec` が、 一時ファイルの作成そのものに失敗した場合に `UnboundLocalError` を投げて本来のエラーを覆い隠していた問題を修正。 `tempfile.mkstemp` を、 その戻り値 `tmp_path` を参照する cleanup ハンドラと同じ `try` に置いていたため、 mkstemp が失敗 (ENOSPC / EACCES / 親ディレクトリ不在) すると except 側で未束縛の `tmp_path` に触れていた。 併せて、 例外を無言で握り潰していた箇所に同 file の `_load_pt` と同じ粒度の warning ログを追加し、 `_save_spec` の戻り値を成否 bool にして `run()` が失敗を `skipped` に計上するようにした (従来は全書き込みが失敗した batch でも `processed=N skipped=0` と報告され、 1 件も書けていないことが表に出なかった)
- CI: distroless trial イメージ (`Dockerfile.cpu.distroless`) で `import onnxruntime` が SIGSEGV (exit 139) し、 `src/python/**` を触る全 PR がブロックされていた問題を修正。 ORT 1.29 が import 時に新設した device discovery (`device_discovery.cc`、 `/sys/devices` を走査して PCI bus ID を読む) が distroless の最小ファイルシステム上でクラッシュする。 本イメージ限定で `onnxruntime<1.29` に上限を設ける (canonical `Dockerfile.cpu` では ORT 1.29 が正常動作することを実測で確認済みのため、 そちらと通常のインストールは巻き込まない)。 シンボル欠落 / ライブラリ欠落 / インタプリタのパッチレベル差 / 実行ユーザー / seccomp はいずれも実測で棄却済み (根拠は Dockerfile のコメントに記録)。 併せて smoke test に `-X faulthandler` を追加し、 次に native crash が起きた際に `exit 139` だけでなく Python トレースバックが出るようにした。 「nonroot 65532 で動く」という誤ったコメントも実測値 (uid 0) に訂正
- 開発ツール: `.claude/hooks/guard-bash.sh` の `is_in_skill` が、 同一セッションで skill を再呼び出しした際に harness が挿入する `(Re-invocation of /<name> — ...)` メタ行 (`"isMeta":true`) を「新しいユーザー入力」と誤判定し、 **2 回目以降の `/create-pr` を常に deny** していた問題を修正 (1 セッションで複数 PR を出す流れが丸ごと塞がる)。 併せて `.claude/hooks/test-guard-bash.sh` の「許可」ケースが exit code しか見ておらず (hook は deny 時も exit 0 で JSON を stdout に出すため) **全て空振りしていた**のを、 出力が空であることまで検査するよう強化。 この振る舞いテストを pre-commit gate (`guard-bash-behaviour`) として登録し、 shellcheck では原理的に検出できない判定ロジックの回帰を commit 時点で捕まえるようにした
- ドキュメント: `docs/guides/development/pretrained-models.md` の 6lang base model 記述を実態に合わせて修正。 HF `ayousanz/piper-plus-base` の `model.ckpt` は 2026-05-03 に HiFi-GAN 版から **MB-iSTFT-VITS2 版** (75 epoch scratch、 `epoch=74-step=500034`) へ差し替え済みだが、 表が「6-Language Base (HiFi-GAN)」、 注記が「MB-iSTFT 版は未アップロード」のまま残っていた。 併せて `dev` (v2.0) では `model_g.dec.cond` の size mismatch で読み込めないこと ([Issue #616](https://github.com/ayutaz/piper-plus/issues/616)) と、 互換タグ `v1.13.0` を使う回避策を明記
- `notebooks/finetune.ipynb`: HF に存在しないファイル名 `epoch=74-step=504712.ckpt` を DL しようとして 404 で失敗していたのを `model.ckpt` に修正。 併せて (1) 公開中の ckpt と互換なリリースタグ `v1.13.0` を固定 clone するよう変更 (`dev` は Multi-scale FiLM 導入で decoder 形状が変わり ckpt を読めない)、 (2) `phoneme_id_map` / `num_symbols` を `get_phoneme_id_map()` (KO/SV を含む 8 言語統合マップ、 185 symbol) ではなく HF `config.json` (173 symbol) から取得するよう変更し、 `model_g.enc_p.emb.weight` の 173 vs 185 size mismatch を解消
- CI: `_build-test-cpp.yml` のテストモデル取得 step を削除。 `https://huggingface.co/ayousanz/piper-plus-base/resolve/main/multilingual-test-medium.onnx` は 404 を返すようになっていたが `curl ... || true` で握り潰されており、 integration test がモデル無しで黙って劣化しうる状態だった。 実際には `test/models/multilingual-test-medium.onnx` は LFS ではない通常の blob として commit 済みで checkout 時点から存在するため、 cache + download をまとめて削除し、 存在確認して欠けていたら fail-fast する step に置き換え
- 学習: CPython 3.13 で `torch.load` が既存 ckpt を `UnpicklingError: GLOBAL pathlib.PosixPath was not an allowed global` で拒否する問題を修正。 `torch.serialization.add_safe_globals([cls])` (bare 形式) は登録キーを **読み手側の** `cls.__module__` から導出するが、 unpickler は **書き手側が記録した文字列**を引く。 CPython 3.13 が具象 path クラスを `pathlib._local` へ移した (3.14 で `pathlib` に復帰) ため両者が一致せず、 3.12 以前で保存した ckpt が 3.13 で読めなくなっていた (逆方向も同様)。 `piper_train._compat` が `pathlib` / `pathlib._local` の両綴りを `(callable, name)` タプル形式で明示登録するようにし、 `weights_only=False` 経路用の Windows alias も両モジュールへ適用する。 併せて `piper_train/__main__.py` と `scripts/convert_multi_to_single_speaker.py` にあった同ロジックの複製 (drift 元) を canonical 実装への委譲に置き換え、 CI で 1 度も実行されていなかった `tests/test_compat.py` に `unit` マーカーを付与
- 契約: `docs/spec/phoneme-set-version.toml` が `num_symbols = 173` を「IMMUTABLE」と宣言する一方、 実コードの `get_phoneme_id_map("multilingual")` は #300 (Swedish 追加) 以降ずっと 185 を返しており、 仕様と実装が乖離していた問題を修正。 原因は gate (`scripts/check_phoneme_set_version.py`) が toml の自己整合と `pua.json` の entry 数しか見ておらず、 **インベントリを実際に構築する関数を一度も呼んでいなかった**こと (契約自体も `pua.json` + 公開モデル config を書き写して作られており、 当初からコードを参照していなかった)。 加えて pre-commit の `files` regex に `id_maps.py` が含まれておらず、 **インベントリ本体を編集しても発火する hook が 1 つも存在しなかった**
- 契約: 単一 pin をやめ、 live inventory (185 / `symbol_set_version = "1.1"`) と出荷済み snapshot (173 / `"1.0"`) を分けて表現するようにした。 両者は append-only な関係であることを実測で確認済み (`sha256(live[:173])` が HF 公開モデルの `phoneme_id_map` と完全一致)。 gate は (1) live の長さ、 (2) live 全体の digest (並べ替え検出)、 (3) 各 snapshot が live の厳密な prefix であること、 を検査する。 長さのみの検査では v1.12.0 が実際に出荷した「185 のまま id 94/149/153 が公開モデルと食い違う」ケースを検出できない
- テスト: `tests/test_swedish_phonemizer.py` の `assert len(id_map) > 180` / `>= 173` という緩い assert (Swedish 12 記号の追加を通した張本人) を、 契約の厳密値 + digest 照合に置換。 `src/python/g2p/tests/test_phoneme_inventory.py` を新規追加し、 id の連続性・snapshot prefix 不変・合成言語コード間の一致を pin
- 学習 / エクスポート: 公開ベースモデル (`ayousanz/piper-plus-base`) を含む Multi-scale FiLM 導入前 (PR #579 以前) の MB-iSTFT ckpt が `RuntimeError: size mismatch for model_g.dec.cond.weight` で読み込めない問題を修正 ([Issue #616](https://github.com/ayutaz/piper-plus/issues/616))。 PR #579 が `MBiSTFTGenerator.cond` の出力チャネルを 2 倍 (FiLM の scale + shift) に拡幅したため、 ONNX エクスポート / FT (`--resume-from-multispeaker-checkpoint`) / 学習再開 (`--resume_from_checkpoint`) の全経路が落ちていた (`strict=False` は size mismatch を緩めない)。 `piper_train.vits.commons.migrate_prefilm_decoder_cond` が旧 `cond` 重みを FiLM の shift 側に載せ scale 側をゼロ埋めする。 `_apply_film` は `scale = sigmoid(scale_raw) + 0.5` なので `scale_raw = 0` で gain が厳密に 1.0 となり、 旧 `x + cond(g)` と **ビット単位で同一**の出力になる (公開 ckpt 実機で max abs diff = 0.0 を確認)。 `cond_layers` は model 側と同じくゼロで backfill。 適用は `VitsModel.on_load_checkpoint` に置いたため `load_from_checkpoint` / `trainer.fit(ckpt_path=)` の両方が透過的に救われる
- 学習: 上記 ckpt からの学習再開で optimizer state が黙って失われる問題を修正。 `optimizer.load_state_dict` は shape を検証しないため、 pre-FiLM の Adam moment が拡幅後の param にそのままロードされ、 最初の `step()` で `RuntimeError` になり、 それを resume の fallback が飲み込んで **epoch 0 から再学習**していた。 パラメータ順序を検証できる場合は moment を同じ規則で拡幅し、 検証できない場合は optimizer state を破棄したうえで警告を出す (黙って epoch 0 に戻る経路を塞ぐ)。 fallback 自体も `UnpicklingError` を捕捉対象に加え、 「重みのみロードし epoch 0 から開始する」ことを warning で明示するようにした

### Changed

- ライセンス方針: `train` extra 限定の copyleft 依存を「明文化された例外」として受理する規定を `CONTRIBUTING.md` に追加。 `soxr` (LGPL-2.1-or-later) は `librosa` 0.11 の必須依存で `train` extra にのみ入り、 PyPI に publish される wheel (`src/python_run` 由来、 依存は `src/python_run/requirements.txt` が宣言) には含まれないため再頒布が発生せず LGPL の義務も生じない。 これまで CI の `allow-dependencies-licenses` には carve-out が入る一方で `CONTRIBUTING.md` は「LGPL はバージョンを問わず禁止」のままだったため、 設定と明文の方針が食い違っていた。 併せて、 scanner の parser bug 回避のための carve-out (`typing-extensions` / `llvmlite`、 実際には copyleft ではない) は方針例外ではなく、 例外表に載せてはならないことを明記

- Rust: `ort` を 2.0.0-rc.12 → rc.13 に更新したことに伴い、 `piper-core` の EP feature (`cuda` / `coreml` / `directml` / `tensorrt`) を weak-dependency 構文 (`ort?/cuda` 等) で `ort` 側へ転送するようにした。 rc.13 から `ort::ep::{CUDA, CoreML, DirectML, TensorRT}` が `ort` 自身の Cargo feature でcfg-gate されるようになり、 転送しないと EP 構造体が解決できずビルドが落ちる。 **利用者影響 2 点**: (1) rc.13 の `ort-sys` prebuilt distribution は `cuda13` タグのみで `cuda12` が存在しないため、 `cuda` feature を有効化する場合は CUDA 13 ランタイムが必要になる (Python / C# / Go / C++ の各ランタイムは従来どおり CUDA 12.x)。 (2) 4 つの EP を同時に含む prebuilt distribution が存在しないため `cargo build --all-features` は `ort-sys` のリンク時に失敗する (`cargo check` / `cargo clippy --all-features` はリンクしないため影響なし)。 単一 EP を指定してビルドすること (例 `--features onnx,cuda`)。 経緯と根拠は `docs/reference/ort-versions.md`、 ランタイム別の CUDA 要求は `docs/spec/ort-provider-contract.toml` に記録

- 学習: `--resume-from-multispeaker-checkpoint` の実処理がインライン複製から `load_multispeaker_checkpoint()` に一本化された。 同関数はどこからも呼ばれない dead code で、 インライン側と挙動が食い違っていた (関数側のみ HiFi-GAN ckpt を明示エラーにし、 インライン側のみ weight_norm キーを remap していた)。 統合の結果、 **FT 経路でも v1.11 以前の HiFi-GAN ckpt が明示エラーになる** (従来は無言で大量の missing keys を出して継続していた)。 同様に `export_onnx` の EMA 適用も 2 箇所の複製を `apply_ema_shadow_params()` に集約した

- CI: `g2p-python-ci.yml` の `test extras` job で venv を workspace 内 (`.venv-extras/`) ではなく `${RUNNER_TEMP}/venv-extras` に作るよう変更。 当 job は `uv.lock` を経由せず PyPI から fresh resolve するため nltk 3.10.x を引くが、 3.10 で追加された `nltk/inisec.py` の `NLTKSafeImportFinder` が「解決先ファイルが cwd 配下に物理的に存在する」モジュールを一律ブロックするため、 workspace 内 venv だと site-packages 全体が誤検知され `import nltk` 自体が `ImportError: Blocked import of regex from current working directory` で失敗していた。 エラーメッセージが案内する `-P` / `PYTHONSAFEPATH=1` は判定基準が sys.path ではなくファイルの物理位置のため回避にならないことを実測で確認済み

## [2.0.0] - 2026-05-25

Issue #527: Docker 全 image + CI workflow + ドキュメントを **Python 3.13 + CUDA 12.8 + Ubuntu 24.04** で完全統一する fully-aligned 戦略 migration。 新 GPU (T4 / RTX 6000 Ada / RTX 5090) サポート + TF32 / bf16-mixed default 化。
加えて Issue #590: **`piper` → `piper_plus` / `piper-plus` フル改名 (クリーンブレーク)** により本家 `piper-tts` (rhasspy/piper) と同一環境への pip 共存が可能に。

### Breaking

- **Default Docker images now require CUDA 12.8 + host NVIDIA driver R570+**
  ([`docker/python-train/Dockerfile`](docker/python-train/Dockerfile),
  [`docker/python-inference/Dockerfile`](docker/python-inference/Dockerfile)).
  Base image bumped from `nvidia/cuda:12.6.3-...-ubuntu22.04` to
  `nvidia/cuda:12.8.1-...-ubuntu24.04`. Hosts running NVIDIA driver R525
  (12.6) or older will fail to start the new images. See
  [Docker base image upgrade](docs/migration/v1.12-to-v2.0.md#docker-base-image-upgrade).
- **Default Python interpreter inside Docker images is 3.13** (was 3.11).
  `requires-python = ">=3.11"` is unchanged; PyPI installs on Python
  3.11/3.12 remain supported. Only the Docker image default has shifted.
  See [Python 3.13 default](docs/migration/v1.12-to-v2.0.md#python-313-default).
- **PyTorch wheel bumped from 2.2.1+cu121 to 2.11.0+cu128** in the
  training image. Required for RTX 5090 (Blackwell sm_120) support.
  See [PyTorch upgrade](docs/migration/v1.12-to-v2.0.md#pytorch-upgrade).
- **Loading checkpoints generated with torch 2.2 is no longer supported**
  in v2.0 training images. Existing ONNX models continue to work for
  inference. Users who need to continue fine-tuning from a torch-2.2
  checkpoint must stay on the v1.12 Docker image tag (preserved
  indefinitely in registry).
  See [Checkpoint resume non-support](docs/migration/v1.12-to-v2.0.md#checkpoint-resume-non-support).
- **distroless final images bumped from debian12 to debian13**
  ([`docker/python-inference/Dockerfile.cpu.distroless`](docker/python-inference/Dockerfile.cpu.distroless),
  [`docker/webui/Dockerfile.distroless`](docker/webui/Dockerfile.distroless)).
  Internal Python paths shifted from `/usr/local/lib/python3.11` to
  `/usr/local/lib/python3.13`.
  See [distroless image upgrade](docs/migration/v1.12-to-v2.0.md#distroless-image-upgrade).
- **TF32 is now enabled by default in training** via
  `torch.backends.cuda.matmul.allow_tf32 = True` and
  `torch.backends.cudnn.allow_tf32 = True`. This is a noop on sm_75 and
  older GPUs (T4 included). For Ada Lovelace / Blackwell, matmul/conv
  are ~1.3-1.5x faster but lose bit-exact reproducibility vs strict FP32.
  See [TF32 default ON](docs/migration/v1.12-to-v2.0.md#tf32-default-on).
- **Canonical training precision in CLAUDE.md Template A/B is now
  `--precision bf16-mixed`** (was `--precision 32-true`). The `32-true`
  option remains available for legacy V100 compatibility / strict
  numerical reproducibility, but is no longer the recommended default.
  New GPU (Ada 6000 / RTX 5090) users get BF16 Tensor Core acceleration
  by default.
  See [bf16-mixed Template default](docs/migration/v1.12-to-v2.0.md#bf16-mixed-template-default).
- **Python import: `import piper` / `from piper.X import ...` は削除**、
  `import piper_plus` / `from piper_plus.X import ...` に置換 (Issue #590、
  互換 shim なし)。 本家 `piper-tts` (rhasspy/piper) を co-install した環境で
  `from piper import ...` を書くと本家の `PiperVoice` が解決される (当 fork ではない)。
  See [piper → piper_plus 改名](docs/migration/v1.12-to-v2.0.md#piper--piper_plus--piper-plus-改名-issue-590).
- **Python CLI entry-point `piper` は削除**、 `piper-plus` に置換 (Issue #590)。
  `pip install piper-plus` (v2.0) 後に `piper` コマンドは存在しない。
  See [piper → piper_plus 改名](docs/migration/v1.12-to-v2.0.md#piper--piper_plus--piper-plus-改名-issue-590).
- **Python module 実行**: `python -m piper` / `python -m piper.webui` / `python -m piper.http_server`
  を削除、 `python -m piper_plus` / `python -m piper_plus.webui` / `python -m piper_plus.http_server`
  に置換 (Issue #590)。
  See [piper → piper_plus 改名](docs/migration/v1.12-to-v2.0.md#piper--piper_plus--piper-plus-改名-issue-590).
- **C++ プリビルドバイナリ**: `./bin/piper` / `piper.exe` を `./bin/piper-plus` / `piper-plus.exe`
  に rename (Issue #590)。 CMake target 名 `piper` は据置 (`OUTPUT_NAME "piper-plus"` で出力名のみ変更)。
  See [piper → piper_plus 改名](docs/migration/v1.12-to-v2.0.md#piper--piper_plus--piper-plus-改名-issue-590).
- **リリースアセット名**: `piper-<os>-<arch>.tar.gz` / `.zip` を
  `piper-plus-cpp-<os>-<arch>.tar.gz` / `.zip` に rename
  (C# `piper-plus-cli-*` / Rust `piper-plus-rs-cli-*` との接頭辞衝突回避に `-cpp-` 識別子、
  Issue #590)。 旧タグ添付資産は per-tag で不変。
  See [piper → piper_plus 改名](docs/migration/v1.12-to-v2.0.md#piper--piper_plus--piper-plus-改名-issue-590).
- **共有辞書 / キャッシュ dir**: `share/piper/` / `~/.local/share/piper` / `%APPDATA%\piper` 等を
  `share/piper-plus/` / `~/.local/share/piper-plus` / `%APPDATA%\piper-plus` に移動
  (Issue #590)。 既に DL 済みの辞書・モデルは再取得または手動移動が必要。
  See [piper → piper_plus 改名](docs/migration/v1.12-to-v2.0.md#piper--piper_plus--piper-plus-改名-issue-590).
- **環境変数 prefix**: `PIPER_*` (例 `PIPER_MODEL_DIR` / `PIPER_DISABLE_WARMUP`) を
  `PIPER_PLUS_*` (例 `PIPER_PLUS_MODEL_DIR` / `PIPER_PLUS_DISABLE_WARMUP`) に統一 (Issue #590)。
  学習側 (`piper_train`) の env var、 Docker container Unix user `piper`、 および
  Wyoming Docker container 内の PIPER_MODEL / PIPER_LANGUAGE / PIPER_SPEAKER_ID / PIPER_PORT
  (Home Assistant 既存ユーザー互換性のため据置) は scope 外。
  See [piper → piper_plus 改名](docs/migration/v1.12-to-v2.0.md#piper--piper_plus--piper-plus-改名-issue-590).

### Added

- **`docs/migration/v1.12-to-v2.0.md`**: v2.0.0 マイグレーションガイド (Issue #527 + Zero-Shot TTS 統合リリース)。 設計の根拠 / ADR / 未決事項 / 実装履歴は [Issue #527](https://github.com/ayutaz/piper-plus/issues/527) + [PR #569](https://github.com/ayutaz/piper-plus/pull/569) を canonical source とする。
- **`torch.backends.cuda.matmul.allow_tf32 = True`** in
  [`src/python/piper_train/__main__.py`](src/python/piper_train/__main__.py)
  (DR-007、 Ada/Blackwell で TF32 Tensor Core 透過適用)。
- **rhasspy/piper (`piper-tts`) との pip 同一環境共存サポート**
  ([Issue #590](https://github.com/ayutaz/piper-plus/issues/590)):
  import 名 / CLI 名 / バイナリ名 / 環境変数 prefix / 共有 dir を全て `piper_plus` /
  `piper-plus` / `PIPER_PLUS_*` に改名したことで、 本家 `piper-tts` と `piper-plus`
  を同一 venv に co-install できるようになった。 新メンタルモデル:
  `import piper` = 本家 rhasspy/piper、 `import piper_plus` = 当 fork
  (完全独立、 名前空間衝突なし)。
  See [新メンタルモデル](docs/migration/v1.12-to-v2.0.md#新メンタルモデル-最重要).
- **高レベル API `piper_plus.api` サブモジュール統合**
  ([Issue #590](https://github.com/ayutaz/piper-plus/issues/590)):
  旧 `src/python/piper_plus/` (Wyoming Docker が独自 ONNX 推論エンジンで使用) を
  `src/python_run/piper_plus/api/` に物理統合。 `from piper_plus.api import PiperPlus`
  で高レベル API を利用可能。 旧 top-level `piper_plus` (高レベル API) と
  runtime `piper` (PiperVoice) の名前空間衝突を解消。

### Changed

- **CI workflow**: 20 個の workflow で `python-version` を `'3.11'` から
  `'3.13'` に bump (matrix workflow `python-tests` / `g2p-python-ci` は
  3.11/3.12/3.13 網羅で据置。 `build-phonemize-wheels` は piper-phonemize が
  `python<3.13` のため 3.11/3.12 のみ網羅、 Issue #527)。
- **Library floor pins**: 17 library の floor drift を root と member で統一
  (`scipy>=1.17.1` / `pytorch-lightning>=2.4.0` / `transformers>=4.50.0`
  / `onnxruntime>=1.26.0` / `numba>=0.61.0` 等、 DR-002)。
- **CLAUDE.md Template A/B**: `--precision 32-true` → `--precision bf16-mixed`、
  `--no-wavlm` を削除 (Ada/Blackwell では WavLM 有効が canonical)。
- **docs/guides/training/**: V100 言及を新 GPU (T4 / Ada 6000 / RTX 5090)
  前提に置換。

### Fixed

- **`monotonic_align/setup.py`**: `from distutils.core import setup` →
  `from setuptools import setup`。 distutils は Python 3.12 で stdlib から
  削除済 (PEP 632)、 setuptools shim 経由で偶然動いていた状態を明示化。
- **Rust security bump** (Issue #590 / PR #598 内): `piper-plus-g2p` の
  `quick-xml` を 0.37 → 0.41 に bump し
  [RUSTSEC-2026-0194 / 0195](https://rustsec.org) (Severity 7.5)、
  および `crossbeam-epoch` 0.9.18 → 0.9.20 を解消。 併せて `piper-core`
  の SSML parser 実装を `piper_plus_g2p::ssml` の re-export へ切替、
  `piper-core` 側の `quick-xml` 直接依存を除去 (downstream `piper-plus`
  クレートの dep tree 縮小 / attack surface 減)。

## [1.13.0] - 2026-06-13

### Added

#### G2P 文単位並列化 + ORT 推論オーバーラップ (Issue #383)

G2P (音素化) を文単位で並列化し、全 5 ランタイム (Python/Rust/C#/Go/C++) に展開。Python は ORT 推論との pipeline 化で長文の TTFB を短縮 (代表値: Go N=20 で約 3.96x、Python で約 -19%)。新 env var `PIPER_G2P_PARALLELISM` で並列度を全ランタイム共通制御でき、`PIPER_G2P_PARALLELISM=1` で逐次の旧挙動に戻せる (Breaking なし)。PR #403。

#### 2 image distroless trial Dockerfiles + CI (webui / cpp-inference)

PR #523 (python-inference) で確立した distroless trial pattern を、 deploy 検証要件のない 2 image に bundle 適用。 既存 `Dockerfile` / `docker-compose` / 関連 CI は **不変更で残し**、 並行 `Dockerfile.distroless` を 2 枚追加して build / size A/B / smoke test を CI で実証する scope。 promotion (canonical 置換) は image 別に別 PR。

- **`docker/webui/Dockerfile.distroless`** (Python + Gradio): multi-stage、 builder = `python:3.11-slim-trixie`、 final = `gcr.io/distroless/python3-debian12`。 PR #523 と同型 Debian-glibc ABI 統一、 `/usr/bin/python3` 絶対パス起動、 arch-neutral lib staging。 site-packages + NLTK data を builder から COPY、 ENTRYPOINT は `python3 /app/app.py` (canonical の `entrypoint.sh` は shell なしのため使えず、 実体は同等の単一行 exec)、 明示的 `USER 65532` を Trivy DS-0002 対応
- **`docker/cpp-inference/Dockerfile.distroless`** (C++ runtime): builder = `debian:12-slim` (canonical の ubuntu:24.04 から変更、 distroless/cc-debian12 = Debian 12 glibc 2.36 との ABI 一致のため)、 final = `gcr.io/distroless/cc-debian12`。 piper binary + ONNX Runtime / libgomp shared lib + OpenJTalk 辞書を COPY。 libgomp は arch-neutral staging で bring-over。 canonical の `entrypoint.sh` (shell) → ENTRYPOINT に直接 `/usr/local/bin/piper` 化
- **新規 CI workflow** (`.github/workflows/docker-distroless-trial.yml`): PR base + workflow_dispatch、 2 image matrix で build (canonical baseline + distroless trial) → size 比較 → smoke (webui: Gradio import / cpp-inference: piper --version) → aggregate sticky comment 投稿
- **既存 workflow chain 統合**: `hadolint.yml` matrix に 2 Dockerfile 追加、 `trivy-container-scan.yml` matrix に 2 target 追加、 `docker-build.yml` の `build-distroless-trials` matrix job (multi-arch linux/arm64 + linux/amd64) に統合 (PR #523 で導入した python-inference distroless と合わせて 3 image trial が 1 job matrix で並走)
- **hadolint config 拡張**: `.hadolint.yaml` の `trustedRegistries` に `cgr.dev` を allow-list 追加 (将来の Wolfi 採用に備えた forward-compat、 本 PR では未使用)
- **promotion path**: 各 trial で build + size 効果が確認できた後、 image 別に canonical 置換 PR を作成 (webui は webui-test.yml smoke、 cpp-inference は container test gate での実モデル E2E が前提)
- **cpp-dev distroless は scope-out 確定** (旧 T-016、 PR #526 で確定): wolfi-base trial で OpenJTalk / mecab tooling chain が Debian apt package 前提のため Wolfi で source build を full chain で組むには iconv / libtool / gettext 等の missing package 連鎖が判明。 加えて cpp-dev は dev image (production 推論経路なし、 cmake / clang / gdb を final stage に同居必須) で distroless 哲学と本質的に不整合、 大目的 (production image の CVE 80% / size 50% 削減) への寄与が限定的。 PR #524 で webui + cpp-inference trial bundle により spike 目的 (multi-stage pattern / glibc ABI 整合 / entrypoint 移植) は達成済のため、 M3 distroless は 5 image → 4 image に scope 縮小し ticket file 削除

#### `python-inference` distroless trial Dockerfile + CI (`Dockerfile.cpu.distroless`)

`docker/python-inference/` の distroless 化を derisk する **trial PR**。 既存 `Dockerfile.cpu` と `docker-compose.yml` / `.github/workflows/deploy-huggingface.yml` (HF Space deploy 経路) は **不変更で残し**、 並行 `Dockerfile.cpu.distroless` を新設して build / size / smoke test を CI で実証する scope。

- **新規 Dockerfile** (`docker/python-inference/Dockerfile.cpu.distroless`): multi-stage build (builder = `python:3.11-slim-trixie`、 final = `gcr.io/distroless/python3-debian12`)。 base image は Debian-glibc baseline 統一で選定: builder と final が同じ glibc ABI を共有するため、 onnxruntime の pre-built C 拡張 (`onnxruntime_pybind11_state.so`) と soundfile の libsndfile dlopen が byte-for-byte 一致で resolve する。 Wolfi 系 (`cgr.dev/chainguard/python`) は当初候補だったが、 Wolfi の glibc / Python build が Debian と別 ABI で onnxruntime が import 不可と判明したため Debian baseline に確定。 builder で `piper_plus_g2p[all]` + `piper_train[inference]` + Gradio WebUI requirements + NLTK data を install、 final へ Python site-packages + `/usr/local/bin/uvicorn` + 必要な shared libs (libsndfile / libgomp / libFLAC / libvorbis / libogg / libopus / libmpg123) を COPY
- **新規 CI workflow** (`.github/workflows/python-inference-distroless-trial.yml`): PR base + workflow_dispatch、 canonical `Dockerfile.cpu` を baseline として build、 distroless trial を build、 image size を比較、 import smoke test 2 種 (ONNX Runtime / piper_train / FastAPI / soundfile import 確認) を実行、 PR コメントに distroless trial report を sticky 投稿
- **scope 限定**: linux/amd64 single-arch CI build のみ (multi-arch は別 PR で buildx)、 `/v1/audio/speech` E2E は CI に ONNX model fixture 配置が前提のため別 PR、 CVE 比較 (Trivy) も canonical 置換 PR 側で実施。 HF Space staging deploy 検証は user 手動 step (Claude Code は実行不可)
- **promotion path**: trial PR で「build 成立 + size 削減効果」 が確認できた後、 別 PR で `Dockerfile.cpu` 自体を置換 (HF Space staging で cold start 検証後)

#### docs/ fenced code blocks の execution gate (`scripts/check_doc_examples.py execute`)

audit gate (`scripts/check_doc_examples.py audit`) で生成した canonical snapshot を入力に、 `executable` category の block を **syntax-validation default** で sandbox 実行する informational tier gate を追加。 加えて `test-flake-retry-contract.toml` の `applies_to` を 4 → 8 runtime に拡張し full scope 化。

- **execute サブモード** (`scripts/doc_examples/executor.py`): bash + python の 2 runner を v1 で実装 (executable scope の 95%+ を担保)。 default は **syntax 検証のみ** (`bash -n` / `python -m py_compile`) で destructive 操作 (`rm` / `curl` 等) を呼ばない。 `--actually-run` 明示時のみ subprocess で実行、 bash は `set -euo pipefail` 注入。 残 4 言語 (rust / csharp / go / wasm) は runner 未登録、 `runner_unsupported` で集計のみ
- **stale audit 検知**: audit JSON の `hash_sha1` と現在の block hash を再計算で比較、 不一致なら `::warning::Audit JSON stale: <file>:<line>` を出力 (block の実行自体は継続)
- **sticky comment 生成**: 「期待値 (audit.totals.executable) vs 実測値」 / outcome 内訳 (pass / fail / timeout / runner_unsupported / runner_missing) / fail 一覧テーブル / stale audit 一覧 を markdown で書き出し (`--sticky-comment`)
- **新規 workflow** (`.github/workflows/doc-examples-gate.yml`): PR base + Tuesday 06:00 UTC schedule + workflow_dispatch、 informational tier (`continue-on-error: true`)、 sticky-pull-request-comment で PR に投稿
- **silent-zero defensive log**: `Collected executable blocks (N=...): bash=A python=B ...` + `Expected from audit.totals.executable=N` を必ず stderr 出力。 N=0 で `::warning::`、 N < expected/2 で `::warning::`
- **8 runtime test flake retry**: `test-flake-retry-contract.toml` の `applies_to` を `[python, rust, go, csharp, wasm, cpp, kotlin, swift]` に拡張、 4 新規 runtime (WASM jest / C++ ctest --repeat / Kotlin gradle test-retry / Swift `swift test -- --test-iterations`) を spec に追加 (status=proposed、 既存 gate の `check_proposed_runtime` で shape validation)
- **Unit tests 26 件追加** (`test_check_doc_examples_execute.py` 13 件 + `test_check_test_flake_retry.py` 既存テスト 8 runtime 対応)
- **実 docs での効果**: syntax-only run で 185 block を validate (165 bash + 20 python)、 既存 docs から **5 件の bash 構文エラー** を検出 (mutation-testing.md / M3-supply-chain.md / T-019/T-020/T-021 SLSA ticket)。 これらは informational tier として sticky comment に記録され、 後続 PR で個別修正候補

#### docs/ fenced code blocks の audit gate (`scripts/check_doc_examples.py audit`)

`docs/` 配下 (~150 markdown) の GFM fenced code blocks を全件抽出し、 3 カテゴリ (executable / needs_placeholder / skip_warranted) に分類する audit 機能を新規実装。 後続の execution gate / blocker 化判定の前提となる canonical 入力 (`tests/fixtures/doc_examples_audit/audit.json`) を生成する。

- **新規 spec**: `docs/spec/doc-examples-contract.toml` で audit 対象 glob / 言語 alias / placeholder 正規表現 / skip directive / 環境依存パターン / silent-zero 防御方針を pin
- **新規モジュール**: `scripts/doc_examples/{extractor,classifier}.py` (markdown-it-py の `commonmark` preset で GFM 三連バッククォート fenced block を抽出、 6 canonical 言語 + 多数の alias を正規化、 placeholder/skip directive/env-dep を deterministic に分類)
- **新規 CLI**: `scripts/check_doc_examples.py audit` (`--config` / `--output` / `--check-snapshot` / `--generated-at` をサポート)。 silent-zero 防御 `Collected blocks (total=N): bash=A python=B ...` を必ず stderr 出力、 total=0 で `::warning::`
- **canonical snapshot**: 現状の audit 結果を `tests/fixtures/doc_examples_audit/audit.json` に commit (464 block: executable 215 / needs_placeholder 2 / skip_warranted 247、 言語別内訳付き、 非 canonical 言語は `unknown` bucket に集約)。 docs 編集で snapshot が drift したら `--check-snapshot` が exit 1
- **既存 `scripts/check_readme_code_examples.py` (シンボル grep) は維持** — 「シンボル存在 vs 実行可否」 の役割分担を spec contract に明記、 重複なし
- **Unit tests 11 件追加** (extractor / classifier 各カテゴリ / 言語 alias 正規化 / silent-zero / snapshot drift / 実 docs snapshot 一致)

実 docs 内訳 (本 PR snapshot):

| 言語 | executable | needs_placeholder | skip_warranted |
|------|-----------|------------------|----------------|
| bash | 165 | 2 | 24 |
| python | 20 | 0 | 0 |
| rust | 11 | 0 | 0 |
| csharp | 5 | 0 | 0 |
| go | 4 | 0 | 0 |
| wasm | 10 | 0 | 0 |
| `unknown` (非 canonical: json/yaml/text/dockerfile/kotlin/etc) | 0 | 0 | 213 |

#### Spec contract gates: model-sha256-manifest / artifact-retention / test-flake-retry (T-005/T-006/T-008)

5 件の spec sync gate 穴のうち未実装だった 3 件を新規 gate 化、 既存実装 (T-004/T-007) は `[meta].direction` 明文化のみで closeout。 各 gate に silent-zero defensive log を inline 実装し M1 で確立した pattern を踏襲。

- **T-005 model-sha256-manifest gate** (`scripts/check_model_sha256_manifest.py`): `docs/spec/model-sha256-manifest.toml` の 6 model entry が CLAUDE.md 「学習済みモデル」 表と一致するか、 `<computed-on-publish>` placeholder か 64-char lowercase hex SHA256 のいずれかか、 `[meta]` 必須 key (spec_version / canonical_source / hash_algorithm / hash_encoding / update_policy / forward_compat_policy) が揃っているかを検証。 `MAX_KNOWN_SCHEMA_VERSION = 2` で forward-compat (loanword sync gate と同型) を pin
- **T-006 artifact-retention gate** (`scripts/check_artifact_retention.py`): 全 `.github/workflows/*.y*ml` (40 workflow / 63 upload step) の `retention-days:` を抽出し、 `[[categories]]` 許容値 [1, 7, 30, 90] と突合。 同 PR 内で初期 baseline 違反 6 件を sweep (cpp-abi-check/fuzz-smoke 4 件: 14d→30d / cppcheck: 14d→7d / scorecard: 5d→7d / typosquatting-watch: 365d→90d) し `[meta].mode = "fail"` で導入完了
- **T-008 test-flake-retry gate** (`scripts/check_test_flake_retry.py`): 4 runtime (python / rust / go / csharp) のうち `status = "phase-1"`/`"phase-2"` の runtime に pyproject 依存 + `--reruns N` flag が wire-up されているか、 全 runtime の retry 値が `retry_count_max = 2` 不変条件を満たすか、 `[[invariants]]` 3 件 (no-blanket-retry / retry-count-max-2 / ci-only-retry) が削除されていないかを検証
- **direction 明文化 (closeout)**: `release-versions.toml` (post-hoc) と `swift-g2p-contract.toml` (pre-impl) の `[meta].direction` を追加。 これら 2 件は既存 `scripts/check_version_manifest_sync.py` / `scripts/check_swift_g2p_contract.py` が gate 化済み
- **CI 統合**: `.github/workflows/contract-gates-extended.yml` の matrix に 3 contract id (model-sha256-manifest / artifact-retention / test-flake-retry) を追加、 既存 `.pre-commit-config.yaml` に 3 hook 追加 (path filter で fast-path)
- **Unit tests**: 41 件追加 (`tests/scripts/test_check_{model_sha256_manifest,artifact_retention,test_flake_retry}.py`)
- **M1 status 反映**: PR #513 merge を受けて `docs/tickets/{README.md,milestones/M1-foundations.md,tickets/T-00{1,2,3}-*.md}` の Status を 「完了」 + PR #513 を記録

#### Kotlin/Android G2P AAR を Maven Central に公開 (Issue #388)

8 言語マルチリンガル G2P を Android アプリから利用するための **engine-less Kotlin AAR** を新設。Maven coordinates `io.github.ayutaz:piper-plus-g2p-android`。`implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")` 1 行で導入できる。

- **Engine-less C API 拡張**: `piper_plus_g2p_create` / `_phonemize` / `_available_languages` / `_load_custom_dict` / `_set_zh_en_dispatch` / `_is_zh_en_dispatch_enabled` / `_free` の 7 関数を C API に追加 (`src/cpp/piper_plus.h`)。ONNX モデル不要で 8 言語 (ja=0, en=1, zh=2, es=3, fr=4, pt=5, ko=6, sv=7) を phonemize 可能。既存 `piper_plus_phonemize()` と同じ `piper::phonemizeText` を共有するため byte-for-byte 互換 (FR-CAPI-3)。既存 ABI (`PIPER_PLUS_API_VERSION 1`) を破壊しない追加のみ。
- **JNI bridge**: `android/piper-plus-g2p/src/main/cpp/piper_plus_g2p_jni.cpp`。既存 TTS フル AAR (`android/piper-plus/`) と同じ `JNIStringGuard` RAII / `JNI_OnLoad` 例外 GlobalRef キャッシュ / BORROWED ポインタ即 `NewStringUTF` コピーパターンを踏襲
- **Kotlin パブリック API**: `PiperPlusG2p` (`AutoCloseable` + `@Synchronized`) / `PhonemeResult` data class / `PiperPlusG2pException` / `OpenJTalkDictionary` (`fromAssets` / `fromPath`) / `DictionaryDownloader` (`downloadFromHuggingFace` suspend、SHA-256 検証付)
- **Gradle module**: `android/piper-plus-g2p/build.gradle.kts` で vanniktech `gradle-maven-publish-plugin` 0.30.0 + `SonatypeHost.CENTRAL_PORTAL` 採用。3 ABI (arm64-v8a / armeabi-v7a / x86_64)、`-Wl,-z,max-page-size=16384` で 16 KB page size 対応 (Android 15+)、minSdk 24 / compileSdk 35 / Kotlin 2.1.0 / JDK 17。Gradle Managed Devices で Pixel 6 API 34 emulator 自動起動
- **CI 自動テスト 5 層**: `.github/workflows/kotlin-g2p-ci.yml` で L1 (Pure Kotlin unit) / L3 (Android instrumented on Gradle Managed Devices) / L4 (parity 雛形) / L5 (`readelf -lW` で 16 KB align gate + AAR サイズ < 10 MB gate) を全 PR で実行
- **Maven Central 自動公開**: `.github/workflows/release-kotlin-g2p.yml` がタグ `kotlin-g2p-v*` push を検知して GPG in-memory key + Sonatype Central Portal credentials で `publishAndReleaseToMavenCentral` を実行。PR では `publishToMavenLocal` の dry-run のみ
- **辞書配布 3 パターン**: AAR には OpenJTalk 辞書 (~102MB) を同梱せず、(1) App assets バンドル (`OpenJTalkDictionary.fromAssets`)、(2) Play Asset Delivery (`fromPath`)、(3) Runtime DL from Hugging Face Hub (`DictionaryDownloader.downloadFromHuggingFace` + SHA-256 検証) の 3 通りを提供。詳細: `docs/guides/platform/android-g2p-dictionary.md`
- **GTest 26 ケース** (`src/cpp/tests/test_c_api_g2p.cpp`): lifecycle / NULL safety / `available_languages` order / 規則ベース 3 言語 (es/fr/pt) / ZH-EN dispatch toggle / borrowed pointer 寿命 / custom dict
- **L4 byte-for-byte parity**: `tools/generate_g2p_golden.py` で Python `MultilingualPhonemizer` から 70 ケースの IPA 列を pre-compute し `tests/fixtures/g2p/phoneme_test_cases_golden.json` に固定。Kotlin instrumented `PhonemeFixtureParityTest.byte_for_byte_parity_with_python_golden` が strict diff で drift を検知 (FR-CAPI-3 / FR-TEST-1)
- **サンプル Compose アプリ**: `examples/android-g2p-sample/` (8 言語タブ + TextField → phonemize → カード表示)。Gradle composite build で in-repo AAR を直接消費。`.github/workflows/kotlin-g2p-ci.yml` の `sample-app` ジョブで `assembleDebug` を CI gate (AC-10)
- **設計・要件**: `docs/spec/kotlin-g2p-{design,requirements}.md`
- **10 並列エージェント自己監査による 22 件の修正** (2026-05-07):
  - **CI 修正**: NDK install を 4 つの Gradle ジョブ (unit-tests / build-aar / instrumented-tests / sample-app) と release publish に追加 (externalNativeBuild が常に NDK を要求するため、無いと全失敗していた)。`concurrency` block 追加でブランチ重複実行を防止。L4 専用 `parity-golden` ジョブ追加: Linux で eunjeon インストール後に `tools/generate_g2p_golden.py` を再実行し、`tools/compare_g2p_golden.py` で `expected_phonemes` の drift だけを strict 検査 (KO の skip / failed_cases メタデータは platform 固有なので除外)。
  - **L4 default_latin_language の golden 修正**: 既存 golden は `default_latin_language="en"` で全ケース生成していたため PT/ES/FR/SV テキストが英語 G2P 経由で誤った IPA を保持していた (例: `"hola"` → `h ˈ o ʊ l ə` 英語フォニックス)。C API 側 `piper.cpp` は `synthesisConfig.languageId` から `defaultLatin` を選ぶため runtime と divergence。`generate_g2p_golden.py` を per-case `default_latin_language=lang` に修正 + golden を再生成 (`"hola"` → `ˈ o l a` Spanish)。`schema_version: 2` で `failed_cases` / `skipped_ko_cases` を追加。
  - **VERSION_NAME = 1.0.0 統一**: `android/gradle.properties` が `0.1.0` のままだったためタグ push 時に 0.1.0 が public される状態だった。`build.gradle.kts` のフォールバックも合わせて 1.0.0 に。`GROUP=io.github.ayutaz` も明示。
  - **AndroidManifest INTERNET permission 追加**: `DictionaryDownloader` が HF Hub 接続するのに必要だが空 manifest のままだった。consumer apps へ manifest merger 経由で伝播。
  - **DictionaryDownloader セキュリティ強化 (NFR-SEC-2)**: (a) `host` パラメータを **allowlist** (`huggingface.co` / `hf-mirror.com`) に固定 + `https://` 強制、(b) ustar の `prefix` (155B) field を `name` field と連結、(c) symlink/hardlink/device entry を `IOException` で reject、(d) per-entry 64MB / total 256MB の上限ガード (TAR-bomb 対策)、(e) 中間ディレクトリ → `renameTo` でほぼ atomic な extract (.complete marker)、(f) `withContext(Dispatchers.IO)` + `currentCoroutineContext().ensureActive()` で coroutine cancellation 対応。
  - **PiperPlusG2pException に `cause` 引数追加**: 設計書要求の `Exception(message, cause)` に整合。`DictionaryDownloader` などの内部 IOException を chain 可能に。
  - **build.gradle.kts**: `ndkVersion = "26.1.10909125"` pin (再現性 NFR-PUB-1)、`targetSdk = 34` 追加 (Play Store 必須)、vanniktech と `android.publishing { singleVariant }` の二重設定を解消、`org.jetbrains.dokka` plugin を適用 (空 javadoc.jar が Sonatype 品質ゲートで弾かれる対策、FR-DOCS-4)、kotlinx-coroutines-android 依存追加。
  - **Kotlin API 仕様整合**: `OpenJTalkDictionary.path` を `internal val` に降格 (公開 API 表面汚染解消、`absolutePath()` 関数のみ public)、`PhonemeResult.phonemeList` を `Collections.unmodifiableList` でラップ、`version()` に `@Synchronized` 追加 (設計書「全 native 呼び出し同期」充足)、`extractAssetTree` に path traversal 防御 (canonical-path 検査) 追加。
  - **L1 ユニットテスト 5 → 18 件**: `DictionaryDownloaderTest` (host allowlist) / `OpenJTalkDictionaryTest` (`fromPath` / `exists` / `absolutePath`) / `PiperPlusG2pNativeTest` (JNI shape reflection) / `PhonemeResultTest` (immutability) / `PiperPlusG2pExceptionTest` (cause) を追加。
  - **L3 instrumented 拡充**: `OpenJTalkDictionaryInstrumentedTest` で 3 辞書配布パターン (assets / fromPath / Downloader allowlist) と `create(context, dict)` 統合を網羅 (FR-DICT-1 / FR-TEST-4)。`PhonemeFixtureParityTest.byte_for_byte_parity_with_python_golden` を `assumeTrue(false)` silent skip → `AssertionError` に変更し golden 欠落を loud fail に。
  - **release-kotlin-g2p.yml**: SemVer regex を SemVer 2.0.0 §10 準拠 (pre-release **+** build metadata 同時許可)、4 つの publishing secrets の fail-fast 検査追加、workflow_dispatch にも version regex を適用。
  - **ドキュメント整備**: `docs/guides/platform/android-g2p-integration.md` (FR-DOCS-2、新規)、`tools/build-openjtalk-dict-archive.sh` (M6 で参照されていたが未実装だったビルドスクリプト)、`tools/compare_g2p_golden.py` (CI 用 golden diff)、`CONTRIBUTING.md` に `kotlin-g2p-v*` tag 規約と Maven Central リリース順序追加。`piper_plus.h` の `findG2pDictFile` 経路に関する誤解を招く記述を訂正。

- **残作業全消化** (2026-05-07、ユーザー指示「すべてこのブランチで対応」):
  - **L2 (linuxTest) ジョブ追加**: 設計書 §9.2 / AC-3 要求の「JVM JNI smoke on Linux .so」を `kotlin-g2p-ci.yml:linux-jvm-smoke` で実装。Linux x86_64 で `libpiper_plus.so` + `libpiper_plus_g2p_jni.so` をネイティブビルドし、JVM から `System.load` + 主要メソッド呼び出し (nativeCreate / nativeVersion / nativeAvailableLanguages / nativePhonemize) で symbol-resolution / ABI mismatch を catch。L3 emulator より約 10x 高速で fail。
  - **ASan CI ジョブ追加 (NFR-SEC-4)**: `kotlin-g2p-ci.yml:asan-tests` で `libpiper_plus.so` + GTest を `-fsanitize=address` 下でビルド・実行。`test_c_api --gtest_filter='G2p*'` で 23 ケースを leak/UAF/heap-OOB 検出付きで実行。`tests/asan_lsan_suppressions.txt` で ORT / OpenJTalk のプロセス終了時に発火する benign leak のみを suppress (実害ある leak は通過させる)。
  - **8 言語×50 ケース fixture 拡充 (FR-TEST-1)**: `tests/fixtures/g2p/phoneme_test_cases.json` を 81 → 419 ケースに拡充 (en 50 / es 50 / fr 54 / pt 52 / sv 51 / zh 56 / ja 53 / ko 53)。`tools/expand_g2p_fixtures.py` で systematic に追加 (数字 / 句読点 / 長文 / 言語固有 (ñ/ç/å/ö/ü/...) / loanword / 単一 char edge case)。Python golden も再生成 (313 ケース、JA/KO は CI Linux で再生成)。
  - **Gradle wrapper 追加**: `android/gradlew` / `gradlew.bat` / `gradle/wrapper/gradle-wrapper.{jar,properties}` (Gradle 8.11.1) を整備。ローカル開発者の `./gradlew` 体験を担保。`.gitattributes` に `gradlew text eol=lf` / `*.jar binary` を追加し OS 間で line ending が壊れないように pin。

#### ZH-EN code-switching を全 7 ランタイムに展開 (Issue #384)

中国語テキストに混在する英単語 (acronyms / loanwords / per-letter fallback) を米国英語ではなく Mandarin pinyin で発音する機能を、Python (PR #397 で先行リリース) に続いて Rust × 2 crate / Go / C# / WASM / C++ の **5 ランタイムへ byte-for-byte 同期展開**。

- **canonical**: `src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json` (acronyms 65 / loanwords 40 / A-Z fallback、131 entries)
- **mirror 7 箇所** + **fixture 6 箇所**: CI gate `ZH-EN Loanword Sync Gate / json-sync` が SHA256 一致を強制 (`scripts/check_loanword_consistency.py` + `/check-loanword` skill)。helper script 自体の挙動を verify する `helper-self-check` job (`--diff` / `--fix` 冪等性) も同 workflow に同居
- **API**: 各ランタイムの `MultilingualPhonemizer` が `[zh,en,zh]` / `[zh,en]` / `[en,zh]` パターンを自動検出し、英語 segment を loanword 経路にディスパッチ。runtime opt-out: `enable_zh_en_dispatch(false)` (Rust) / `SetZhEnDispatch(false)` (Go) / `EnableZhEnDispatch = false` (C#) / `setZhEnDispatch(false)` (WASM)
- **Forward-compatible loader (YELLOW-5)**: 全 7 ランタイム (Python + Rust × 2 / Go / C# / WASM / C++) で `schema_version: 2` の未来フィールドを silent ignore する挙動を pinning test で固定
- **Two-layer model**: コンパイル時 (Cargo feature `chinese` / csproj `<EmbeddedResource>` / Go `//go:embed` / C++ CMake) + ランタイム (default-on opt-out) の二層管理 (TICKET-01 §7 懸念 5)
- **ランタイム test カバレッジ**: Rust × 2 / Go / C# / WASM / C++ + Python の各 ZH-EN test スイートで `phonemize_embedded_english` の lookup priority / forward-compat / dispatch / opt-out / per-token prosody (a1=tone, a2=a3=1) を検証
- **Issue #384 例**: `请打开 GPS` / `我喜欢用 Python 写代码` / `让我用 ChatGPT 写代码` を Python リファレンス test がカバー。各ランタイムの `phonemize_embedded_english` は同 JSON (byte-for-byte 同期) と同 lookup ロジックで動くため Python と等価な IPA 列を返す。設計と運用契約: [`docs/reference/zh-en-loanword/README.md`](docs/reference/zh-en-loanword/README.md)。

##### 既知の制約 / 別 PR フォローアップ予定

本 PR では JSON 同期と各ランタイムへの dispatch wiring を成立させたが、以下の hardening / 拡張は別 PR で取り組む:

- **Cross-runtime IPA parity CI**: `tests/fixtures/g2p/zh_en_loanword_matrix.json` の各 case を全ランタイムに食わせて token 列が一致することを検証する gate (現状は per-runtime に loadable + per-case `expected_token_count` strict check のみ — Python が IPA 列を JSONL で pre-compute して全ランタイムが同じ列を返すか確認する parity job は未実装)。
- **Loader hardening (Tier 1-2 セキュリティガード)**: `MAX_LOANWORD_FILE_SIZE` / `MAX_LOANWORD_ENTRIES` / `MAX_LOANWORD_DEPTH` をユーザー指定 override path 受付経路 (`--zh-en-loanword-dict-paths` 等) に追加。bundled JSON は安全だが攻撃者が用意した巨大/深い JSON を読ませた場合の DoS 防止。
- **Python opt-out API parity**: 現状 Python は `set_zh_en_dispatch` を持たず常時 ON。他 6 ランタイムと API parity を取るために将来 `MultilingualPhonemizer.set_zh_en_dispatch(bool)` を no-op or 実機能として追加検討 (test `test_dispatch_no_optout_api_exposed` で現状を pin 中)。
- **WASM JS 実配線**: `ChineseG2P.setZhEnDispatch` の wrapper は整備済だが、`G2P.create()` も `piper-plus` 側もまだ `wasmPhonemizer` を注入していないため、JS-only 実行では dispatch は no-op (Rust WASM 直叩きでは動作)。`G2P.create({ wasmPhonemizer })` 統合が次フェーズ。
- **Rust piper-core / piper-plus-g2p の chinese.rs 重複**: `piper-core/src/phonemize/chinese.rs` は piper-plus-g2p の ~470 行のコピー (CI parity test で drift 防止)。`pub use piper_plus_g2p::chinese::*` への置換で長期メンテナンスコストを下げる予定。
- **Rust `last_eos` Mutex のセマンティクス改善**: 現状 `Mutex<String>` は単一スレッド前提で安全だが論理的にはスナップショット。中期的には `phonemize_with_prosody` の戻り値型に EOS を含める設計に変更予定。

#### Swift G2P 単独利用サポート (Issue #387)

iOS / Swift から piper-plus の G2P (Grapheme-to-Phoneme) を **ONNX Runtime 非依存で**単独利用可能に。8 言語 (ja/en/zh/ko/es/fr/pt/sv) 対応、辞書はバイナリ埋込で iOS App Sandbox でも動作。

- 新 SPM product: `PiperPlusG2P` (`Package.swift` の `.library(name: "PiperPlusG2P", ...)`)
- 新 artifact: `libpiper_plus_g2p-ios-v${VERSION}.xcframework.zip` (合成エンジン xcframework と独立、ORT 非依存、~3-5MB zip)
- Swift API: `Phonemizer(languages:)` / `phonemize(_:language:)` / `availableLanguages` (`Sources/PiperPlusG2P/`)
- Rust 側変更:
  - `piper-plus-g2p` crate に `[lib] crate-type = ["staticlib", "cdylib", "rlib"]` 追加
  - `bundled-dicts` feature 新設 (cmudict + pinyin JSON を `include_str!` / `include_bytes!` で埋込)
  - `EnglishPhonemizer::new_bundled()` / `ChinesePhonemizer::new_bundled()` 追加
  - `ffi.rs::register_one()` を `bundled-dicts` 有効時に新コンストラクタ経由に変更
- `cbindgen.toml` 新設 — `piper_plus_g2p.h` を CI で自動生成
- CI: `release-shared-lib.yml` に `build-g2p-ios` matrix + `assemble-g2p-xcframework` ジョブ追加。`release` ジョブは G2P xcframework の sha256 と `Package.swift` の `g2pChecksum` 一致を verify
- ドキュメント: [`docs/reference/swift-g2p.md`](docs/reference/swift-g2p.md) (仕様)、[`docs/guides/platform/swift-g2p-integration.md`](docs/guides/platform/swift-g2p-integration.md) (利用ガイド)、[`docs/spec/swift-g2p-contract.toml`](docs/spec/swift-g2p-contract.toml) (FFI/ABI/JSON 契約)
- 第三者ライセンス: `src/rust/piper-plus-g2p/THIRD_PARTY_LICENSES.md` に CMU Pronouncing Dictionary (BSD-style) と pypinyin (MIT) のセクションを追加 (bundled-dicts で埋込む辞書の attribution)
- FFI: `default_languages()` 関数を新設し、有効な Cargo features と `bundled-dicts` の有無に応じて `piper_plus_g2p_create(NULL)` の言語セットを動的構築 (`src/rust/piper-plus-g2p/src/ffi.rs`)
- 並行性検証: `tests/PiperPlusG2PTests/ConcurrencyTests.swift` を追加。`Phonemizer.@unchecked Sendable` を 60 並列 phonemize / 20 並列 init / 100 反復 deinit で実証
- README 更新: [`README.md`](README.md) / [`README_EN.md`](README_EN.md) Interfaces セクションに iOS Swift G2P (SPM) 行追加。`docs/guides/platform/ios-integration.md` Distribution Selection 表に G2P-only 行追加。crate `src/rust/piper-plus-g2p/README.md` を v0.4 に統一、Feature Flags 表に `ffi` / `bundled-dicts` 追加、C FFI 章を iOS 統合向けに拡充
- ビルド成果物の `.gitignore`: `*.xcframework/` / `*.xcframework.zip` / `build-g2p-ios/` / `.build/` / `.swiftpm/` / `*.xcodeproj/` / `DerivedData/` を追加
- **CI 整備 (PR で実行されるようにした)**:
  - `release-shared-lib.yml` に `pull_request` trigger と path filter を追加。`build-g2p-ios` / `assemble-g2p-xcframework` のみ PR で smoke run、`build-shared` / `build-ios` / `assemble-xcframework` / `build-android` / `release` は `if: github.event_name != 'pull_request'` で tag push 限定を維持
  - `.github/workflows/swift-g2p-ci.yml` 新設 — macOS runner で `cargo build --target {aarch64,x86_64}-apple-darwin` で staticlib を universal 化、`cbindgen` でヘッダ生成、`xcodebuild -create-xcframework` で local macOS xcframework 組立、`Package.swift` を CI 専用 path-based manifest に置換 (workspace ephemeral)、`swift test --filter PiperPlusG2PTests` を実行。`PhonemizerTests` / `GoldenPhonemeTests` / `ConcurrencyTests` 全 3 ファイルを **PR で自動検証**できる
- **テスト追加**:
  - `src/rust/piper-plus-g2p/src/ffi.rs::tests`: `default_languages()` の各 feature 組合せ (full / rule-based / no-bundled-dicts) と `register_one()` の正常系・UnsupportedLanguage / Phonemize エラー系を 7 件追加。lib tests 396 → **403** に増加 (`cargo test --features all-languages,naist-jdic,bundled-dicts,ffi`)
  - `tests/PiperPlusG2PTests/PhonemizerTests.swift`: assertion を Golden fixture と整合する形で強化。`isEmpty` チェックのみだった 8 言語テストに、具体トークン照合 (en `h`, ja `k/o/n/i/a`, es `o/l/a`, fr `b`, pt `o`)、最小トークン数の `XCTAssertGreaterThanOrEqual`、中国語の PUA tone marker 検出 (E000–F8FF) を追加

#### iOS shared-lib を xcframework として配布開始 (Issue #377)

iOS 利用シナリオ (Dart FFI / Godot / Swift / SPM) に対応する xcframework 配布を成立させた。device (arm64) + simulator (arm64+x86_64 universal) の両 slice を含む。

- 新 artifact: `libpiper_plus-ios-v${VERSION}.xcframework.zip` (device slice + simulator universal slice)
- **`piper_plus.xcframework` は static archive** — Xcode では **"Do Not Embed"** で取り込む (リンクのみ)。`onnxruntime.xcframework` は dynamic framework のため **"Embed & Sign"** が必須
- 利用者ガイド: [`docs/guides/platform/ios-integration.md`](docs/guides/platform/ios-integration.md) (Dart / Godot / Swift 横断、トラブルシューティング、App Store 提出チェックリスト含む)
- Swift プロジェクト向け手順: [`examples/swift/README.md`](examples/swift/README.md)

#### Swift `import PiperPlus` を有効化する `module.modulemap` 同梱

- xcframework の各 slice の `Headers/` に `module.modulemap` を CMake で自動生成して同梱
- Swift consumer は `import PiperPlus` で `piper_plus.h` の C API surface 全体にアクセス可能
- 仕様: 非 framework 形式の `module PiperPlus { umbrella header "piper_plus.h" export * module * { export * } }`

#### Swift Package Manager マニフェスト (`Package.swift`) を repo 直下に配置

- consumer は `Package.swift` 一行 (`from: "1.13.0"`) のみで `import PiperPlus` 利用可能 — ORT は wrapper target 経由で **transitive 解決**される
- 内部構造: Swift `target` (`PiperPlus`、`@_exported import PiperPlusBinary` で C API を再エクスポート) + `binaryTarget` (`PiperPlusBinary`、xcframework.zip 参照) + `dependencies: [onnxruntime-swift-package-manager]`
- `platforms: [.iOS(.v15)]` のみ宣言 (macOS / visionOS / Mac Catalyst slice は v1.13.0 では無し、M5 候補)
- メンテナがリリースタグ push **前** に `Package.swift` の version + checksum を `dev` 上で手動更新する運用 (sherpa-onnx 方式、`Package.swift` 冒頭コメントに手順記載)
- リリース時に `release` ジョブが Package.swift の checksum が placeholder ("0000...") でないこと、および xcframework zip の SHA-256 と一致することを CI ガード

#### iOS shared-lib 取得経路を Microsoft 公式 CDN に切替

ONNX Runtime の旧 GitHub Releases zip は Microsoft が配布チャネルを CocoaPods/SPM/CDN に一本化したため削除されており、v1.11.0 以降 `Build iOS arm64` ジョブが連続失敗していた。**release ジョブの巻き添えで Linux/Windows/macOS/Android shared-lib も Releases に上がっていなかった問題を解消**。

- curl URL を `https://download.onnxruntime.ai/pod-archive-onnxruntime-c-${VERSION}.zip` に変更
- sha256 検証ステップ追加 (1.17.0 = `1623e1150507d9e5...db871`)
- CDN zip は Mach-O dylib のみで static `.a` 不在のため、利用者は `Embed & Sign Frameworks` で組込

#### `PrivacyInfo.xcprivacy` informational reference を xcframework に同梱

- xcframework root に空の Privacy Manifest (`NSPrivacyTracking=false`、3 配列空) を配置
- **注意:** Apple App Store の Privacy Manifest スキャナは `*.framework` bundle root の `PrivacyInfo.xcprivacy` を読む。static archive xcframework のルート配置は **informational reference のみ** — consumer app target で `PrivacyInfo.xcprivacy` を別途用意する必要あり
- 推奨 declaration テンプレートと Required Reason API カテゴリ (SystemBootTime / FileTimestamp / DiskSpace) を [`docs/guides/platform/ios-integration.md`](docs/guides/platform/ios-integration.md#app-store-submission-checklist) に記載

#### iOS リンクエラー検出 CI ガード

- `release-shared-lib.yml` の `Verify symbol resolution` を 2 段階チェックに強化
  - ORT-prefix 系 (`_Ort*` 等) の未解決 → fail (ORT version drift 検出)
  - project-internal 系 (`_piper_plus_*`, `_openjtalk_*`, `__ZN<N>piper`) の未解決 → fail (iOS 除外バグ検出)
- desktop-only TU を iOS で除外して呼び出し側だけ残るバグ (例: `openjtalk_phonemize.cpp` から `openjtalk_is_available` を呼ぶ場合) を CI で検出

#### Voice Cloning + SSML を C++/WASM ランタイムに展開

v1.12.0 で 5 ランタイム (Python/Rust/C#/Go/WASM) に展開した SSML / Voice Cloning を、残る C++ と WASM の TTS 統合面に拡張。

- **C++ SSML parser** (`src/cpp/ssml.{hpp,cpp}`, CLI `--ssml`) — W3C subset (`<speak>`, `<break>`, `<prosody rate>`) を CLI バイナリで処理可能に。C API には未エクスポート (FFI 経由は次フェーズ)。Issue #444, PR #477
- **WASM SSML parser** (`src/wasm/openjtalk-web/src/index.js::synthesizeSsml`) — `isSsml` で自動 dispatch、`synthesizeSsml` で silence 挿入 + length_scale 切替。`@piper-plus/g2p` の `parseSsml` を再利用。PR #479
- **WASM Voice Cloning 統合** — `synthesizeFromReferenceAudio` / `speakerEmbedding` option を `PiperPlus` クラスに追加 (`src/wasm/openjtalk-web/src/synth.js`)。Rust 側 wasm bindings は v1.12.0 で既に提供済みだったが、`piper-plus` npm 経由の API として完成。PR #478
- **C++ Voice Cloning CLI フラグ** — `--reference-audio` / `--speaker-embedding` / `--speaker-encoder-model` を CLI バイナリに追加 (C API は `speaker_embedding` テンソル経路で動作、ECAPA-TDNN 推論 API はスタブ)。PR #475, #476

これにより SSML サポートは **Python/Rust/C#/Go/WASM/C++ の 6 ランタイム**、Voice Cloning は **6 ランタイム**で利用可能。

#### マルチランタイム RTF ベンチマーク

7 ランタイム横断の Real-Time Factor (RTF) ベンチマーク基盤を整備し、GitHub Pages に常時公開。

- `tools/benchmark/multi-runtime/` で Python/Rust/C#/Go/WASM/C++ + CLI の RTF を統一フォーマットで計測 (baseline_v1.json)
- 結果を GitHub Pages (`https://ayutaz.github.io/piper-plus/bench/multi-runtime/`) にプッシュ。`dev` ブランチへの merge ごとに自動更新 (`.github/workflows/pages-multi-runtime-bench.yml`)
- v1.12.0 baseline と差分回帰検出用に CI gate を準備 (PR #484, #480, #483, #485, commits 4367e958 / f08cd417 / 2177dbd9 / 7bf3dc59)
- README.md に公開 URL リンクを追加 (2177dbd9)

#### サーバー機能拡張

- **真のストリーミングチャンク + Phoneme Timing 配線** — `?streaming=true` で文単位の真のチャンク配信 + 各チャンクに phoneme-timing メタデータを同梱 (Python/Go ランタイム)。`/api/phoneme-timing` で streaming にも対応。PR #481
- **Bearer Token 認証 + Rate Limit** — `docker/python-inference/inference.py` (OpenAI 互換 Docker サーバー) に `PIPER_API_KEYS` 環境変数 (カンマ区切りリスト) による bearer auth と `slowapi` ベースの rate limit を追加。PR #475

#### Post-v1.12.0 fixes

- npm: `piper-plus` の subpath exports に types フィールドを追加 (`./timing`, `./streaming` 等は types 提供、`./phonemizer` / `./wasm/*` は意図的 skip)。PR #465 (ec4c5b7d)
- `piper.http_server` の `/v1/audio/speech/languages` で `sv` (スウェーデン語) が欠落していた問題を修正。commit 2f4efaf9

#### Post-v1.12.0 documentation

- v1.12.0 リリース直後のドキュメントドリフト一括修正 (HiFi-GAN archived 注記、CLAUDE.md / README 整合)。PR #466 (3414bb7c)
- README.md / CHANGELOG / docs/spec の v1.12 以降サイクル整合監査 (本 PR)

#### Post-v1.12.0 tests

- Go: `voice` / `download` カバレッジを 793 → 拡充 (LJSpeech 互換性パス含む)。PR #469 (4f49d27a)
- G2P: zh-en loanword / pt dialect / SSML エッジケースのテスト拡充。PR #472 (4ff0eb7b)

#### Post-v1.12.0 chore

- Docker: arm64 build/test matrix を CI に追加 (`docker-build-test.yml`)。PR #473 (16fa5091)
- Docker: GitHub Actions runner の disk 枯渇対策 (build artifact prune + buildx cache strategy)。PR #482 (22c78236)
- CodeQL: `cpp/loop-variable-changed` をルール全体で suppress (false positive 多数のため)。PR #492 (cd6a9d8a)
- CI: `deploy-huggingface.yml` / `release-shared-lib.yml` に `scripts/generate_model_card.py` 駆動の `MODEL_CARD.md` + `LICENSE_ATTRIBUTIONS.md` 生成 step を注入。 HF Space deploy / GitHub Release artifact に attribution が確実に同梱され、 dataset attribution の脱落を構造的に防止 (M3.2 / PR #511 実装完了)
- CI: OpenSSF Scorecard を週次 + dev push で実行する `scorecard.yml` を追加 (`docs/proposals/ci-expansion-2026-05.md` §3.6 Week 1 由来、 Top 10 外の supply-chain hardening)。 SARIF を code scanning に upload + `scorecard.dev` に publish、 PR を block しない informational tier
- CI: `scripts/check_changelog_format.py` + `changelog-format.yml` + pre-commit hook (`changelog-format`) で keep-a-changelog 形式 validator を追加 (`docs/proposals/ci-expansion-2026-05.md` §3.7 Tier S #1 由来)。 H1 / Unreleased / バージョン header date format / 降順を error tier、 セクション名 / 重複を warning tier として検査。 既存 historic な絵文字付きセクションは bootstrap baseline として allowlist 化
- CI: `scripts/check_readme_heading_tree.py` + `readme-heading-tree-parity.yml` で multilingual README の heading tree parity を informational tier で追加 (`docs/proposals/ci-expansion-2026-05.md` §3.7 Tier S #2 由来)。 既存 `check_readme_h2_parity.py` (H2 個数のみ) を補強し、 H2/H3/H4 の structure と H2 section 内の H3 count を比較。 default tolerance ±5 で既存翻訳 drift を bootstrap baseline 吸収、 新規 drift 拡大のみ警告。 PR を block しない
- CI: `scripts/ci_observability_snapshot.py` + `ci-observability-snapshot.yml` で 週次の CI flake / cancel / skip trend snapshot を追加 (`docs/proposals/ci-expansion-2026-05.md` §3.9 #1 由来、 Top 10 外の CI observability)。 過去 7 日の `gh run list` を workflow 単位に集計し、 cancellation_rate > 10% の workflow を "flake watch" 候補として artifact 出力。 M1.1 cancelled baseline alarm (PR 単位の silent skip gate) の trend 観測層
- CI: `.github/workflows/rust-miri-nightly.yml` で nightly Rust miri を週次実行 (`docs/proposals/ci-expansion-2026-05.md` §3.1 Sanitizer 拡張 #8 由来、 Top 10 外)。 piper-plus-g2p crate の 27 箇所の unsafe ブロック (FFI 系を除く Rust internals) に対する Undefined Behavior / stacked borrow / aliasing 違反を `cargo +nightly miri test --skip ffi` で informational 検出。 timeout 60 min、 PR を block しない

### Limitations (v1.13.0 iOS xcframework)

| Item | Status | Notes |
|------|--------|-------|
| ONNX Runtime bundling | ✗ | xcframework に同梱されない。SPM 経由なら transitive 解決、それ以外は consumer が CocoaPods / 手動 DL で取得 + Embed & Sign |
| OpenJTalk 辞書 (日本語 TTS 必須) | ✗ | App Sandbox で auto-DL 不可。consumer app が `open_jtalk_dic_utf_8-1.11/` を bundle に同梱して `dict_dir` で渡す ([guide](docs/guides/platform/ios-integration.md#step-4-japanese-tts-only-bundle-the-openjtalk-dictionary)) |
| macOS / Mac Catalyst slice | ✗ | M5 候補 — 現状 xcframework は iOS のみ。`Package.swift` も `platforms: [.iOS(.v15)]` のみ |
| visionOS / tvOS / watchOS slice | ✗ | M5 候補 — ORT visionOS 対応待ち |
| `.dSYM` for crash symbolication | ✗ | xcframework binary は stripped、別 issue 追跡 |
| App Extension / App Clip | ✗ | piper-plus + ORT (~35 MB) が 32 MB / 10 MB 制限を超過 |
| Privacy Manifest 自動スキャン | ✗ | static archive xcframework は Apple スキャナの読取り対象外、consumer app target に追加要 |
| C++ symbol leak (ODR) | ⚠ | `fmt::` / `spdlog::` / `piper::` symbols は static archive に export される。他 C++ 静的ライブラリと衝突する場合は Other Linker Flags に `-Wl,-load_hidden,...libpiper_plus.a` を追加 |

### Deprecated

#### `libpiper_plus-ios-arm64-${VERSION}.tar.gz` (device-only、`.framework` 同梱 tar.gz)

- v1.13.0 では新 xcframework.zip と並行配布 (移行期間)
- **v1.14.0 で削除予定** — `libpiper_plus-ios-v${VERSION}.xcframework.zip` への移行を推奨
- v1.13.0 の `release-shared-lib.yml` は tar.gz 生成時に `::warning::` を出力するため利用者が deprecation を即時認識可能

### Fixed

- iOS / Linux / Windows / macOS / Android shared-lib リリースパイプラインを復旧 (Issue #377、v1.11.0 以降の停止)
  - `release` ジョブの `needs:` が `build-ios` 失敗で全 OS artifact のアップロードを止めていた
- Bundle size gate: Android AAR ビルドが prebuilt `libpiper_plus.so` 欠如で永久 SKIP となっていた問題を修正 (Issue #494)
  - `bundle-size-gate.yml` に `build-android-shared-libs` matrix job (arm64-v8a / armeabi-v7a / x86_64) を追加し、`release-shared-lib.yml` と同じ NDK r26c + ORT 1.20.0 + 16 KB page-align で `libpiper_plus.so` をビルド。bundle-size ジョブが artifact を `android/piper-plus-g2p/src/main/jniLibs/<ABI>/` に配置してから `assembleRelease` を実行することで `maven::piper-plus-g2p-android` の Observed サイズが取得可能に
  - `scripts/check_ort_versions.py` の `TARGETS` に `bundle-size-gate.yml` を追加し、ORT バージョン drift gate の対象に統合 (Copilot review fix)
- スウェーデン語 (sv) の単語単位 言語判定 (per-word LID) を全 7 ランタイムで復旧・統一 (Issue #539)。`å`/`ä`/`ö` を含む語 (例: `så` / `och` / `för` / `är`) が英語と誤判定されていた回帰を修正 (#297 で全ランタイム実装 → #300 の g2p パッケージ抽出で Python/Rust から脱落 → 残存コピーが drift、WASM は char-level の別実装)。**保守的ポリシー** (strong indicator = `å`/`Å` または 46 語の function-word リスト完全一致のみ。`ä`/`ö` 単独は独語/フィンランド語/借用語と共有のため不十分) で再実装。全ランタイムが byte-identical な `sv_function_words.json` をロードし、新規 sync gate (`scripts/check_swedish_lid_consistency.py` + `docs/spec/swedish-lid-mirrors.toml`、ZH-EN loanword gate と同型) が 7 データミラー + 6 fixture ミラーの byte-for-byte 一致を強制。cross-runtime parity fixture matrix で一致を実証。学習済み 6lang モデルは sv 未含有のためデフォルト推論は不変、独立 G2P 用途と将来の sv モデルに影響
- v1.12.0 で配布された config.json (つくよみちゃん / 6lang base) に未 PUA 化の multi-codepoint 音素 (`ɔɪ` / `œ̃` / `ɐ̃`) が混入し、Windows の C++ 推論が `is not a single codepoint` で失敗していた問題を修正 (Issue #385、PR #389)。`pua.json` を v1 → v2 化して該当音素を PUA 割り当て + 全 6 ランタイムの PUA テーブルを同期 + `map_token(strict=True)` で未知トークンを fail-fast 化
- Windows の C++ ランタイム (`piper.exe`) でつくよみちゃん 6lang モデルの `--download-model` が PowerShell `-Command $args` のバグにより URL / 出力先が空になりダウンロードできなかった問題を修正 (PR #557)。あわせて multi-codepoint 音素 (`ɔɪ` / `œ̃` / `ɐ̃` 等) の raw キーが C++ パーサに漏れ、Windows のつくよみ / base config で推論が失敗していた v1.12.0 の回帰をガードする regression CI を追加 (実 config / `pua.json` データ修正は上記 PR #389、本 PR は再発防止 CI)
- 推論の EOS region trim を全 6 ランタイム (Python / Rust / Go / C# / WASM / C++) で全入力に対し適用し、ファインチューニング済みモデル (つくよみちゃん等) で末尾音節が二重に聞こえる問題を修正 (Issue #499、PR #506 / #507)。**挙動変更注記:** 本修正により全モデル・全ランタイムで出力音声の末尾フレーム (`ceil(durations[-1])` 由来の EOS region) が trim され、v1.12.0 比で出力音声長・末尾が変化する。バグ修正だがデフォルト出力が変わるため明示 (破壊的変更ではない)
- Go の text splitter を Python / Rust の canonical 実装 (post-consume 方式) に統一し、CJK 句読点 + 閉じ括弧パターンが 1 文として誤結合されていた問題を修正 (Issue #346、PR #504)
- リリース QA で判明した Windows ビルドの諸問題を修正 (PR #505): `.gitattributes` の `eol=lf` catch-all 追加 (CRLF チェックアウトで gofmt / byte-sync gate が破損)、contract gate スクリプトの cp932 / cp1252 コンソール `UnicodeEncodeError` crash、`check_secret_path_reference` の Windows パス処理
- v1.12.0 の MB-iSTFT-VITS2 ONNX (つくよみちゃん等) を Docker python-inference / webui サーバや Rust / C++ ランタイムで実行すると `Required inputs (speaker_embedding, speaker_embedding_mask) are missing` で 500 エラー / ロード失敗していた問題を修正 (Issue #426、PR #443)。推論側 4 箇所で speaker_embedding 入力の有無を ONNX セッションから動的判定し、未使用時は zero embedding + mask=0 を feed する fallback を追加。実モデルでの回帰を防ぐ integration gate も追加

### Security

- `release-shared-lib.yml` の workflow-level permissions を `contents: read` に縮小、`release` ジョブのみ `contents: write` を opt-in
- tag validator の regex を `^[0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9.-]+)?$` に anchored 化 (例: `1.0.0-malicious$(rm)` 形のタグ injection を拒否)
- `src/python_run/requirements.txt`: `g2p-en` 経由 transitive 依存 (`g2p-en` → `nltk` → `joblib`) にセキュリティ下限を明示 (`nltk>=3.9.4` / `joblib>=1.5.0`)。診断手順を `docs/getting-started/troubleshooting.md` ("Security Audit CI Issues") に追加
  - 2026-05 の `Security Audit / pip-audit (Python)` dev push 失敗は **上流 advisory データ欠陥** が原因で piper-plus 側のコード/依存問題ではない: `nltk` `PYSEC-2026-97` (CVE-2026-0846) と `joblib` `PYSEC-2024-277` (CVE-2024-34997) が 2026-05-20 に `last_affected` 欠落で生成され、安全な `nltk 3.9.4` / `joblib 1.5.3` を含む全バージョンが flag された (同一 commit が後の schedule run では pass)。`pypa/advisory-database` PR #289 ("Update records generated incorrectly", 2026-05-21) で修正済み
  - 下限ピンは将来の dependency resolution が真に脆弱なバージョンへ退行するのを防ぐ regression insurance
- `.github/workflows/security-audit.yml`: pull_request `paths` に `src/python_run/requirements.txt` を追加。従来 `setup.py` のみが対象で、実際の依存定義 source (setup.py がパースする requirements.txt) の変更が PR の pip-audit gate を通らなかった漏れを修正
- 依存ライブラリの脆弱性対応: `protobufjs` 7.5.6 → 7.5.8 (CVE-2026-45740、PR #530)、`idna` 3.10 → 3.15 (CVE-2026-45409、PR #531)、`gitpython` 3.1.49 → 3.1.50 (GHSA-mv93-w799-cj2w、PR #437)、Dependabot security alert 対応で `urllib3` (high) / `@protobufjs/utf8` (medium) を更新 (PR #450)
- HTTP サーバーのログインジェクション対策 (CodeQL `py/log-injection`、PR #435)、および C# の `cs/unsafe-double-checked-lock` 修正 + CodeQL ノイズ削減 (PR #434)
- Rust の `pyo3` advisory RUSTSEC-2026-0176 / RUSTSEC-2026-0177 を `.cargo/audit.toml` で ignore (rust-numpy が `pyo3` 0.24 系に pin しており上流更新待ち、PR #558 / #559)

## [1.12.0] - 2026-05-04

### Changed (Breaking)

#### Decoder を MB-iSTFT-VITS2 に統一 (HiFi-GAN Generator 削除)

VITS の Decoder を **MB-iSTFT (Multi-Band inverse STFT) + PQMF** に完全に置き換え、HiFi-GAN `Generator` クラスを削除。`upsample_rates(16x) * iSTFT_hop(4x) * PQMF_subbands(4x) = 256x` で従来と同じ総倍率を維持しつつ Decoder 計算量を削減し、CPU 推論を **2.21x 高速化** (Mean infer 168.2ms → 76.2ms, RTF 0.066 → 0.037, 100 phoneme p50)。ONNX 互換 iSTFT は DFT 行列方式 (`OnnxISTFT`) で `F.conv_transpose1d` に展開し opset 15 で動作。出力形状 `[B, 1, T]` を維持しているため、C#/Rust/Go/WASM/C++ ランタイム は変更不要 (既存 HiFi-GAN ONNX も推論側は引き続き動作)。`--quality high` も MB-iSTFT で対応 (resblock="1" + 512ch + (4,4) upsample)。

**Breaking changes:**

- `--mb-istft` フラグは廃止 (常に有効)。
- `Generator` クラス削除 — 既存 HiFi-GAN `.ckpt` からの学習再開・FT は不可。MB-iSTFT 対応の base モデル (`piper-plus-base`) と追加モデル (`piper-plus-tsukuyomi-chan` 等) を本マージ時に再公開。
- `_check_decoder_architecture_compatibility` 削除 (不要になったため)。
- `mb_istft` hparam 削除。

**保持される CLI:**

- `--c-sub-stft` (sub-band STFT loss 重み, デフォルト 1.0)
- `--sub-stft-fft-sizes` / `--sub-stft-hop-sizes` / `--sub-stft-win-sizes`

**学習済みモデル:** 6lang MB-iSTFT 75 epoch ベース + つくよみちゃん MB-iSTFT 500 epoch FT。
**実装:** `vits/mb_istft.py`, `vits/stft_onnx.py`, `vits/stft_loss.py`。Issue #268, PR #320。

#### .NET 全プロジェクトを `net10.0` LTS に移行

C# プロジェクト (`PiperPlus.Core`, `PiperPlus.Cli`, テスト、Bench) の Target Framework を **`net10.0` LTS** に直接移行。`net6.0` / `net8.0` / `net9.0` のサポートは廃止。NuGet パッケージ `PiperPlus.Core 0.3.0` / `PiperPlus.Cli 0.3.0` 以降は **`net10.0` LTS のみ**。詳細: PR #374 (本 v1.12.0 Chore 内記載)。

#### `PiperVoice.phonemize()` の戻り値セマンティック変更

戻り値**型** `list[list[str]]` は v1.11.0 から変更ないが、**意味論が変わった**:

- **v1.11.0 以前**: 入力テキスト全体を 1 つの phoneme シーケンスとして音素化し、常に **1 要素** のリスト (`[whole_text_phonemes]`) を返していた。
- **v1.12.0 以降**: 入力テキストを終止符で文単位に分割し、文ごとに音素化して **N 要素** のリストを返す。SSML (`<speak>...`) 入力は単一ユニットとして構造保持。

**影響を受ける呼び出しパターン:**

- `phonemes_list = voice.phonemize(text); ids = voice.phonemes_to_ids(phonemes_list[0])` のように **`[0]` で固定アクセスしている既存コードは複数文を渡すと壊れる** (1 文目のみ処理されることになる)。
- 全文を一括処理したい場合は `for phonemes in voice.phonemize(text): ids = voice.phonemes_to_ids(phonemes)` に書き換える、または事前に `text` を 1 文に絞る。

**移行ガイド:** `docs/migration/v1.11-to-v1.12.md` 参照。
**実装:** `src/python_run/piper/voice.py:phonemize()` (#367)

### Added

#### 全7ランタイムで短テキスト合成品質改善 (Strategy A/B/C)

短テキスト (1-2文節) 合成時のノイズ・歪み・0秒出力問題に対する緩和策を全7ランタイム (Python/Rust/C#/C++/Go/JS-WASM/CLI) に並列実装。VITS の構造的制限 (rhasspy/piper#252) に起因する既知問題を解消。Silence Padding + Post-trim (Strategy A)、Dynamic Scales Adjustment (Strategy B)、SSML `<break>` Auto-injection (Strategy C, SSML対応4ランタイムのみ) を組み合わせる。設定仕様: `docs/spec/short-text-contract.toml` (#337)

#### Voice Cloning + SSML + Wyoming Docker 統合 (#331)

- **Voice Cloning**: 5ランタイム (Rust/C#/Go/WASM/C++) に Speaker Encoder (ECAPA-TDNN) + `speaker_embedding` テンソル対応を統合。参照音声から話者特徴を抽出し、未知話者の声質で TTS 合成可能。
- **SSML 基本サポート**: `<speak>`, `<break>`, `<prosody rate="...">` を Python/Rust/C#/Go の 4 ランタイムで実装 (W3C SSML サブセット準拠、Python 62 / Rust 39 / C# 59 / Go 67 テスト)。
- **MOS ベンチマークツール**: サンプル生成、PESQ/STOI 等メトリクス計算、調査フォーム生成 (`tools/benchmark/`)。
- **iOS/Android ビルド CI**: libpiper_plus のモバイルクロスコンパイル (iOS arm64 + Android arm64-v8a/armeabi-v7a/x86_64)。
- **Wyoming Docker**: HA 統合用の Docker Compose 環境 + ガイド (`docker/wyoming/`, `docs/guides/integration/home-assistant.md`)。
- **モデル投稿ガイド**: `CONTRIBUTING_MODELS.md` + GitHub Issue テンプレート。

#### 汎用 Colab ファインチューニングノートブック (#324)

LJSpeech 形式 (`wavs/` + `metadata.csv`) のカスタムデータセットで piper-plus モデルをファインチューニング可能な汎用 Colab ノートブックを追加。事前学習済みベースモデル (6lang/つくよみちゃん等) からの転移学習に対応。

#### Python ランタイム ストリーミング文単位分割 (新規)

[Zenn スクラップ (kun432 氏)](https://zenn.dev/kun432/scraps/cddbfcd75b8b34) で指摘された「Python ランタイムだけ `synthesize_stream_raw()` に文単位分割が無く、HTTP `?streaming=true` でも単一チャンクで返ってしまう」問題を解消。

**新規モジュール:**

- `piper.text_splitter` (`src/python_run/piper/text_splitter.py`)
  - `split_sentences(text) -> list[str]` — 終止符 `.`/`!`/`?`/`。`/`！`/`？` および直後の閉じ括弧 (`」 』 ） ］ 】 ｣ ” ’ »` 等) を扱う
  - Rust `piper-core/src/streaming.rs::split_sentences` と同等の挙動 (post-consume 戦略)

**PiperVoice 修正:**

- `phonemize()` が複数文の入力を文ごとに音素化し `list[list[str]]` を **N 要素** で返すよう変更 (v1.11 までは常に 1 要素) — **挙動が破壊的に変わるため上記 "Changed (Breaking)" セクション参照**
- SSML (`<speak>...`) は単一ユニットとして扱い構造保持
- 既存呼び出し側 (`synthesize_stream_raw` / `synthesize_with_timing`) は無修正で複数チャンク化が動作

**互換性:**

- HTTP `?streaming=true` (PR #361 の FastAPI `StreamingResponse`) も真のチャンク配信になる
- `phonemize()` を直接呼んでいる外部コードは戻り値の要素数前提を見直す必要あり

**設定仕様:**

- `docs/spec/text-splitter-contract.toml` の Implementations 一覧に Python 実装を追加
- 終止符 6/7、閉じ括弧 14/14 (Rust と同状態、U+FF0E は spec 通り未対応)

**テスト:**

- `tests/test_text_splitter.py` (18 件) — Rust テストスイートを移植
- `tests/test_voice_streaming.py` (8 件) — `synthesize_stream_raw()` の文単位 yield と SSML ハンドリング

**関連:** PR #367 (続編元: PR #361 FastAPI 移行)

#### Python ランタイム Phoneme Timing 機能 (新規)

Python ランタイムに完全な phoneme timing 出力機能を追加。VITS Duration Predictor から音素ごとの開始時刻・終了時刻・継続時間を抽出し、JSON/TSV/SRT 形式で出力可能。

**新規モジュール:**

- `piper.timing` モジュール (`src/python_run/piper/timing.py`)
  - `PhonemeTimingInfo`, `TimingResult` データクラス
  - `durations_to_timing()`, `timing_to_json/tsv/srt()`, `timing_to_json_compact()`
  - `build_phoneme_id_reverse_map()` (PUA char 対応)

**PiperVoice 拡張:**

- `synthesize_with_timing(text, wav_file=None, ...) -> tuple[bytes, TimingResult | None]`
- `has_duration_output` プロパティ (モデル対応判定)
- `_synthesize_ids_core()` 内部メソッド (durations 取得 + original_phoneme_ids 保持)

**HTTP エンドポイント:**

- `POST/GET /api/phoneme-timing` (FastAPI、`format=json|tsv` 対応)
- `language` / `language_id` クエリパラメータで多言語対応

**設定:**

- `PiperConfig.hop_size` フィールド追加 (デフォルト 256、`config.json` の `audio.hop_size` から読込)

**互換性:**

- Rust/Go/C++/C# の既存実装と byte-for-byte 互換
- 既存の `synthesize()`, `synthesize_stream_raw()`, `synthesize_ids_to_raw()` API は完全な後方互換性を維持

**テスト:**

- `tests/test_phoneme_timing.py` (44 テスト)
- `tests/test_voice_timing.py` (22 テスト)
- `tests/test_http_timing.py` (14 テスト)
- `tests/test_config_fallback.py` に hop_size テスト 5 件追加

- 全言語 Zero-Shot TTS 推論対応 — Go・WASM・Python Runtime で `speaker_embedding` テンソル入力を実装し、C++/C#/Rust に続き全 6 実装が zero-shot 推論に対応
- クロス言語 speaker embedding テスト 92 件 — ユニットテスト 73 件 + E2E テスト 19 件（C++/C#/Rust/Go/WASM/Python 全実装を網羅）
- Zero-Shot テスト用 ONNX モデル生成スクリプト (`scripts/generate_zero_shot_test_model.py`) — CI 用の最小 zero-shot ONNX モデルを自動生成
- C++/C#: NumPy v2.0 .npy パーサーサポート追加（ヘッダー長 uint16→uint32）とテストケース追加
- WASM: `speaker_embedding` 未指定時のゼロベクトルフォールバック追加
- WASM: embedding 次元バリデーション（192 次元であることを確認）
- WASM: ONNX モデル入力名のケイパビリティ検出追加
- C++: JSONL `speaker_embedding` サイズバリデーションと警告ログ追加
- C++/Go: ゼロベクトル speaker embedding フォールバック時の警告ログ追加
- C++: `speaker_embedding` 指定時にモデルが対応入力を持たない場合の警告追加
- Python Training: CLI 引数 `--c-dino`, `--kl-annealing-epochs`, `--max-spec-length`, `--no-compile` を追加
- Python Training: ExponentialLR スケジューラーサポート追加（`--lr-scheduler exponential`）
- Python Inference: `warmup_onnx_session` で `speaker_embedding` サポートを追加
- CI: `go-ci` を `ci-required` ゲートに追加
- CI: `test_short_text_mitigation.py` / `.js` をワークフローに追加

### Fixed
- Go `.npy` ファイルパーシング修正 — speaker embedding の NumPy v1/v2 フォーマット読み込みが正常に動作するよう修正
- Rust JSONL `speaker_embedding` 上書きバグ修正 — JSONL 入力時に speaker_embedding フィールドが意図せず上書きされる問題を解消
- C++ `piper_plus_c_api` の `std::optional` API 誤用を修正
- 全言語で stale な `speaker_embedding_mask` テンソル入力を削除
- C#/Rust/Go: SpeakerEncoder メルスペクトログラム形状を `[1,80,T]` → `[1,T,80]`（CAM++ 互換）に修正
- C#/Rust/Go: SpeakerEncoder FFT ウィンドウを 512 → 400（Kaldi 25ms@16kHz）に修正
- C#/Rust/Go: SpeakerEncoder の CMVN（バンド単位平均減算）未適用を修正
- C#/Rust/Go: SpeakerEncoder のハードコードされた ONNX 入力名を動的ルックアップに修正
- C++/C#/Rust: NumPy v2.0 .npy パーサーの uint16 → uint32 ヘッダー長修正
- 全言語: `noise_scale` デフォルトを 0.667/0.8 → 0.4/0.5 に更新（zero-shot 最適化済み値）
- Go: config キー名の不一致 `noise_w` → `noise_scale_w` を修正
- Go: `speaker_embedding` 指定時の dual-mode sid 制御を修正
- C#: embedding 未指定時の dual-mode sid フォールバックを修正
- C#: `PiperConfig InferenceConfig` の stale なデフォルト値を修正
- Python Training: チェックポイントリジューム後の EMA CPU/GPU デバイスミスマッチを修正
- Python Training: シングル GPU リジューム時に EMA state が破棄される問題を修正
- Python Training: FP16 学習時の DINO center dtype ミスマッチを修正
- Python Training: SCL dtype ミスマッチ（CamPP FP32 vs FP16）を修正
- Python Training: `TextEncoder` の speaker conditioning が `x_mask` なしで適用される問題を修正
- Python Training: `--lr-warmup-epochs`, `--lr-min`, `--spk-emb-noise-sigma` CLI 引数が有効化されるよう修正
- Python Training: `val_dataloader` のワーカー数を最大 2 にキャップ
- Python Inference: 廃止された `--reference-audio` コードパスを削除
- Python Inference: `export_onnx.py` のシングルスピーカー+prosody での positional arg バインディングを修正
- Python: `speaker_embedding_mask` の残存参照を export/tests から削除
- C++: `--output-dir` CLI オプションのダブルダッシュ欠落を修正
- WASM: `prosody_features` のゲーティングを ONNX モデル入力名で条件分岐するよう修正
- Rust: E2E テストから `#[ignore]` を削除（モデルファイルがリポジトリにトラッキング済み）
- Golden test フィクスチャを `n_fft=400` で再生成

### Removed

- 死んだコード `src/python_run/piper/espeak_phonemizer.py` を削除 (piper-plus は推論時に espeak-ng に依存しない)
- Python ランタイムから HTS voice 依存を完全除去 (#342) — Python は pyopenjtalk-plus パスのみ。C++/Go/Rust/WASM の OpenJTalk バックエンドは引き続き利用
- Unity UPM を削除し関連ドキュメント整理 (#341)

### Changed

- HTTP server を Flask から **FastAPI に移行**、`?streaming=true` で `StreamingResponse` による真のチャンク配信に対応 (#361)
- Go Docker — Debian 化 + ORT 修正 + OpenJTalk 日本語 G2P + `serve` サブコマンド対応 (#332, #334)
- README の「30秒で試す」を OS 別ワンライナー化 + CLI バイナリ選択ガイド追加 (#360)
- Rust `piper-python` バインディングを非推奨の `synthesize_text()` から `synthesize_with_params()` に移行
- CI ワークフローを更新し、全 speaker embedding テストを実行するよう変更

### Fixed

- 短文「こんにちは。」が「あこんにちはた」と崩壊する問題を修正 (C++ ランタイム、UTF-8 コードポイントベースの文分割への置換 + 終止符直後の閉じ括弧を消費するロジック) (#363, #347, #348)
- Wyoming HA 統合エラー + Docker g2p import + リリース配布を解決 (#362)
- Go Dockerfile を `TARGETARCH` で arm64 対応 (multi-arch ビルド) (#366)
- WavLM Discriminator: safetensors 未公開モデルに合わせて `use_safetensors=False` に変更 (#353)
- Dependabot セキュリティアラート対応 (低リスク 7 件 + 高リスク 4 件) (#352, #364)
- テスト品質監査 — 全 18 件の再実装テスト修正 + 本番コード改善 (#338)
- C++ テスト全実行化 + 表面化した 11 テスト不具合修正 (#340)
- CI `changes` ジョブに checkout ステップを追加 (#339)
- crates.io 公開順序を修正 (#327)
- Pages デプロイを `dev` ブランチに限定 (#328)

### Documentation

- README の「30秒で試す」を OS 別ワンライナー化 + CLI バイナリ選択ガイド追加 (#360)
- 監査結果に基づくドキュメント全面同期 (v1.11.0 以降の差分を一括反映) (#368)
- エコシステム調査に基づく認知度・コントリビューション改善 (#329)
- npm 公開に伴うバージョン表記更新 (#330)

### Chore

- GitHub Actions runner を `ubuntu-24.04` に、Docker base を Debian trixie に更新 (#373)
- .NET 全プロジェクトを `net10.0` LTS に直接移行 (#374)
- EOL ランタイム (Node 18, Python 3.8) を更新 (#370)
- Node.js バージョンを 24 LTS に統一 (#345)
- MB-iSTFT 公開用 ckpt 変換スクリプトを復活 + `.gitignore` 補完 (#369)
- black を 26.3.1 へ更新 (Dependabot #145, #146) (#365)
- Claude Code hooks + skills で開発ワークフロー自動化 (#350)

### Tests

- 196 → 212 passed (リグレッション 0 件)

## [1.11.0] - 2026-04-06

### Added

- OpenAI 互換 TTS API エンドポイント追加 — `/v1/audio/speech` で既存の OpenAI クライアントから利用可能 (#321)
- C API 共有ライブラリ — opaque handle + ストリーミング + 配布パッケージ + FFI サンプル (#309)
- Go 推論バインディング — 6言語 G2P・ONNX 推論・CLI・サーバー (#260, #270)
- piper-g2p 独立 G2P パッケージ (Python + Rust + JS/WASM) (#300)
- 韓国語 G2P 対応 — C#・Go・npm/WASM 実装 + ドキュメント更新 (#299)
- スウェーデン語 G2P 対応 — 全プラットフォーム実装 (#297)
- WASM G2P — ES/FR/PT/ZH 実装 + テスト 841 件 (#316)
- WebUI: entrypoint 自動モデル DL — `PIPER_MODEL` 環境変数で起動時取得 (#313)
- README 多言語化 — 7言語追加 (KO/ES/PT/DE/RU/SV/HI) (#310)

### Changed

- CPU 推論 Tier 2 Quick Wins — warmup/cache/JA phonemize 全実装統一 (#318)
- dynamic_block_base + メモリアリーナ/パターン — 全実装統一 (#317)
- ONNX Runtime SessionOptions 最適化 — 全実装間で設定統一 (#315)
- コールドスタート最適化 — 初回発話レイテンシ ~2s → ~300ms (Rust/C#/WASM) (#302)
- WASM/npm パッケージ最適化 — 辞書外部化・feature gate・CI 改善 (#301)

### Fixed

- WebUI: NLTK tagger データ追加 — 英語推論の LookupError 解消 (#314)
- セキュリティ脆弱性対応 — Dependabot アラート 17 件解消 (#311)
- npm: config.json フォールバック追加 — HuggingFace 404 解消 (#304)
- Dependabot セキュリティアラート対応 — Python/Rust 依存更新 (#298)

### Documentation

- npm インストール手順追加 + NVDA リンク更新 (#293)
- npm バージョン参照を 0.1.1 に更新 (#292)
- 完了済みチケット削除 + ドキュメント誤記修正 (#312)
- 完了済み WASM G2P チケット・計画文書を削除 (#319)

### Chore

- 不要ドキュメント・壊れたデモ・WIP ワークフロー削除 (#303)

## [1.10.0] - 2026-03-28

### Changed

- PyPI パッケージ名を `piper-tts-plus` から `piper-plus` に変更 — 全レジストリ (npm, crates.io, NuGet) で名前統一 (#289)
  - `pip install piper-plus` でインストール可能に
  - 旧パッケージ `piper-tts-plus` はスタブリリースで `piper-plus` へリダイレクト予定

### Fixed

- npm: DictManager の辞書ダウンロードを GitHub Releases (r9y9/open_jtalk) に統一 — Rust/C#/C++ と同一ソース (#288)
  - 旧: HuggingFace 個別ファイル (404 エラー) → 新: tar.gz 一括 DL + SHA-256 検証 + DecompressionStream 展開
  - voice ファイル (mei_normal.htsvoice) を HuggingFace `piper-plus-base` にアップロード
  - PiperPlus._init() が DictManager.loadDictionary() + IndexedDB キャッシュを使用するように修正
  - SimpleUnifiedPhonemizer にプリロード済みデータ受け取り対応 (dictData/voiceData)
  - npm パッケージ v0.1.1 としてリリース

## [1.9.0] - 2026-03-28

### Added

- npm パッケージ `piper-plus` v0.1.0 — ブラウザ内で完全オフラインの多言語 TTS (JA/EN/ZH/ES/FR/PT) を提供 (#285)
  - OpenJTalk WASM (JA)、SimpleEnglishPhonemizer (EN)、キャラクタベース (ZH/ES/FR/PT)
  - `onnxruntime-web` による ONNX 推論、eSpeak-ng 不使用 (GPL リスク回避)
  - `PiperPlus`, `ModelManager`, `DictManager`, `AudioResult` 高レベル API
  - HuggingFace モデル自動 DL + IndexedDB キャッシュ
  - 282 テスト、CI (`npm-publish.yml`)
- PyPI パッケージ (`piper-tts-plus`) にプロジェクト説明 (README.md) を追加 (#286)

## [1.8.2] - 2026-03-24

### Added

- `export_onnx` で `emb_lang` 自動統一 (`--unify-emb-lang` / `--no-unify-emb-lang`) — シングルスピーカー多言語モデルで自動有効化 (#266, #279)
- `export_onnx` に `--unify-emb-lang-source N` オプション追加 (ソース言語インデックス指定)
- `docs/design/issue-266-auto-unify-emb-lang.md` 設計ドキュメント追加
- `emb_lang` 自動統一のユニットテスト7件 + ONNX統合テスト2件 (`test_export_onnx.py`)
- テスト用マルチリンガルモデルフィクスチャ追加 (`conftest.py`)

### Fixed

- `preprocess.py` の Windows 互換性修正 — `_HAS_SIGALRM` ガードで `signal.SIGALRM` 未対応プラットフォームでのクラッシュを回避 (#282)
- `preprocess.py` で `--timeout-seconds` が SIGALRM 未対応時にサイレント no-op になる問題に警告ログ追加

### Changed

- CLAUDE.md, training-guide.md を Issue #266 の自動 emb_lang 統一に合わせて更新
- `export_onnx` のドキュメントに `--simplify`, `--debug` オプションを追加
- `.gitignore` に `datasets/`, `models/`, `__pycache__/` 追加
- `pyproject.toml` に `VERSION` ファイルの package-data 設定追加

## [1.8.1] - 2026-03-22

### Fixed

- PyPI パッケージ (`piper-tts-plus`) の日本語音素化が空結果を返す致命的バグを修正
  - HTS ラベルパーシングを学習側と同じ正規表現ベースに書き換え (Kurihara method)
- `piper.__version__` が wheel インストール時に `"unknown"` を返す問題を修正
- wheel に `tests/` パッケージが含まれていた問題を修正

### Added

- EN/ZH/ES/FR/PT の phonemizer を runtime パッケージに追加 (6言語マルチリンガル対応)
- `MultilingualPhonemizer` (Unicode ベース言語自動検出 + ルーティング) を追加
- N バリアント規則・疑問詞マーカーを runtime 側に追加 (学習側と一致)
- 6言語統合テスト (`test_multilingual_integration.py`)
- CI: `python-tests.yml` に runtime テストステップ追加 (3 OS)
- CI: `dev-build-all.yml` に wheel ビルド後の6言語スモークテスト追加

### Changed

- `token_mapper.py` を全87エントリの多言語 PUA マッピングに更新
- `voice.py` を `piper_train` 不要のローカル `MultilingualPhonemizer` に切り替え
- `pyopenjtalk-plus>=0.4`, `g2p-en>=2.1.0`, `pypinyin>=0.50` を依存関係に追加

## [1.8.0] - 2026-03-22

### Added

#### C# (.NET) CLI

- モデル名/エイリアス自動解決 + 未ダウンロード時自動ダウンロード (`--model tsukuyomi`)
- `[[ phoneme ]]` インライン音素記法サポート
- カスタム辞書の大小文字分離・単語境界マッチング (C++パリティ)
- デフォルト辞書自動読み込み (`data/dictionaries/`)
- DotNetG2P + DotNetG2P.MeCab による日本語G2P
- DotNetG2P.English による英語G2P
- 中国語PUAマッピング + トーンマーカー修正
- `lid` (言語ID) テンソル対応
- OpenJTalk辞書自動ダウンロード (`DictionaryManager`)
- ストリーミング文分割 (`TextSplitter`)
- カスタム辞書 JSON v1/v2 形式対応
- NuGet パッケージ公開準備 (PiperPlus.Core, PiperPlus.Cli v0.1.0)

#### Rust CLI

- モデル名/エイリアス自動解決 + 自動ダウンロード (`find_model`, `resolve_model_path`)
- `--download-model` / `--model-dir` オプション追加
- `--quiet`, `--test-mode`, `--output-raw` オプション追加
- `--sentence-silence`, `--phoneme-silence` オプション追加
- `--list-models` 言語フィルタ (`--list-models ja`)
- カスタム辞書CLI統合 (テキスト/バッチ/ストリーミング全パス)
- 環境変数サポート (PIPER_DEFAULT_MODEL, PIPER_DEFAULT_CONFIG, PIPER_MODEL_DIR)
- naist-jdic をデフォルトfeatureに変更 (辞書バンドル)
- PyO3 0.22→0.23 アップグレード
- crates.io パッケージ公開準備 (piper-plus, piper-plus-cli v0.1.0)

#### CI/CD

- Rust CLIバイナリビルド (PR時3OS、リリース時5ターゲット)
- NuGet/crates.io 自動publishジョブ
- GitHub Actions を Node.js 24 対応バージョンに全面更新
- CI concurrencyグループ追加
- ARM64 QEMU DNS修正

#### 全言語共通

- `--output-file` 省略時に `output.wav` デフォルト出力
- Python モデルカタログ・ダウンロード機能追加

### Fixed

- C# ONNX推論の `lid` テンソル未送信バグ修正
- C# 中国語音素マッピング修正 (「你好」3 IDs → 15 IDs、「你好，今天天气很好。」3 IDs → 51 IDs)
- Rust 多言語推論で各言語に正しいPhonemizerを使用するよう修正
- Rust JA辞書未発見時のPassthroughPhonemizerフォールバック追加
- C# CLI統合テストの global.json rollForward修正
- C# テストのstderrレースコンディション修正
- リリースアーティファクト名衝突解消 (C#/Rust)

### Changed

- Rustクレート名: piper-core→piper-plus, piper-cli→piper-plus-cli
- C#/Rust バージョンはPyPIと独立管理 (v0.1.0)

## [1.7.0] - 2026-03-18

### 🚀 Major Features

#### Added

- **GPL-free 6言語マルチリンガルTTS** — 日本語・英語・中国語・スペイン語・フランス語・ポルトガル語の学習パイプライン + C++ G2P。espeak-ng (GPL) 不要で6言語推論が可能 (#218)
- **WebブラウザTTS高速化基盤** — ベンチマーク・キャッシュ・WebGPU・ストリーミング対応。全97テストパス (#246)
- **C++ CLI UX大幅改善** — `--text`による直接テキスト入力、`--list-models`/`--download-model`によるモデル管理、`--version`表示 (#244)
- **C++/Python音素化パイプライン同期** — プロソディマーク挿入・文脈依存Nバリアント・疑問詞マーカー・BOS/EOS制御をC++に実装。OpenJTalkフロントエンドをpyopenjtalk-plus Cライブラリに統一。fullcontext完全一致を達成 (#229)
- **Docker テスト強化・推論テスト統合** — 8テキスト比較テスト(8/8 PASS)、python-inferenceとwebui統合、CI回帰テスト (#230)
- **ONNXエクスポートFP16デフォルト化** — `export_onnx`でFP16変換をデフォルト適用し、モデルサイズを約50%削減。`--no-fp16`フラグで無効化可能。LayerNormalization/Sigmoid/SoftmaxはFP32を維持し数値安定性を確保 (#239)

#### Changed

- **全ONNXモデルをFP16に統一 + モデル参照を6lang版に更新** — テストモデル・HuggingFace Spacesモデルを6lang FP16版に統一し、モデルカタログ(piper_plus_voices.json)を6lang版に更新。モデルサイズ約50%削減（77MB→39MB） (#256)
- CMake ExternalProjectをpyopenjtalk-plus PyPI sdistベースに統一（全プラットフォーム共通）
- OpenJTalkをスタンドアロンバイナリから静的ライブラリリンクに変更
- `openjtalk_dictionary_manager.c`にバイナリ相対パスでの辞書検索を追加
- ブランディング統一: "Piper TTS" → "piper-plus" (#232)

### 🎯 Performance

- **ORT SessionOptions最適化** — ONNX Runtimeのセッションオプション調整で10-15%速度向上 (#250)
- **WebUI ONNXセッションキャッシュ** — セッション再利用により83%高速化 (#242)

### 🔧 Improvements

#### Fixed

- **C++マルチリンガルphonemizerの全6言語動作修正** — JA以外の5言語(EN/ZH/ES/FR/PT)が動作しない問題を修正。辞書ファイル(CMU/pypinyin)をビルド成果物に同梱し、辞書検索パスを3段階探索(モデルDir→exe相対→環境変数)に拡充。`--language`指定でラテン文字言語の検出精度向上、辞書未ロード時のgraceful degradation対応 (#254)
- **config.jsonフォールバック検索の統一** — 全コンポーネントで一貫したconfig検索ロジック (#243)
- **Windows学習互換性** — Windows環境での学習パイプライン修正 + prosodyモデル置換 (#232)
- **Dockerビルドトリガー修正** — トリガーブランチをdevに修正 (#228)
- **HuggingFace Spacesデプロイ修正** — Python API呼び出しに変更 (#224)
- ExternalProject並列ダウンロードのレースコンディション修正
- `phoneme_ids.cpp`の`interspersePad=false`パスで未知phonemeによるクラッシュを防止
- CIテストをM1.5のアーキテクチャ変更(静的リンク)に適合

### 📚 Documentation

- **CLAUDE.md大幅リファクタリング** — 6言語対応完了に伴い約60%削減 (#252)
- **ユーザビリティ改善ドキュメント** — クイックスタート再構成・Windows対応ガイド追加 (#241)
- **ドキュメント全面整理・README刷新** (#225)
- READMEにバッジ追加 & 事前学習済みモデルセクション追加 (#217)

### 🧹 Maintenance

- ルートPythonスクリプト整理 (#231)
- Docker環境全面整理・CPU化 (#221)
- 未使用workflow整理 & Python最低バージョン3.11化 (#227)
- Gradio 6.9.0更新 (#226)

## [1.6.0] - 2026-02-11

### 🚀 Major Features

#### Added

- **FP16 Mixed Precisionデフォルト化** + マルチスピーカーモデル修正 (#195)
  - 学習速度2-3倍向上、GPUメモリ約50%削減
  - デフォルトで有効 (`--precision 16-mixed`)
- **OpenJTalk A1/A2/A3 prosody values** の抽出・活用 (#196)
  - Duration Predictorへの韻律情報注入
  - `--prosody-dim 16` でデフォルト有効
- **WavLM Discriminator** (#198, #212)
  - WavLMベースの知覚品質判別器
  - デフォルトで有効（学習時のみ使用、推論に影響なし）
  - FP16 Mixed Precision対応済み
- **GPL-free 英語G2P** - g2p-en (Apache-2.0) ベース (#213)
  - espeak-ng/piper-phonemize (GPL) なしで英語推論が可能
  - ストレスマーカー、機能語処理、文脈依存変換対応
- **Phonemizer ABC + 言語レジストリ** (#215)
  - 抽象基底クラスによるif/elif分岐の解消
  - 新言語追加が容易なプラグイン構造
- **疑問詞マーカー拡張 + 文脈依存「ん」バリアント** (#204, #207, #210)
  - 強調疑問 (`?!`)、平叙疑問 (`?.`)、確認疑問 (`?~`) の区別
  - 後続音に応じた「ん」の発音バリアント (N_m, N_n, N_ng, N_uvular)

#### Changed

- **デフォルト辞書の拡充** — 誤読防止エントリ追加 (#208)

### 🔧 Improvements

#### Fixed

- **ONNXエクスポートで常にdurationsを出力** (#209, #211)
- **英語G2P espeak-ng互換性の改善** (#214)

## [1.5.5] - 2025-09-25

### 🔧 Improvements

#### Fixed

- **Windows環境での日本語TTS文字化け問題** を修正 (#185)
- **Windows PowerShellビルドエラー** 修正 + ワークフローリファクタリング (#182)
- **ARMv7ビルド失敗の修正** + デバッグ機能追加 (#184)

### 📦 Build System

#### Added

- **piper-phonemize-bundled パッケージ** — クロスプラットフォームwheel対応 (#189)
- **ARMビルド用Dockerfile** の追加 (#183)

#### Changed

- PyPIリリースバージョン形式制限の削除 (#190)
- 動的VERSIONファイル更新対応 (dev/pre-release builds) (#191)
- リリースワークフローのバージョン検証順序修正 (#192)

## [1.5.2] - 2025-09-18

### 🚀 Major Features

#### Added

- **Windows版日本語音声合成の完全サポート** (#180)
  - OpenJTalkバイナリをWindows版リリースに含める
  - naist-jdic辞書（40MB）を全プラットフォームに自動同梱
  - Windows環境での日本語TTSが追加設定なしで動作

### 🔧 Improvements

#### Fixed

- **Windows環境でのパス処理の改善**
  - スペースを含むパスでの実行問題を解決
  - 8.3形式短縮パス名の自動使用
  - 一時ファイル処理の最適化

### 📦 Build System

#### Changed

- **CI/CDワークフローの強化**
  - 全プラットフォームでOpenJTalk辞書を自動ダウンロード
  - ビルドアーティファクトに日本語TTS機能を含める
  - Windows/Linux/macOSで統一された日本語音声合成機能

## [1.5.1] - 2025-09-17

### 🔧 Improvements

#### Fixed

- **piper_phonemize UTF-8エンコーディング対応** (#178)
  - テキスト処理でのエンコーディング問題を解決
  - 多言語テキストの安定した処理を実現

- **Windows 11 espeak-ng-dataディレクトリ検出問題** (#177)
  - Windows 11環境でのディレクトリ検出ロジックを改善
  - 自動ダウンロード機能との互換性向上

### 📚 Documentation

#### Added

- **日本語TTS品質向上の技術レポート** (#176)
  - 品質問題の詳細な分析
  - 改善提案と実装ロードマップ

#### Changed

- **ブランディング更新** (#175)
  - プロジェクトロゴの刷新
  - 視覚的アイデンティティの強化

### 🧪 Developer Experience

#### Added

- **PyPiパッケージ改善** (#172)
  - 音素マップモジュールをパッケージに含める
  - インストール後すぐに使える完全な機能セット


## Older Releases

Releases v1.5.0 and prior are archived in [CHANGELOG-archive.md](CHANGELOG-archive.md) for readability.
