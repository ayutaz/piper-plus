window.BENCHMARK_DATA = {
  "lastUpdate": 1779151417723,
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
          "id": "efe870fb589a16d0b6c11f084ffb8fa015c0c826",
          "message": "ci: tickets index + 10 CI gates (audio / ABI / supply-chain / fuzz) (#511)\n\n* docs: CI/CD 拡張プラン (Top 10) を個別実装チケット 10 本 + 5 phase overview に分解\n\n30 エージェント並列調査の Top 10 を「実装者が一人で着手できる粒度」まで分解した個別チケットを docs/tickets/ に追加。 各チケットは 9 節構成 (目的 / 詳細 / チーム配置 / Unit&E2E テスト / 懸念 / Reinvention / Handoff / 関連ファイル / 参照) で、 親調査 / 親マイルストーン doc と bidirectional に相互リンクする。\n\n* ci: cancelled / skipped baseline alarm gateway\n\nHub-and-spoke gateway that converts cancelled / skipped / failure of monitored\nspoke workflows into an explicit fail, closing the fail-open gap that allowed\nPR #419 to merge with a collapsed baseline. stdlib-only Python script + 6\nfixture scenarios + workflow with workflow_run + pull_request triggers.\n\n* docs(tickets): mark M1.1 status as in-progress (PR draft)\n\n* ci: first-PR fast lane for new contributors\n\nContract gates (PUA / loanword / ORT / migration parity / ruff version sync)\nare downgraded to `neutral` (= warning, but pass for branch protection) when\na PR comes from an author whose `author_association` is FIRST_TIME_CONTRIBUTOR\n/ FIRST_TIMER / NONE, unless a maintainer has attached `run-full-gate`. Core\nlint and the cancelled-baseline gateway stay required.\n\nThe cancelled-baseline gateway is taught to treat `neutral` as success so the\ntwo pieces compose: contributors get an onboarding lane, but a cancelled or\nskipped run still fails. Includes weekly `first_pr_health.py` snapshot for\nthe 4-week follow-up review.\n\n* ci: migration guide cross-ref lint\n\n[Unreleased] > ### Breaking entries must reference docs/migration/v*.md with\na resolvable anchor. New keep-a-changelog parser (`check_migration_xref.py`,\nstdlib only) + workflow gated by `breaking` label or CHANGELOG diff; existing\n`migration-changelog-parity` is kept (responsibility separation).\n\n* ci: audio MOS proxy informational tier (PESQ / STOI / UTMOS / WER)\n\nAdds the diff/render/Bencher-JSON layer of the audio MOS proxy gate as an\ninformational tier (continue-on-error: true). The workflow bootstraps with\nzero-filled stubs so the first PR is green; PESQ / STOI / UTMOS / Whisper\nWER calls are scaffolded but invoked only by CI (heavy deps are deferred).\n30-sample golden corpus manifest committed; reference WAVs stay on HF Hub.\n\n* ci: cross-runtime audio byte parity informational tier\n\n* ci: public ABI snapshot diff (C / Swift / Kotlin) bootstrap baseline\n\n* ci: model card / license attribution auto-generation\n\n* ci: typosquatting weekly scan (PyPI / npm / crates / NuGet / Maven)\n\nstdlib Levenshtein + homograph (ASCII / leet / Cyrillic) scan with a\nJSON-fixture mode for unit testing. The weekly workflow polls all five\nregistries inline, classifies via the script, and opens (or updates) one\nsticky GitHub issue per cycle if any suspect is found. canonical / allowlist\nfilters keep `piper-plus` itself and known false positives (`piper-phonemize`\netc.) out of the report.\n\n* ci: informational fuzz for forward-compat + timing monotonicity\n\n* ci: inject model-card / license attribution hook into HF Space & shared-lib release\n\n- deploy-huggingface.yml: Prepare Space files 直後に `generate_model_card.py validate`\n  + `generate --model multilingual-test-medium` で MODEL_CARD.md と\n  LICENSE_ATTRIBUTIONS.md を hf-space-deploy/ に同梱\n- release-shared-lib.yml: release job の sparse-checkout に\n  `scripts/generate_model_card.py` + `data-sources.yml` を追加し、\n  Generate checksums 前に validate+generate を実行。 Create GitHub Release の\n  files に MODEL_CARD.md / LICENSE_ATTRIBUTIONS.md を追加\n- HF Space は CSS10 JA 6lang model だけ載るため `used_only_in=tsukuyomi-*` の\n  dataset は filter で除外。 shared-lib release は任意モデルと使われるため\n  filter なし (全 dataset 同梱)\n- docs/tickets/M3-2-license-auto-injection.md と docs/tickets/README.md の\n  ステータスを「validate + generate + workflow hook 注入完了」に更新\n- CHANGELOG.md Post-v1.12.0 chore に 1 行追加\n\n* ci: fix Migration Guide Lint YAML scalar bug + extend lychee exclude for PR #511 tickets\n\n両 fail とも PR #511 内既存問題で 5 連続 fail していたものを本コミットで修復:\n\n- migration-guide-lint.yml line 77: plain scalar の `run: echo \"...### Breaking...\"`\n  は YAML parser が space + `#` をインラインコメントと解釈し、 引用符が\n  unclosed のまま shell へ渡されて EOF エラーで終了していた。 block scalar\n  (`|`) に変えて値全体を渡すよう修正。\n- .lychee.toml: PR #511 で追加した docs/tickets/ と\n  tests/scripts/fixtures/migration_xref/ で発生する 13 broken link を\n  分類して exclude / exclude_path に追加:\n  - `.claude/memory` 系 5 件 — ユーザー固有 path で repo に実体なし\n    (auto memory システム設計に従う logical reference)\n  - Swift SymbolGraph 旧 URL (M3-1) — swiftlang/swift repo 構造変更で 404\n  - USENIX 2020 paper URL (M3-3) — USENIX サイト path 変更で 404\n  - migration_xref fixture 5 件 — 意図的 broken link を含む negative-case\n    test data (`scripts/check_migration_xref.py` の検知対象)\n- .editorconfig: `.lychee.toml` は upstream lychee project と同じ 2-space\n  indent で書かれているため、 global `[*.{rs,toml}]` の 4-space ルールを\n  file 単位 opt-out (`docs/spec/*.toml` と同じ pattern)。\n\n* docs: 実装完了した個別 ticket .md 10 個を削除し参照を整理\n\nPR #511 で M1.1〜M4.2 の 10 ticket は全て実装完了 (`scripts/`,\n`workflows/`, `tests/scripts/` に成果物が落ちている)。 個別 ticket は\n実装ログとしての役目を終えたため削除し、 phase overview / README は\n「実装完了 (PR #511)」 マーク付きの簡素な表へ縮小。\n\ndead link になる箇所を同時修正:\n- 親 milestone doc の 10 ticket リンクを「実装ステータス: 実装完了 (PR #511)」 に置換\n- 各 workflow / script docstring / pre-commit / spec / migration README のコメント内 ticket 参照を proposals link + PR #511 補記に置換\n- `.lychee.toml` の `.claude/memory` / Swift SymbolGraph / USENIX 2020 exclude (削除した ticket .md 起因) を撤去\n\nM-Stretch-overview.md は親 milestone doc から参照されており未着手の検討候補\nとして保持。\n\n* chore: lychee/commitlint regression を修正\n\n- M1/M4-overview.md の .claude/memory 参照を plain text 化 (削除した\n  ticket 起因の lychee broken link 撤去後に顕在化)\n- .commitlintrc.json に footer-max-line-length=0 を追加 (body と同精神、\n  日本語 body 行で footer 判定された場合に 100 文字 limit を回避)\n\n* ci: OpenSSF Scorecard を週次 + dev push で実行 (proposals §3.6 Week 1)\n\n`docs/proposals/ci-expansion-2026-05.md` §3.6 Week 1 由来、 Top 10 外の\nsupply-chain hardening 追加項目。 `ossf/scorecard-action@v2.4.2` で 17\ncheck のスコアを SARIF として code scanning に upload + scorecard.dev\nへの publish を有効化 (informational、 PR を block しない)。\n\n既存 cosign / SBOM / Trivy / dependency-review / action-pin gate と\n重複しないため net flat policy 違反なし。 Scorecard は外部公開メタの\nベンチマーク的位置付け。\n\n* ci: CHANGELOG keep-a-changelog format validator (proposals §3.7 Tier S #1)\n\n`docs/proposals/ci-expansion-2026-05.md` §3.7 Tier S #1 由来、 Top 10 外の\ndocs / i18n / CHANGELOG 拡張。 M1.2 migration-guide-lint (anchor link\n強制) と相補的に「CHANGELOG.md 自体の format drift」 を validator script\n+ workflow + pre-commit hook で gate 化。\n\n検査項目 (error tier):\n- # Changelog H1 が冒頭にある\n- ## [Unreleased] が最初のリリースより前\n- バージョン header は ## [X.Y.Z[-pre]] - YYYY-MM-DD 形式\n- リリースは降順\n\n検査項目 (warning tier):\n- セクション名は keep-a-changelog 7 種 + piper-plus extended のいずれか\n- 同名セクションが同一リリース内で重複しない\n\n`## Older Releases` を terminator、 絵文字付き historic セクションを\nbootstrap baseline として allowlist 化。 既存 CHANGELOG.md は error 0、\npytest 10 ケース全 pass。\n\n* ci: README heading tree parity (proposals §3.7 Tier S #2, informational)\n\n`docs/proposals/ci-expansion-2026-05.md` §3.7 Tier S #2 由来、 Top 10 外の\ndocs / i18n / CHANGELOG 拡張。 既存 `check_readme_h2_parity.py` (H2 個数\nのみ ±20%) を補強し、 H2/H3/H4 tree structure の comparison と H2 section\n内 H3 count drift を比較する informational tier gate を追加。\n\n実装内容:\n- `scripts/check_readme_heading_tree.py`: canonical (README.md JP) vs 7\n  言語翻訳 README の H2/H3/H4 tree を抽出、 H2 count + H2 section の H3\n  count 比較 + (optional) order pattern 比較\n- `.github/workflows/readme-heading-tree-parity.yml`: PR の README*.md\n  変更時に走る informational workflow (PR を block しない)\n- pytest 9 ケース、 全 pass\n\ndefault `--h3-tolerance 5` で既存翻訳側 drift (DE/ES/FR/KO/PT/ZH の 6\n言語が共通の H3 細分化 pattern を持つ) を bootstrap baseline として吸収。\nEN は canonical と完全一致、 他 6 言語は section #2/#6/#9 で +5/+5/+3\nH3 を持つが tolerance 内。 新規 drift 拡大が起きた時に警告される。\n\n* ci: CI flake/cancel observability snapshot (proposals §3.9 #1)\n\n`docs/proposals/ci-expansion-2026-05.md` §3.9 #1 由来、 Top 10 外の CI\nobservability 拡張。 M1.1 cancelled baseline alarm が PR 単位で silent\nskip を gate するのに対し、 本 snapshot は過去 7 日の workflow run を\ntrend として集計する data layer。\n\n実装:\n- scripts/ci_observability_snapshot.py: gh run list -> workflow 単位の\n  total/success/failure/cancelled/skipped count + ratio + flake candidate\n  抽出 (cancellation_rate > 10% threshold)\n- .github/workflows/ci-observability-snapshot.yml: 月曜 UTC 08:00 schedule\n  + workflow_dispatch、 90 日 retention の JSON artifact\n- pytest 6 ケース、 全 pass\n\ndashboard UI は yagni で別 PR/後続作業に分離。 本 PR では data layer のみ。\n\n* ci: Rust miri nightly informational (proposals §3.1 #8)\n\n`docs/proposals/ci-expansion-2026-05.md` §3.1 Sanitizer 拡張 #8 由来、\nTop 10 外。 piper-plus-g2p crate の 27 箇所の unsafe (FFI 系を除く\nRust internals) に対する UB / stacked borrow / aliasing 違反を nightly\nmiri で informational 検出する。\n\n実装:\n- .github/workflows/rust-miri-nightly.yml: 毎週日曜 UTC 03:00 schedule\n  + workflow_dispatch、 timeout 60 min (miri は通常 cargo test の 10-50x\n  遅い)\n- cargo +nightly miri test --package piper-plus-g2p --lib -- --skip ffi\n- continue-on-error: true で PR を block せず、 miri-output.log を 30 日\n  artifact として保持して maintainer が trend 観測\n\n既存 ASan / UBSan / clang-tidy gate (C++ 側) と重複せず、 Rust 側の\nmemory safety を補完する。 piper-plus-g2p に内在する 27 箇所の unsafe\nは CString / *const c_char の往復で必要。\n\n* docs: tickets dir 削除 + M-Stretch 詳細実装方針を proposals に集約\n\nTop 10 + §3 軽量 5 件 (PR #511) の実装が完了し docs/tickets/ の役割が\n終了したため、 6 ファイルを削除。 M-Stretch S1-S8 の詳細は新規\ndocs/proposals/ci-expansion-deferred-items.md に集約 (Claude Code 実装\n前提で 8 項目の真の障壁を再評価、 536 行)。\n\nmilestones.md / docs/README.md の tickets リンク参照を撤去、\ndeferred-items への誘導を追加。 ダングリング link 0 件。\n\n* docs: PR #511 反映で INDEX / proposals に最新化漏れを追加\n\n- docs/spec/README.md: audio-parity-contract.toml を Core Contracts に追加\n- docs/reference/README.md: branch-protection-history.md を Operations に追加\n- CLAUDE.md 主要ファイル索引: audio-parity / branch-protection-history を追加\n- docs/proposals/ci-expansion-2026-05.md: 序文に実装完了ステータス (Top 10 + 軽量 5 件)\n  と関連ドキュメント節に milestones.md / deferred-items.md リンクを追加\n- docs/README.md proposals 節: deferred-items.md エントリ追加、 2026-05.md にも\n  実装完了 annotation 付与\n\nエージェントチーム 4 並列 (proposals / top-level / docs INDEX / guides) で\ndocs/ 全体を網羅監査した結果のうち、 「実装と doc が齟齬」 する必須項目のみ\n反映。 informational tier 公開状態未確定 (Scorecard / model-card output 経路)\nや機能仕様変更でない追加情報 (SECURITY badge / CONTRIBUTING attribution 説明)\nは保守的判断で見送り。\n\n* docs(proposals): 役割を終えた 2026-05 / milestones を削除し deferred-items に集約\n\nPR #511 で Top 10 + §3 軽量 5 件が実装完了したため、 親調査\n`ci-expansion-2026-05.md` と マイルストーン詳細 `ci-expansion-milestones.md`\nは役割を終えた。 M-Stretch 8 項目の詳細実装方針は `ci-expansion-deferred-items.md`\nに集約済みのため、 前者 2 ファイルを削除。\n\ndangling reference 対応:\n- docs/proposals/ci-expansion-deferred-items.md: 自己参照 5 箇所を inline 化、\n  関連ドキュメント section に「git log --diff-filter=D」 で履歴参照する旨を明記\n- docs/README.md: proposals 節を deferred-items.md 1 行に集約\n- docs/migration/README.md: 関連 doc から 2026-05.md 参照を削除\n\nCHANGELOG / workflow YAML 内の `docs/proposals/ci-expansion-2026-05.md` plain\ntext 参照は backtick で囲まれており lychee `include_verbatim = false` で対象外\nとなるため、 履歴記述として残置。\n\n* docs(proposals): deferred-items も PR から外す (proposals ディレクトリ全削除)\n\nPR #511 の scope を Defensive Foundations 実装 (Top 10 + §3 軽量 5 件) に\n絞るため、 deferred-items.md (M-Stretch 8 項目の Claude Code 前提再評価) も\nPR からは外す。 内容は別途検討する。\n\n- docs/proposals/ci-expansion-deferred-items.md: 削除 (538 行)\n- docs/README.md: Proposals section ごと削除\n- docs/proposals/ 自体が空になり自動消滅\n\nローカルバックアップ: /tmp/ci-expansion-deferred-items-backup-*.md\n\n* ci(parity): 4 runtime (Python/Rust/Go/C#) で audio byte parity を実装\n\nPR #511 の Runtime Parity Deep gate が self-comparison (python vs python2)\nのみで cross-runtime 検出として機能していなかった指摘への対応。\n\nPhase 1 で実装可能な 4 runtime (Python / Rust / Go / C#) の cross-parity\nを bootstrap 配置。 C++ / WASM CLI は phoneme_ids JSONL 入力経路が未実装\nのため Phase 2 (別 PR) へ deferred、 contract toml で\nsupports_dump_wav=false に降格し audio_parity.py の skip ロジックで\n報告する。\n\n主な変更:\n- src/python_run/piper/__main__.py: --json-input flag を追加し\n  phoneme_ids JSONL stdin 経路を実装 (G2P バイパス、 Rust/Go/C# と契約一致)\n- tests/fixtures/audio-corpus/parity/phoneme_ids.jsonl: ja「あいうえお」相当\n  の固定 12 ID 列 fixture (BOS + 5 phoneme + PAD intersperse + EOS)\n- .github/workflows/runtime-parity-deep.yml: dump-{python,rust,go,csharp}\n  4 matrix job + compare job 構成に刷新、 informational tier 維持\n- docs/spec/audio-parity-contract.toml: wasm / cpp を supports_dump_wav=false\n  に降格 (Phase 2 で true に戻す)\n- scripts/audio_parity.py: collect_skips() を追加し supports_dump_wav=false\n  / --inputs 未指定 runtime を skip 行として報告\n- tests/scripts/test_audio_parity.py: skip ロジック検証 5 ケース追加\n  (合計 15 ケース、 tests/scripts/ 全 140 件 pass)\n\n* feat(parity): C++ + WASM CLI に phoneme_ids JSONL 入力経路を実装 (Phase 2)\n\nPR #511 cross-runtime audio byte parity gate を 4 runtime (Phase 1) →\n6 runtime (Phase 2) に拡張するための実装。 docs/spec/audio-parity-contract.toml\nへの反映と workflow / pytest 更新は別 commit で続ける。\n\nC++ (src/cpp/main.cpp):\n- processLine の JSON 入力分岐で phoneme_ids field を抽出 (text と排他、\n  両方あれば phoneme_ids 優先)\n- 3 つの outputType 分岐 (DIRECTORY / FILE / STDOUT) に phoneme_ids 経路を\n  最優先 branch として追加し、 既存 piper::synthesize API (piper.cpp:1239)\n  を直接呼ぶ\n- text の require を「phoneme_ids 不在時のみ」 に緩める\n\nWASM (src/wasm/openjtalk-web/bin/piper-cli.js, new):\n- Node CLI bin script を新規作成 (ESM, ~280 行)。 onnxruntime-node を\n  dynamic import で使い JSONL stdin → phoneme_ids → ONNX session.run →\n  WAV write の最小経路を提供\n- 既存 src/index.js (browser API、 fetch/IndexedDB 依存) は変更しない\n- package.json に bin entry + onnxruntime-node devDependency + files に\n  bin/**/*.js を追加\n\nWASM bin の standalone unit tests (test/js/test-piper-cli-bin.js, new):\n- argv parser 4 ケース (--help / 必須欠落 / 未知 flag / 値欠落)\n- JSONL / config preflight 2 ケース (空 stdin / 不在 config)\n- WAV byte layout 3 ケース (44-byte RIFF header / 4 sample rate / 0-sample)\n- file shape contract 2 ケース (shebang / dynamic import)\n- 合計 11 ケース、 node --test で全 pass、 ONNX 推論経路を回避し CLI 層を\n  独立検証\n\n* ci(parity): Phase 2 仕上げ — workflow 6 runtime + contract + pytest 13 ケース追加\n\nPR #511 cross-runtime audio byte parity gate を Phase 2 完了状態に移行:\ncontract toml で 6 runtime 全 supports_dump_wav=true、 workflow が\ndump-{cpp,wasm} を含む 6 matrix で稼働、 pytest が 6 runtime topology\n全パターン (full / partial / unknown / dump_wav 優先順位 / fail-on-mismatch)\nを 13 ケースで検証する。\n\nC++ helper (src/cpp/piper.{hpp,cpp}):\n- 新規 piper::phonemeIdsToWavFile(config, voice, ids, audioFile, result)\n  を declare + impl。 既存の textToWavFile と対称な公開 API で、 内部で\n  既存の static-scope synthesize() を直接呼ぶ thin wrapper\n- main.cpp の processLine 3 つの outputType 分岐をこの helper に統一\n  (writeWavFromBuffer 経由ではなく既存 writeWavHeader 経路に乗せる)\n- cmake --build build --target piper で local build pass、 既存 fixture\n  (BOS + あいうえお + EOS) を入力した smoke test で 22050 Hz / 16-bit /\n  mono / 6302 byte の WAV を出力すること確認\n\nWorkflow (.github/workflows/runtime-parity-deep.yml):\n- dump-cpp matrix job 追加: cmake build + ./build/piper 実行\n- dump-wasm matrix job 追加: npm install --no-save onnxruntime-node +\n  node src/wasm/openjtalk-web/bin/piper-cli.js 実行\n- compare job の inputs loop を python/rust/go/csharp/cpp/wasm 6 runtime に\n  拡張 — sticky comment に C(6,2)=15 pair の tier 判定を出力\n\nContract toml (docs/spec/audio-parity-contract.toml):\n- cpp / wasm を supports_dump_wav=true に戻し、 cpp.cli を実 binary 名\n  \"piper\" に修正。 Phase 2 完了 note を block コメントに反映\n\npytest (tests/scripts/test_audio_parity.py):\n- 既存 5 ケースを Phase 2 contract (全 6 enabled) に整合させて書き換え。\n  supports_dump_wav=false 検証は _write_ad_hoc_contract helper で擬似\n- 新規 8 ケース:\n  - test_load_contract_runtimes_section_has_six_runtimes (canonical)\n  - test_collect_skips_all_runtimes_enabled_full_inputs\n  - test_collect_skips_unknown_runtime_is_kept_verbatim\n  - test_collect_skips_priority_dump_wav_over_missing\n  - test_render_markdown_full_six_runtime_pair_count (15 pair pin)\n  - test_cli_compare_phase2_full_six_runtimes (rc=0, 15 pair, 0 skip)\n  - test_cli_compare_phase2_partial_three_inputs (3 pair + 3 skip)\n  - test_cli_compare_phase2_fail_on_mismatch_across_runtimes\n- tests/scripts 全 148 件 pass (audio_parity 23 件 / 累積 +13 from Phase 2)\n- src/wasm/openjtalk-web/test/js/test-piper-cli-bin.js は別 commit で\n  既に追加済 (11 ケース、 node --test pass)\n\n* test(parity): Phase 2 のエッジケース網羅 — C++ gtest 4 + integration 7 + WASM 23 + pytest 9 ケース追加\n\nPR #511 Phase 2 で追加した変更箇所 (C++ phonemeIdsToWavFile / main.cpp\nprocessLine の JSONL 経路 / WASM bin / audio_parity.py の skip ロジック /\nparity fixture) に対しエッジケースを系統的に拡張。\n\nC++ gtest (src/cpp/tests/test_streaming_raw_phonemes.cpp): 4 ケース追加\n- PhonemeIdsToWavBasicHeader: RIFF/WAVE/fmt/data magic + サンプルレート/\n  ビット深度/data chunk size の byte-level 検証\n- PhonemeIdsToWavSameLengthOnRepeat: VITS stochastic 性を踏まえ「同一入力\n  → 同一フレーム数 + 同一 WAV ヘッダー」 の弱不変条件 (cross-runtime gate\n  が tier 2/3 で吸収する設計と整合)\n- PhonemeIdsToWavShortInputProducesAudio: BOS+1+EOS の最短入力で\n  Strategy A padding 経由の非空出力\n- PhonemeIdsToWavDifferentInputsDifferentOutputs: 別 ID 列で別出力\n  (キャッシュ汚染による silent pass を防止)\n\nC++ CLI integration (tests/scripts/test_cpp_cli_phoneme_ids.py, new):\n7 ケース — file / stdout (-) / directory 3 経路 + text/phoneme_ids 排他 +\nper-line output_file 上書き + 両欠落エラー + 複数行 utterance。\nbuild/piper 不在環境では pytestmark.skipif で全件 skip。\n\nWASM bin standalone (test-piper-cli-bin.js): 11 → 34 ケース\n- argv parser: short alias (-h/-m/-c/-f) / 各 flag value missing / numeric flag\n- floatToInt16 clamp: ±1.0 / out-of-range / mid-range / empty (5 ケース)\n- JSONL edge: 空 phoneme_ids / 非配列 / 不正 JSON / blank lines tolerance\n- 不正 JSON config / fallback (sample_rate / num_speakers / num_languages)\n- bin source structural contract (BigInt64Array / scales tensor / optional\n  inputs 条件分岐 / per-line output_file / stdout sink / array validation)\n\naudio_parity.py pytest (test_audio_parity.py): 23 → 32 ケース\n- 全 inputs unsupported (0 pair + 全 skip)\n- 空 [runtimes] section の contract\n- supports_dump_wav 欠落 → default true\n- 非 dict runtime spec → garbage tolerance\n- parity fixture phoneme_ids.jsonl validation (BOS/EOS/PAD layout)\n- snapshot: 8-bit PCM / stereo (channel average) / 24-bit (sha256 のみ動作)\n\neditorconfig-checker exclude:\n- src/cpp/tests/test_streaming_raw_phonemes.cpp を exclude に追加。 既存\n  2-space indent (.editorconfig default は 4-space) が 179 件の違反を\n  発火させたため、 既存 style を維持する保守的選択肢として exclude を\n  選択 (memory feedback_conservative_changes)\n\n合計: tests/scripts/ 全体 148 → 164 件 pass、 WASM node test 11 → 34 件 pass、\nC++ gtest +4 件 pass。\n\n* fix(ci): runtime-parity-deep の dump-go / dump-rust failure を修正\n\nPR #511 Phase 1 commit (9d8c6a0d / 24fb6808) で導入した 6 matrix workflow が\n2 runtime で fail していた根本原因 2 件を修正:\n\n1. dump-go: 「ONNX Runtime shared library path not specified; set\n   ONNX_RUNTIME_SHARED_LIBRARY_PATH or pass it to Init」 で起動失敗。\n   既存 go-ci.yml と同じ pattern で ONNX Runtime download + cache +\n   ONNX_RUNTIME_SHARED_LIBRARY_PATH env 設定を追加。 ORT_VERSION は\n   1.24.4 (go-ci.yml と同じ pin) を env 変数で集約\n\n2. dump-rust: rust-lld 連携で「undefined symbol: __isoc23_strtoull /\n   __isoc23_strtol」 が出ていた。 これは ubuntu-22.04 の glibc 2.35 と\n   新しい ort-sys binary (glibc 2.38+ symbol を要求) の mismatch。\n   全 6 matrix を ubuntu-22.04 → ubuntu-24.04 に upgrade (既存 ci.yml の\n   rust-tests / go-ci の ubuntu-24.04 と整合) して解消\n\ninformational tier (continue-on-error: true) の挙動は維持。\n\n* fix(ci): runtime-parity-deep の Rust binary 名 + Go JSONL output 修正\n\nPR #511 commit bf144813 後の CI で残った 2 件の job fail を修正:\n\n1. dump-rust: 「No such file or directory: ./src/rust/target/release/piper-plus」\n   src/rust/piper-cli/Cargo.toml は [[bin]] override なし → package 名\n   `piper-plus-cli` がそのまま binary 名。 workflow の path を\n   piper-plus → piper-plus-cli に修正\n\n2. dump-go: 推論成功 (loaded ONNX, synthesized line=1) なのに\n   /tmp/parity/go.wav が無いことで ls が fail。 Go CLI の JSONL mode は\n   --output-file を無視し --output-dir/line_NNN.wav の連番ファイルを\n   書く仕様 (src/go/cmd/piper-plus/main.go:425)。 これは Rust/C# と異なる\n   contract だが上流変更は本 PR の scope 外。 workflow で --output-dir を\n   使い rename で go.wav に揃える形に修正\n\n* test(parity): close test gaps surfaced by 5-agent review\n\n5 並列 review agent (C++ API / WASM CLI / Python parity script /\nCI workflow / cross-runtime symmetry) で識別された Tier1+2 の\n網羅穴を保守的に塞ぐ。 Tier3 (WAV header structural checks for\n4 runtimes, 100MB+ files, markdown escape) は overkill のため defer。\n\nCI infrastructure 修正:\n- runtime-parity-deep.yml: Go 1.23 -> 1.26 (go-ci.yml 同期),\n  compare job Python 3.13 -> 3.11 (dump-python と ABI parity)\n\nRust CLI (test_cli_smoke.rs): JSONL phoneme_ids E2E が完全欠落\nしていたため 3 ケース追加 (1 つは ORT 不要、 2 つは #[ignore]\n+ test model exists check で E2E)。\n\nPython CLI (test_json_input_cli.py 新規): --json-input 経路の\nCLI subprocess 4 ケース (file / stdout / per-line override /\nmulti-line directory)。\n\naudio_parity.py (test_audio_parity.py): 4 ケース追加 (zero\ninputs + empty contract / duplicate runtime last-wins / corrupt\nWAV header / all runtimes disabled)。\n\neditorconfig-checker: Cargo.lock の indent (cargo 1.x の生成\nフォーマット) は editorconfig 4-space 規約と非互換のため除外\n追加 (既存の test_streaming_raw_phonemes.cpp と同パターン)。\n\n* fix(ci): single --inputs flag in compare loop (argparse last-wins bug)\n\nPR #511 Phase 2 で compare job が「5 skip / 1 input / 0 pair」を\nsilently 出力していた真因を特定。 dump 6 matrix は全 success だった\nが、 compare job の bash loop が --inputs を runtime 毎に prepend して\nいたため argparse の nargs=\"*\" 仕様 (同名 flag 出現毎に上書き) で\n最後の --inputs wasm=... のみが残り、 他 5 runtime は inputs に\n渡されなかった。\n\n修正: --inputs 1 回 + 全 RUNTIME=PATH を space 区切りで列挙する\nパターンに変更。 期待結果は C(6,2)=15 pair の tier 判定。\n\nこれまでの調査で副次的に判明した事項:\n- 全 artifact zip は wav 直下構造 (gh API で zip 確認)\n- compare job upload artifact にも全 6 wav が正しい layout で含まれた\n- bash loop の WARN echo は実は出力されておらず、 [-f] check は全\n  pass していた (gh API logs で確認)\n- 真因は 12 個の --inputs flag が argparse で 1 個に潰れたこと\n\ndefensive: bash loop に「Collected inputs (N runtimes): ...」echo\nを追加し、 同種の regression を即座に発見できるよう可観測性向上。",
          "timestamp": "2026-05-19T09:41:52+09:00",
          "tree_id": "ad6b5b8fd160a3bb8a4233e095feacce3f132861",
          "url": "https://github.com/ayutaz/piper-plus/commit/efe870fb589a16d0b6c11f084ffb8fa015c0c826"
        },
        "date": 1779151415807,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "RTF (en)",
            "value": 0.1008,
            "unit": "ratio"
          },
          {
            "name": "Latency P50 (en)",
            "value": 25.8,
            "unit": "ms"
          },
          {
            "name": "Latency P95 (en)",
            "value": 26,
            "unit": "ms"
          },
          {
            "name": "Cold Start (en)",
            "value": 1353.5,
            "unit": "ms"
          },
          {
            "name": "Peak Memory (en)",
            "value": 210.7,
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