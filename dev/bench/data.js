window.BENCHMARK_DATA = {
  "lastUpdate": 1779070688264,
  "repoUrl": "https://github.com/ayutaz/piper-plus",
  "entries": {
    "Python inference benchmark": [
      {
        "commit": {
          "author": {
            "email": "41669061+ayutaz@users.noreply.github.com",
            "name": "yousan",
            "username": "ayutaz"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7f0da7eaaca78529318d8d1626d1f1b04bdd203f",
          "message": "fix(ci): dev push 限定の RTF Regression / Docker Build 失敗を修正 + PR 検知拡張 (#463)\n\n* fix(ci): dev push 限定で連続失敗していた 2 workflow を修正\n\n- RTF Regression: benchmark-action@v1.20.4 は内部で\n  `git fetch ... gh-pages:gh-pages` を呼ぶため repo に gh-pages branch が\n  無いと `fatal: couldn't find remote ref gh-pages` で失敗していた\n  (header コメントの auto-push 期待と実挙動が異なる)。 Store step の前に\n  idempotent な gh-pages 初期化 step を追加し、 初回 dev push で空 orphan\n  commit を push して以降の baseline 比較を有効化する。\n- Docker Build (build-cpp-dev): `wget -q` で onnxruntime release-asset を\n  ダウンロードしていたため、 transient な GitHub redirect 失敗で silently\n  exit 1 → ビルド全体が落ちていた (dev push で 9+ 回連続失敗)。 curl\n  --retry 5 --retry-all-errors に置換し、 retry / progress を可視化。\n- pre-commit hadolint hook を CI と揃え (`--failure-threshold=error`):\n  既存 warning (DL3015/DL4001 等、 .hadolint.yaml で error 化していない)\n  でローカル commit が silently 落ちる drift を解消。\n\n* fix(ci): dev push 限定の失敗を PR 段階で検知できるよう trigger 拡張\n\nこれまで Docker Build / RTF Regression の dev push 限定失敗は PR で\n検知できず、 dev へマージしてから事故るループだった (PR #463 自体は\nfix だけ。 これは原因系の再発防止)。\n\nDocker Build (docker-build.yml):\n- trigger に `pull_request: branches: [dev]` を追加 (paths は push と\n  同じ)。 PR で全 7 Dockerfile を build-only で回し、 wget silent fail /\n  apt package 不在等の Dockerfile 起因問題を PR で fail-fast。\n- `docker/build-push-action.with.push` を `true` から\n  `${{ github.event_name != 'pull_request' }}` へ条件化 (全 10 step)。\n  PR では push しない、 push event でのみ ghcr.io / Docker Hub へ push。\n- `docker/login-action` (ghcr.io login) も `if: github.event_name !=\n  'pull_request'` で gate (全 7 step)。 fork PR で write token 不在の\n  ため落ちるのも回避。\n- Docker Hub login と cosign installer / sign は既に tag ref で\n  gate 済みのため触らない (PR では既に skip)。\n- concurrency group を追加: PR は cancel-in-progress=true で古い build を\n  cancel、 push to dev は cancel-in-progress=false (image push 途中で\n  止めるとレジストリが不整合になり得るため)。\n\nRTF Regression (rtf-regression.yml):\n- `Ensure gh-pages branch exists` step を PR でも実行する形に拡張。\n  PR: read-only check で不在なら `::error::` で fail し、 push to dev\n  が落ちる前に PR 段階で surface する。 push to dev: 不在なら従来通り\n  空 orphan commit で作成。 fork PR は job-level if で既に skip。\n\n* fix(docker/cpp-dev): ONNX Runtime v1.20.0 layout 変更で cp が directory を落とす真因を修正\n\nPR #463 で trigger を PR に拡張したことで、 dev 連続 9 回失敗の真因が\nようやく surface した。 `wget -q` が silent fail していたわけではなく、\nONNX Runtime v1.20.0 が `lib/cmake/` と `lib/pkgconfig/` を lib/ 配下に\nsubdirectory として同梱しており、 `cp onnxruntime-.../lib/* /usr/local/lib/`\nが `cp: -r not specified; omitting directory` で exit 1 になっていた。\n\n`wget -q` は download 自体は成功させていて、 後段の cp が失敗 → bash\n`set -o pipefail` + && chain で全体が exit 1 → 元コミットでは\n\"wget exit 1\" のように見えていた。 curl にしたことで cp の stderr が\nbuild log に visible になり、 PR 段階で真因特定できた。\n\n修正: `cp` → `cp -r` (include 側と対称)。\n\n* fix(ci): Copilot review #463 対応 (worktree 経由 orphan / curl コメント精緻化)\n\n- rtf-regression.yml: gh-pages 初期化を `git switch --orphan` から\n  `git worktree add --orphan -b gh-pages` に変更。 dev checkout の\n  working tree を一切触らず一時 worktree でだけ orphan commit を作って\n  push する。 `git switch --orphan` も Git 2.27+ では working tree を\n  clear するが、 version dependent な挙動より明示的な isolation の\n  ほうが読み手にも自明。 checkout-back conflict も発生しない。\n- docker/cpp-dev/Dockerfile: コメントの「retry / progress を可視化」\n  が誤り (`-fsSL` の `-s` は progress bar 抑制) だったので修正。\n  実際の curl 置換の目的は (1) 真因が cp side だったため後段エラーが\n  build log で visible になること、 (2) `--retry-all-errors` で\n  transient redirect/network 失敗を retry すること、 (3) `-fS` の組合せ\n  で curl 自身のエラーは silent でなく stderr に出すこと。 `-s` は\n  build log が膨大化しないよう意図的に維持。\n\n* fix(ci/rtf): PR で gh-pages 不在を warning にする (chicken-and-egg 回避)\n\nPR #463 の trigger 拡張で意図通り PR で gh-pages 不在を検知できるよう\nになったが、 「初回 dev push 前は gh-pages が必ず不在」という\nchicken-and-egg があり、 fail にすると PR を merge できない。\n\n→ `::error::` を `::warning::` に変更し、 step 自体は success させる。\n通常運用 (gh-pages 作成後) では silent pass、 万一 gh-pages が削除\nされた場合は warning で flag するが merge は可能 (直後の dev push で\n自動再生成される)。\n\ngh-pages の直 push を avoid: 副作用が大きい (public な GitHub Pages\nsurface を作ってしまう) ため CI workflow 側で対応する保守的アプローチ。",
          "timestamp": "2026-05-13T22:33:39+09:00",
          "tree_id": "3e5605ffba7616f7a699db8cfb09580816060466",
          "url": "https://github.com/ayutaz/piper-plus/commit/7f0da7eaaca78529318d8d1626d1f1b04bdd203f"
        },
        "date": 1778679323166,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "RTF (en)",
            "value": 0.1012,
            "unit": "ratio"
          },
          {
            "name": "Latency P50 (en)",
            "value": 25.9,
            "unit": "ms"
          },
          {
            "name": "Latency P95 (en)",
            "value": 26,
            "unit": "ms"
          },
          {
            "name": "Cold Start (en)",
            "value": 1387.8,
            "unit": "ms"
          },
          {
            "name": "Peak Memory (en)",
            "value": 209.7,
            "unit": "MB"
          },
          {
            "name": "Model Size (en)",
            "value": 37.6,
            "unit": "MB"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "41669061+ayutaz@users.noreply.github.com",
            "name": "yousan",
            "username": "ayutaz"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ea994a2cff37bc9ae99c2994f31409053b71bd3e",
          "message": "docs: 15エージェント監査に基づくv1.12.0以降のドキュメント全面同期 (#493)\n\n* docs: 15エージェント監査に基づくv1.12.0以降のドキュメント全面同期\n\nv1.12.0 リリースと、その後の主要 PR (SSML C++/WASM #477/#479、Voice\nCloning WASM #478、bearer auth #475、multi-runtime RTF benchmark #484\n等) が反映されていなかったドキュメント群を一括で整合。日本語 README\nを canonical として 10 言語 README にも v1.12.0 breaking notice を翻訳\n配置 (RTF benchmark / Portuguese dialect 等の独自 banner は除去)。\nCLAUDE.md は ZH-EN loanword 「7→10 mirror」、SSML 「4→6 ランタイム」\n更新と test path / sub-stft フラグ表記を実装に整合。Python 学習側\ndocstring の \"HiFi-GAN\" 残骸 (vits/ema.py 3 箇所) と prosody_dim\ndefault 0/16 不整合も解消。pre-commit の codespell hook が\n`.codespellrc` の `skip` を無視する drift と、editorconfig-checker が\nmarkdown / Python に厳格 4-multiple indent を要求して ruff format と\n衝突する drift を `.pre-commit-config.yaml` / `.editorconfig` で吸収。\n\n* docs: 15エージェント監査に基づく整理 (CHANGELOG archive 分離 / CLAUDE.md 圧縮 / docs INDEX 整備)\n\n## 整理内容\n\n### 整理 (archive / 削除)\n- docs/csharp-cli-exit-code-rootcause.md → docs/archive/ (PR #401 解決済 root cause memo)\n- docs/guides/fix-multi-codepoint-config.md → docs/archive/ (v1.12.0 修正済 fix note)\n- docs/drafts/ 空ディレクトリ削除\n\n### docs/ 目次整備\n- docs/README.md broken link 4 箇所修正 (絶対パス /CONTRIBUTING.md 等 → ../CONTRIBUTING.md)\n- docs/README.md 目次拡充 (guides 全 15 ファイル、migration、archive、spec INDEX 掲載)\n- docs/spec/README.md 新規 (31 spec ファイルの分類 INDEX、CI gate との対応も明示)\n\n### CHANGELOG 整理\n- CHANGELOG.md v1.5.0 以前 (v1.5.0/v1.4.0/v1.3.0/v1.2.0、204 行) を CHANGELOG-archive.md に分離\n- CHANGELOG.md は v1.5.1 以降を維持、末尾に archive へのリンク追加\n\n### CLAUDE.md 圧縮\n- L5-7 v1.12.0 Breaking changes banner (3 行) → migration link 1 行に圧縮\n- L107-114 A vs B パラメータ差分テーブル (10 行) → 散文 2 行に圧縮\n- L328-363 アーカイブ: バイリンガル版の履歴 (36 行) → 1 行サマリに圧縮 (詳細は git 履歴 / CHANGELOG-archive 参照)\n\n## 結果\n\n| ファイル | Before | After | 効果 |\n|---------|--------|-------|------|\n| CLAUDE.md | 363 行 | 319 行 | -44 行 (12% 削減) |\n| CHANGELOG.md | 951 行 | 751 行 | -200 行 (21% 削減) |\n| CHANGELOG-archive.md | - | 210 行 | 新規 (履歴を分離) |\n| docs/README.md | 62 行 | 110 行 | 目次拡充 (15 guides + spec INDEX + archive) |\n| docs/spec/README.md | - | 76 行 | 新規 INDEX (31 spec の分類) |\n\nactive doc は -244 行で読みやすさ向上、archive は別ファイルに分離。\n\n## Notes\n\n15 エージェント並列監査の調査結果 (大規模整理候補 = docs/guides/ サブ dir 化 / spec/ .toml 専用化 / 多言語 README locales 化 / 大型 spec 分割) は別 PR に分離 (merge conflict リスク / レビュー負荷を考慮)。\n\n* docs: 削除候補ファイル除去 + guides/spec のサブディレクトリ化 (大規模整理)\n\n15エージェント監査で「別 PR に分離」としていた整理候補のうち以下を実施:\n\n## 削除 (アーカイブ移動から削除に格上げ)\n- docs/archive/csharp-cli-exit-code-rootcause.md (PR #401 解決済 root cause memo)\n- docs/archive/fix-multi-codepoint-config.md (v1.12.0 修正済 fix note)\n- docs/archive/ ディレクトリ (空)\n- README_HI.md / README_RU.md / README_SV.md (canonical 乖離度「高」、追従困難)\n\n## docs/guides サブディレクトリ化\n12 ファイルを 3 カテゴリに再編成:\n- integration/ (4 files): home-assistant, open-webui-integration, llm-ecosystem, wasm-bundler-guide\n- platform/ (4 files): ios-integration, swift-g2p-integration, android-g2p-{dictionary,integration}\n- development/ (4 files): building-from-source, cli-usage, pretrained-models, adding-pua-codepoint\n\n## docs/spec から .md 設計書を docs/reference/ に分離\nspec/ は .toml 専用 (CI gate 対応の機械可読契約)、reference/ は .md 設計書:\n- docs/spec/{ios-shared-lib,kotlin-g2p-{design,requirements},model-resolution,mutation-testing,ort-versions,pua-test-matrix,speaker-encoder-contract,swift-g2p,zh-en-loanword-runtime-rollout}.md → docs/reference/\n\n新規:\n- docs/reference/README.md (Design Documents / Quality & Testing 目次)\n\n修正:\n- docs/spec/README.md を .toml 専用に再構成 (16 contract + 5 versions/manifests)\n- docs/README.md の Specification セクションを Spec + Reference 2 段構成に\n\n## link 更新\n- README.md / README_EN.md / その他 README 5 言語の language switch から HI/RU/SV 削除\n- .github/workflows/codespell.yml の HI/RU/SV exclude 削除\n- 全 README / CHANGELOG / .github/workflows / .claude/skills / examples / docs/spec / docs/guides 内の `guides/X.md` 参照を `guides/(integration|platform|development)/X.md` に\n- 全 references の `spec/<10 .md files>` を `reference/<same>` に\n- 移動した 12 guide files 内部の relative path (../, ../../) を 1 階層深くなった分修正\n\n## editorconfig\n\n- `.editorconfig` に `.github/workflows/swift-g2p-ci.yml` 用の `indent_size = unset` 追加 (shell case branch continuation alignment、既存 android-build.yml と同じ理由)\n\n## 結果\n\n| 項目 | 件数 |\n|------|-----|\n| 削除ファイル | 5 (3 README + 2 archive) |\n| 移動 (renamed) | 22 (12 guides + 10 spec/.md) |\n| 新規 | 1 (docs/reference/README.md) |\n| link 更新 | 44+ 件 (workflow / SKILL / examples / README 等) |\n\nzh-en-loanword-runtime-rollout.md (1749 行) の 6 ランタイム別分割は別 commit で対応中。\n\n* docs(reference): zh-en-loanword 設計を 6 ランタイム別に分割 (1749行 → 7ファイル)\n\n- 削除: docs/reference/zh-en-loanword-runtime-rollout.md (1749 行)\n- 新規: docs/reference/zh-en-loanword/ ディレクトリ\n  - README.md (761行) — index + 共通設計 + 12 横断的課題\n  - python.md (292行) — canonical 実装、JSON 同期、後方互換、データセット運用\n  - cpp.md (329行) — iOS/Android リソース、xxd 代替、thread safety\n  - rust.md (133行) — 2 crate 並列、Arc<LoanwordData>\n  - wasm.md (181行) — 二層 FFI、WASM サイズ最適化\n  - go.md (150行) — //go:embed、sync.Once\n  - csharp.md (124行) — DotNetG2P.Chinese 制約、独立実装\n\n横断参照 9 箇所を新パスに更新 (SKILL.md / workflows / kotlin-g2p-*.md /\ndictionary-versions.toml / README.md / scripts / tests)。\n\n* docs: PR #493 Copilot レビュー 11 件への対応\n\n事実誤認・実装乖離の修正:\n- src/wasm/openjtalk-web/README.npm.md: synthesizeFromReferenceAudio コード例を\n  実装 (instance method, params: text/referenceWav/encoder/sampleRate/options) に一致\n- src/go/README.md: Go ランタイムに未実装の bearer-auth 行を削除\n- CHANGELOG.md: bearer auth target を piper.http_server → docker/python-inference/inference.py、\n  env var を PIPER_AUTH_TOKEN → PIPER_API_KEYS (実装と一致)\n- src/python/piper_train/vits/lightning.py: _load_test_dataset docstring を実装\n  (get_phonemizer(\"ja-en\") ハードコード) に一致\n\n整合性 / 配置の修正:\n- CLAUDE.md: Strategy A/B/C を \"全 7 ランタイム\" → \"全 6 ランタイム (Python/Rust/C#/Go/WASM/C++)\"\n  に統一 (README.md L113 / CHANGELOG.md L150 と一致)\n- README_DE/ES/FR/KO/PT/ZH.md: v1.12.0 banner をバッジ block の後ろに移動\n  (README.md L21 の canonical 配置と整合、バッジ分断を解消)\n\n設定の修正:\n- .editorconfig: [*.py] の redundant `indent_size = 4` を削除 (直後に unset している)\n- .pre-commit-config.yaml: codespell exclude regex を path-anchored に\n  (sample_texts.py / zh_en_loanword.json の誤 match を防止、削除済み HI/RU/SV を除去)\n\n事実関係の確認のみで実装/ファイル変更不要 (返信で対応):\n- src/go/README.md CLI flag テーブル: main.go で全 flag 確認済み (一致)\n- src/wasm/openjtalk-web/README.npm.md dispatch table: phonemizer-compat.js / js-g2p-adapter.js\n  で @piper-plus/g2p G2P 使用を確認済み\n- README accent 復元: 各多言語 README の本文も accent なしの ASCII 化が canonical 方針\n\n* docs: サブディレクトリ化後の CI gate 3 件を修正\n\n直前の commit 2bb99cf5 (guides/spec のサブディレクトリ化) で発生した\nリンク drift とパス drift を解消し、PR #493 で fail していた 3 gate を pass:\n\n1. Migration <-> CHANGELOG Parity Gate:\n   - docs/migration/v1.11-to-v1.12.md に `net10.0` (TFM) キーワード追記\n   - CHANGELOG L241 `.NET 全プロジェクトを net10.0 LTS に移行` をカバー\n\n2. lychee (link-check):\n   - docs/guides/README.md: integration/ サブディレクトリ配下への相対パスへ更新\n     (home-assistant.md / llm-ecosystem.md / open-webui-integration.md\n      / wasm-bundler-guide.md)\n   - docs/reference/{kotlin-g2p-design,kotlin-g2p-requirements,pua-test-matrix}.md:\n     pua-contract.toml の参照を ../spec/ へ\n   - docs/reference/swift-g2p.md: swift-g2p-contract.toml の参照を ../spec/ へ\n\n3. speaker-encoder contract gate:\n   - scripts/check_speaker_encoder_contract.py の CONTRACT_PATH を\n     docs/reference/speaker-encoder-contract.md に修正 (実ファイルが\n     docs/reference/ 配下、他 .md 形式 contract のパターンと整合)\n   - test/{test_speaker_encoder_e2e,generate_speaker_encoder_golden}.py と\n     src/python/tests/test_speaker_encoder_golden.py の docstring も同期\n\n* fix(docker/python-train): UV_NO_CACHE で wheel cache layer bloat を解消 (#495)\n\nbuilder stage で torch+CUDA (~3GB) + scipy/numpy/librosa を uv pip で\nインストールする際、 ~/.cache/uv に全 wheel が duplicate で保存され\n~3-5GB の余分な layer を produce、 GH Actions runner の ephemeral\ndisk を multi-stage COPY 中に枯渇させていた (scipy unpack 段階で\n\\`no space left on device\\` で fail)。\n\nUV_NO_CACHE=1 を builder stage の冒頭で設定し、 uv の wheel cache を\n完全に無効化。 rebuild 時の wheel 再 download コストは\ndocker/build-push-action の \\`cache-from: type=gha\\` (mode=min) が\n吸収するため、 cache miss 時にのみ download コストを払う。\n\n修正前 (run 25922832820): builder image ~13-17GB → ephemeral 枯渇\n修正後想定: builder image ~9-12GB に縮小、 disk pressure 緩和\n\nIssue #495",
          "timestamp": "2026-05-16T01:24:47+09:00",
          "tree_id": "272fbd9ba1989acdfb4bb31ab078ba3562c2397f",
          "url": "https://github.com/ayutaz/piper-plus/commit/ea994a2cff37bc9ae99c2994f31409053b71bd3e"
        },
        "date": 1778862365779,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "RTF (en)",
            "value": 0.095,
            "unit": "ratio"
          },
          {
            "name": "Latency P50 (en)",
            "value": 24.3,
            "unit": "ms"
          },
          {
            "name": "Latency P95 (en)",
            "value": 24.5,
            "unit": "ms"
          },
          {
            "name": "Cold Start (en)",
            "value": 1335.6,
            "unit": "ms"
          },
          {
            "name": "Peak Memory (en)",
            "value": 209.3,
            "unit": "MB"
          },
          {
            "name": "Model Size (en)",
            "value": 37.6,
            "unit": "MB"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "41669061+ayutaz@users.noreply.github.com",
            "name": "yousan",
            "username": "ayutaz"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "6fe8c9c6af2a3a6f9ba299ce3eb77a0a6e2b3156",
          "message": "fix(runtime): trim EOS region for all inputs (Issue #499 Tier 1) (#506)\n\nVitsModel.infer() expands attention with ceil(w) but exposes raw float\nw as the durations output. The EOS frame(s) generated under ceil\nexpansion carry decoder leakage that sounds like the final syllable was\nrepeated — audible on fine-tuned models such as\npiper-plus-tsukuyomi-chan (Issue #499 / HF samples ja/en/zh/fr/pt).\n\n_trim_padding_by_durations already drops the EOS region but only when\nStrategy A short-text padding was applied. This adds _trim_eos_region\nwhich applies the same drop to every inference path so long-text\noutputs are no longer left with the audible doubled tail.\n\nChanges:\n- src/python_run/piper/voice.py: add _trim_eos_region; apply in\n  _synthesize_ids_core when was_padded=False.\n- src/python/piper_train/infer_onnx.py: mirror the helper and apply\n  in main()'s inference path.\n- TestTrimEosRegion (9 cases) added to both\n  src/python_run/tests/test_short_text_mitigation.py (CI: \"Run runtime\n  full tests\") and src/python/tests/test_infer_onnx.py (cross-runtime\n  contract mirror).\n\nMeasured on tsukuyomi-chan-6lang-fp16.onnx with text\n\"こんにちは、つくよみちゃんです。\" (ls=1.0, nw=0, deterministic):\nceil(durations[-1])=2 frames (512 samples, ~23 ms) trimmed; trailing\n\"doubled syllable\" 2nd-peak amplitude drops by ~30 % (15535 → 10997).\nRemaining structural decoder leakage upstream of EOS requires Tier 2\n(durations = w_ceil at export) or model re-training to remove.",
          "timestamp": "2026-05-18T11:17:04+09:00",
          "tree_id": "331ee698ca5404d3f97d87d095b767d03d67a52a",
          "url": "https://github.com/ayutaz/piper-plus/commit/6fe8c9c6af2a3a6f9ba299ce3eb77a0a6e2b3156"
        },
        "date": 1779070686420,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "RTF (en)",
            "value": 0.1036,
            "unit": "ratio"
          },
          {
            "name": "Latency P50 (en)",
            "value": 24.8,
            "unit": "ms"
          },
          {
            "name": "Latency P95 (en)",
            "value": 36,
            "unit": "ms"
          },
          {
            "name": "Cold Start (en)",
            "value": 1353.9,
            "unit": "ms"
          },
          {
            "name": "Peak Memory (en)",
            "value": 209.3,
            "unit": "MB"
          },
          {
            "name": "Model Size (en)",
            "value": 37.6,
            "unit": "MB"
          }
        ]
      }
    ]
  }
}