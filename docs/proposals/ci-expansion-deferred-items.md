# CI/CD 拡張 — Defensive Foundations から外した 8 項目の詳細

**作成日**: 2026-05-18
**スコープ**: PR #511 (Defensive Foundations: Top 10 + §3 軽量 5 件) に乗せなかった 8 項目を、 **「実装作業は Claude Code が行うので人手工数は 0」 という前提で** 再評価したもの。
**前身ドキュメント**: 親調査 `ci-expansion-2026-05.md` および `ci-expansion-milestones.md` は PR #511 で役割を終え 2026-05-18 に削除済み。 本ドキュメントが M-Stretch 8 項目の集約後ソースとなる。

---

## 前提の置き換え — なぜこのドキュメントが必要か

親調査と M-Stretch マイルストーン (前身ドキュメント) は、 通常の「**人間 1 名が 4 週で着手できるか**」 という工数モデルで採否を判定していた。 PR #511 でも同じ基準で 8 項目を defer した。

しかし piper-plus の実装作業は実態として **Claude Code** が行っており、 ロジック組み立て / 試行錯誤 / 検証 / リファクタの工数は **0 と見なせる**。 この前提に置き換えると、 障壁の質が変わる:

| 障壁の質 | 通常モデルでの重み | Claude Code モデルでの重み |
|---------|-----------------|--------------------------|
| 試行錯誤の時間 | 高 (人間時間が稀少) | **0** |
| ファイル数の多さ | 高 (review 負荷) | 低 (機械的に正確) |
| 多言語横断 | 高 (専門性分散) | 低 (8 言語 G2P 横断対応の実績あり) |
| **外部サービス申請** | 中 | **高** (人間判断が必要) |
| **production deploy 検証** | 中 | **高** (実環境は CI で再現不能) |
| **設計判断 / RFC 必要** | 中 | **高** (community input 必要) |
| **CI minute 増加** | 低 | **中** (OSS unlimited だが queue tail latency 悪化) |
| **regression blast radius** | 高 | **高** (Claude Code でも release 系の breakage は実害) |
| **review 範囲の膨張** | 高 | **中** (logically 分割可能だが、 maintainer 1 名のレビュー帯域は有限) |

つまり、 **試行錯誤コストが消えても、 production 影響 / 外部依存 / 設計判断 / レビュー帯域は残る**。 本ドキュメントは 8 項目それぞれについて「Claude Code が実装するなら何が真の障壁か」 を整理する。

---

## 全体マップ

| 項目 | 親 doc § | カテゴリ | 真の障壁 (工数=0 後) | 推奨アクション |
|------|--------|--------|---------------------|--------------|
| [#1 Distroless / Chainguard](#1-distroless--chainguard-移行) | §3.6 W3-4 | Supply chain | production deploy 検証 | M-Stretch S5 個別 milestone (1 image / 1 PR) |
| [#2 SLSA Build L3](#2-slsa-build-l3) | §3.6 W5-6 | Supply chain | release breakage blast radius / hermetic build 設計 | M-Stretch S4 個別 milestone (1 registry / 1 PR) |
| [#3 Sigstore Rekor + Action SHA drift](#3-sigstore-rekor--action-sha-drift-監視) | §3.6 W2 | Supply chain | false positive 運用判断 / baseline 生成 | 本 PR 次以降に informational として追加可 |
| [#4 7 runtime CLI help auto-extract](#4-7-runtime-cli-help-auto-extract) | §3.7 Tier S #3 | Docs sync | CI minute 増 / auto-commit と branch protection | 単独 PR で追加可 (build matrix 8 並列 / 8 min) |
| [#5 spec contract toml ↔ impl 同期 gate](#5-spec-contract-toml--impl-同期-gate) | §3.7 Tier A | Docs sync | universal 化不能、 残 12 spec の優先度判断 | 個別 spec ごとに別 PR、 優先度は user が決める |
| [#6 mkdocs-material 統合配信](#6-mkdocs-material-統合配信) | §3.7 Tier A | Docs infra | 公開範囲設計 / i18n 戦略 / Pages 運用 | 別 milestone (docs infra) として独立 |
| [#7 Code example execution test](#7-code-example-execution-test) | §3.7 Tier A | Docs sync | docs audit + placeholder 規約 | 単独 PR 可、 ただし audit 結果を user 確認 |
| [#8 Test result aggregation](#8-test-result-aggregation) | §3.9 #2 | Observability | 既存 skill との重複、 Pages 基盤前提 | #6 mkdocs と coupling、 後回し |

---

## #1 Distroless / Chainguard 移行

### 目的 / 期待効果 (メリット)

- **container image attack surface の劇的削減**: 既存 `python:3.13-slim` ベース (~150MB、 sh / apt / Python 全部入り) を `cgr.dev/chainguard/python:latest` (~30MB、 shell 無し、 binary だけ) に置換すると、 CVE スキャンで検出される脆弱性が **典型的に 80-95% 減**。 piper-plus の Docker pull/run 環境 (HuggingFace Space / Home Assistant addon / self-host wyoming) の **脆弱性パッチ tail risk** を構造的に削減できる。
- **image pull 時間短縮**: HF Space の cold start (~60s) のうち image pull が ~30s を占めており、 distroless 化で半減すれば user-visible startup latency 改善 (体感の demo experience に直結)。
- **OpenSSF Scorecard +0.5pt 寄与**: Dangerous-Workflow / Pinned-Dependencies と並ぶ `Vulnerabilities` 項目で「base image の vuln 数 0」 が直接寄与 (現状 Scorecard で `Vulnerabilities` は最弱点)。
- **runtime supply chain attack 耐性**: 「container 内で `sh -c "wget malicious.sh | sh"` 系の post-exploitation pattern」 が shell 不在で構造的に不可能になる (defense in depth)。

### 対象 (5 Dockerfile)

```text
docker/python-inference/Dockerfile    # FastAPI + ORT 推論 API (HF Space で使用)
docker/webui/Dockerfile               # Gradio WebUI
docker/wyoming/Dockerfile             # Home Assistant 連携
docker/cpp-inference/Dockerfile       # C API デモ
docker/python-train/Dockerfile        # 学習環境 (GPU、 distroless 化困難)
```

### 真の障壁 (Claude Code 実装でも残るもの)

1. **production deploy 検証は CI で再現不能**:
   - HF Space (実 deploy) で entrypoint が動くかは push 後にしか分からない
   - Home Assistant addon の supervisor との互換性 (`s6-overlay` 等を期待する場合あり) は HA test instance が必要
   - Gradio の health probe を Python ベースに置換した場合、 user の reverse proxy 設定との互換性が読めない
2. **段階的 rollout が必須**:
   - 5 image を 1 PR で切り替えると、 1 つでも breakage があると全 deploy chain が止まる
   - 1 image ずつ別 PR で out (canary) → 1 週間 production 観測 → 次 image、 の運用 cadence が必要
3. **学習用 image (python-train) は distroless 不向き**:
   - `pyopenjtalk` の C 拡張 build に gcc / make が必要 → multi-stage builder 必須
   - GPU CUDA toolkit (`nvidia/cuda:12.x`) は distroless 提供なし、 そもそも対象外
4. **設計判断**:
   - Chainguard (商用、 ただし OSS 無料 tier あり) vs Google distroless (完全無料) の選定は user の判断
   - image tagging 戦略 (`piper-plus:1.12.0-distroless` を別 tag で出すか、 既存 tag を置換するか) は backwards-compat 設計

### 推奨

Distroless 個別 milestone として、 5 image を **1 image / 1 PR** の cadence で段階移行。 Claude Code が Dockerfile を書き換えるのは即時可能だが、 各 PR で **「user が HF Space に手動 push して動作確認」 する手順** を Test Plan に含める必要がある。

---

## #2 SLSA Build L3

### 目的 / 期待効果 (メリット)

- **OpenSSF Scorecard 9.0 → 9.3 への到達**: 残 `Token-Permissions` / `SAST` 項目を別途整備すれば 9.5 も視野。 9.3+ は OSS でも稀少 (top 5% 水準)。
- **release artifact の改竄不可能性証明**: 5 registry (PyPI / NuGet / crates.io / npm / Maven) の package を user が download する際、 in-toto attestation で「**GitHub Actions の workflow_X.yml の commit Y から build された**」 が cryptographic に検証可能。 Supply chain attack (`event-stream` 事件、 `colors.js` 事件) の **構造的予防**。
- **enterprise user の採用障壁低下**: SLSA L3 attested package は NIST SSDF / EU CRA 等の compliance 要件に直接 map されるため、 政府系 / regulated industry の adoption が容易になる。
- **既存 cosign 署名との相互補強**: 現状 `cosign-release-artifacts.yml` は artifact 署名のみ。 SLSA L3 generator は build provenance (どの commit / どの runner / どの input から作られたか) を追加するため、 「**署名されているが build 環境が compromised**」 ケースを補える。

### 対象 (5 registry release workflow)

```text
.github/workflows/release-pypi.yml         # piper-plus + piper-plus-g2p
.github/workflows/release-nuget.yml        # PiperPlus.Core / PiperPlus.Cli
.github/workflows/release-crates.yml       # piper-plus / piper-plus-cli / piper-plus-g2p (+ wasm)
.github/workflows/release-npm.yml          # piper-plus (npm) + @piper-plus/g2p
.github/workflows/release-maven.yml        # io.github.ayutaz:piper-plus-g2p-android
```

各 workflow に SLSA generator job 追加 (~40 行/workflow)。

### 真の障壁 (Claude Code 実装でも残るもの)

1. **release breakage の blast radius**:
   - 5 release workflow を同時に書き換えると、 1 つでも breakage があると next release 全 registry が ship 不能
   - 1 registry / 1 PR で段階導入 → tag 1 個 (v1.13.0-rc.1 等) で actual release 検証 → 次 registry、 が安全
2. **hermetic build 設計の非互換**:
   - SLSA L3 は **`workflow_dispatch` の手動 input が parameterless trigger に近いこと** を要求 (input が build output に影響しない構造)
   - 既存 release workflow の多くが `inputs.version` で tag 上書きを許容している → hermetic 化のために `git tag` から取る形に統一が必要
3. **Maven Central の特殊性**:
   - 既存 GPG 署名 + Sonatype OSSRH ワークフローと SLSA generator の attestation を 1 release に両方含める設計は非自明
   - Android AAR は JAR と classifier が違うため、 attestation の `subject` 構成が一筋縄でない
4. **設計判断**:
   - 5 registry を **同じ tag / 同じ run** で同時 release するか、 個別 trigger を許容するか
   - SLSA verifier (`slsa-verifier`) の使い方を README に記載するかどうか (記載すれば user benefit 大、 ただし docs 更新範囲が広がる)
5. **release 経路の知見が必要**:
   - 各 registry の token / secret 設定 (`PYPI_API_TOKEN`、 `NUGET_API_KEY` 等) と SLSA generator が要求する `id-token: write` permission の relation
   - 既存 token 戦略を変更する必要があるか (trusted publisher 移行可否) は registry ごとに調査必要

### 推奨

SLSA Build L3 個別 milestone。 **1 registry / 1 PR** の cadence で、 各 PR は (a) workflow 改変、 (b) v1.13.0-rc.X で actual release、 (c) verifier で attestation 確認、 を 1 set として含める。 Claude Code は workflow YAML を書けるが、 各 step の RC release は user の判断で実行。

---

## #3 Sigstore Rekor + Action SHA drift 監視

### 目的 / 期待効果 (メリット)

- **release artifact の改竄検出**: ユーザーが PyPI / NuGet 等から download した package を、 piper-plus の sign 経路 (`cosign-release-artifacts.yml`) で signed されたものと **Rekor transparency log 経由で再検証** 可能。 release 後に PyPI account compromise されて malicious package が同一 version で reupload された場合の検出経路を確立。
- **upstream action の supply chain 攻撃検出 (Action SHA drift)**:
  - 現状 `action-pin-gate.yml` は SHA pin **形式** を強制 (sliding `@v3` 禁止) するだけで、 pin した SHA が upstream で revoke / force-push されたケースは検出不能
  - `tj-actions/changed-files` 事件 (2025 年 3 月): SHA pin していた user も、 attacker が同一 SHA を保つように force-push したため被害発生 → 「**pin した SHA が依然として正規 commit に紐づいているか**」 を週次で監視する gate が必要
- **OpenSSF Scorecard +0.5pt 寄与**: `Dangerous-Workflow` 関連で「**pinned SHA が dangling していない**」 を informational gate で trend 化できる。
- **PR #414 教訓の構造的延長**: 「pin format 強制 → pin 自体の生存確認」 への defensive layer 追加。 同種事件再発時に「気付いた頃には sub-dependency 経由で侵入済」 になるのを防ぐ。

### 実装内容 (Claude Code が作るもの)

**3a. Sigstore Rekor verification workflow** (新規):

```yaml
# .github/workflows/rekor-verify.yml (informational, weekly)
- run: |
    for tag in $(gh release list -L 10 --json tagName -q '.[].tagName'); do
      cosign verify-blob \
        --rekor-url https://rekor.sigstore.dev \
        --certificate-identity-regexp "https://github.com/ayutaz/piper-plus" \
        --certificate-oidc-issuer https://token.actions.githubusercontent.com \
        --signature <fetched .sig> --certificate <fetched .crt> \
        <fetched artifact>
    done
```

**3b. Action SHA drift checker** (新規 script):

```python
# scripts/check_action_sha_drift.py (~100 lines)
# 全 .github/workflows/*.yml から uses: の SHA pin を抽出
# 各 SHA を GitHub API で resolve、 dangling / force-pushed を検出
# baseline (scripts/action_sha_baseline.json) で既知の OK を吸収
```

```yaml
# .github/workflows/action-sha-drift.yml (informational, weekly)
schedule: ['0 4 * * 1']  # 月曜 04:00 UTC
- run: uv run python scripts/check_action_sha_drift.py
```

### 真の障壁 (Claude Code 実装でも残るもの)

1. **GitHub API rate limit と baseline 生成**:
   - 既存 pin ~270 個 × commits API 1 call = 1 回の workflow run で 270 req
   - `GITHUB_TOKEN` の 5000 req/h 内に収まるが、 失敗時 retry を含めると **rate limit safety margin の設計が必要**
   - baseline (現時点の SHA → tag/branch 解決結果) を初回に scan で生成する必要があり、 generated artifact を commit するか否かの判断
2. **false positive 運用判断**:
   - 「dangling SHA」 = upstream で reference が消えたが SHA 自体は git db に残存 → **これは安全か危険か** の判定は人手
   - org / repo deletion (`unmaintained/some-action`) と force-push attack は区別困難 → informational tier で trend を見るしかない
3. **PR を block するか informational か**:
   - blocker 化すると upstream action の事故で本 repo の release が止まる → informational tier 推奨
   - ただし informational のままだと「誰も artifact を見ない」 結末になる risk → trend を Issue auto-create する設計が必要
4. **Rekor verify の対象選定**:
   - 最新 10 release を毎週 verify するか、 全 release を verify するか
   - signed されていない古い release (cosign 導入前) は skip する条件分岐が必要

### 推奨

**本 PR の次の PR で informational tier として追加可能**。 PR #511 が 18 commits / 9 新規 workflow を持つため、 review scope 膨張回避のため別 PR が望ましい。 Claude Code が実装するなら 1-2h 程度で workflow + script 1 set 完成、 ただし **baseline JSON 生成 + 1 週間の informational 観測** で false positive 率を測ってから設計を確定する cadence。

---

## #4 7 runtime CLI help auto-extract

### 目的 / 期待効果 (メリット)

- **docs ↔ CLI の drift 検出**: 既存 `cli-flag-contract.toml` は **flag 存在** を強制するが、 `--help` 出力の **wording / description / example** までは検出していない。 README / 個別 runtime docs に書かれた CLI 説明と実装の drift を構造的に検出可能。
- **contributor 体験の劇的改善**: README が指す flag が「実装側で renamed / removed されていて動かない」 ケース (PR #346 で発生した text_splitter 系の drift と同質の問題) を防ぐ。 新規 contributor が README から始めて壁にぶつかる体験を構造的に消せる。
- **release notes の自動補強**: CLI flag 差分が `docs/reference/cli-help/<runtime>.txt` の git diff として可視化されるため、 CHANGELOG の `### Changed` セクションを書くときの一次資料が常に最新。
- **多言語 G2P エコシステムの一貫性**: 8 言語 G2P を 7 runtime で同期している piper-plus の特性上、 CLI の flag 命名規約 (`--language ja-en-zh` のような区切り) が runtime 間で drift しないことの保証は user-visible value 大。

### 対象 (生成ファイル)

```text
docs/reference/cli-help/python.txt    # uv run python -m piper --help
docs/reference/cli-help/rust.txt      # cargo run -p piper-plus-cli -- --help
docs/reference/cli-help/csharp.txt    # dotnet run --project PiperPlus.Cli -- --help
docs/reference/cli-help/go.txt        # go run ./cmd/piper-plus --help
docs/reference/cli-help/wasm.txt      # node src/wasm/openjtalk-web/dist/cli.js --help
docs/reference/cli-help/cpp.txt       # ./build/piper_plus --help
docs/reference/cli-help/g2p-python.txt  # uv run python -m piper_plus_g2p --help
```

`cli-help-extract.yml` workflow が weekly + manual で全 runtime build → `--help` 出力 → `git diff --exit-code` で drift 検出、 PR base では block。

### 真の障壁 (Claude Code 実装でも残るもの)

1. **CI minute 増 (build 重)**:
   - Rust release build: ~5 min
   - C++ CMake + ORT 取得: ~8 min (ORT download cache が必要)
   - C# dotnet restore + build: ~3 min
   - WASM emsdk + wasm-pack: ~6 min
   - 7 runtime parallel matrix で **wall clock ~8 min**、 ただし concurrent runner queue を圧迫
   - 既存 workflow 93 本のうち重い build を持つものは ~15 本、 +1 で目に見える concurrency 影響
2. **auto-commit workflow と branch protection**:
   - `GITHUB_TOKEN` で push する設計は branch protection の `Require pull request` rule に block される
   - 解決策 a: `auto-commit` を別 bot account 経由 → bot account 作成 + SSH key 管理 (人手)
   - 解決策 b: PR を自動作成して human merge → 結局 review burden 残る
   - 解決策 c: drift 検出時に **CI fail のみで auto-commit しない** → drift 修正は human 側
3. **`--help` 出力の non-determinism**:
   - 一部 runtime で version string (`piper-plus 1.12.0-dev`)、 build timestamp、 absolute path が出力に含まれる
   - これらを post-process で sanitize する rule を runtime ごとに設計
4. **Android G2P には CLI が無い**:
   - `io.github.ayutaz:piper-plus-g2p-android` は library のみで CLI 提供せず → 7 runtime ではなく 6+ runtime 対象
   - Swift G2P も同様、 `examples/swift-g2p/HelloG2P` は CLI を持つがこれは library そのものではない

### 推奨

**単独 PR で追加可能**。 Claude Code が実装するなら workflow YAML + 各 runtime build 設定 + drift detection script で半日。 ただし **CI minute 影響** を user に確認してから merge 推奨 (queue tail latency 増加が体感されるか)。 既存 `cli-flag-contract.toml` との関係は **「contract が flag 存在を、 cli-help が wording を担保」** で重複なし、 補完関係。

---

## #5 spec contract toml ↔ impl 同期 gate

### 目的 / 期待効果 (メリット)

- **spec doc が「実装と乖離した死文」 になることを構造的に防止**: piper-plus は `docs/spec/*-contract.toml` を 30 個持ち、 これらが**実装 → spec ではなく、 spec → 実装の単方向 truth source** として設計されている (loanword / PUA / 音素表等)。 spec が drift すると multi-runtime 同期そのものが崩壊するため、 sync gate の存在自体が architecture の前提。
- **新規 runtime 追加時の onboarding コスト削減**: Swift G2P / Kotlin G2P 追加時、 既存 13 spec の gate がなければ「どこに何を合わせるべきか」 を README 散読で発見する必要があった。 残 12 spec も gate 化すれば、 next runtime 追加 (例: PHP / Ruby G2P) 時に「**12 spec のうち N 個に違反**」 と自動列挙される。
- **release 前の自信**: `release-versions.toml` ↔ 5 registry の package metadata 同期は手動運用 → bump 時の typo 事故 (PR #401 系の version mismatch) を構造的に予防。
- **spec doc の rot 防止**: gate が無いと spec は時間とともに「**書かれているが守られていない fiction**」 化する (typical software 病理)。 gate により doc の信頼性そのものが上がる。

### 既存カバレッジ (13 spec、 gate 実装済)

| Spec | 検証 script | 機能 |
|------|-------------|------|
| `ort-session-contract.toml` | `scripts/check_ort_session_contract.py` | ORT session 設定が 7 runtime 横断一致 |
| `short-text-contract.toml` | `scripts/check_short_text_contract.py` | 短テキスト Strategy A/B/C のパラメータ |
| `text-splitter-contract.toml` | `scripts/check_text_splitter_contract.py` | 文末記号 / SSML 扱い |
| `phoneme-timing-contract.toml` | `scripts/check_phoneme_timing_contract.py` | hop_length / sample_rate の式 |
| `audio-parity-contract.toml` | `scripts/check_audio_parity_contract.py` | SNR / mel-spec MSE 閾値 |
| `pua-contract.toml` | `scripts/check_pua_consistency.py` | PUA codepoint allocation |
| `loanword-mirrors.toml` | `scripts/check_loanword_consistency.py` | ZH-EN loanword 10 mirror |
| `dictionary-mirrors.toml` | `scripts/check_dictionary_sync.py` | 辞書 mirror |
| `ssml-contract.toml` | `scripts/check_ssml_consistency.py` | SSML AST 構造 |
| `chinese-tone-contract.toml` | 個別 gate | 声調表記 |
| `japanese-n-variant-contract.toml` | 個別 gate | ん の 4 variant |
| `pt-dialect-contract.toml` | 個別 gate | BR / EU 切替 |
| `cli-flag-contract.toml` | `scripts/check_cli_flags.py` | CLI flag 存在 |

### 残カバレッジ穴 (12 spec、 gate 無し)

```text
artifact-retention-contract.toml      # workflow の retention-days を解析
audio-format-contract.toml            # WAV header / sample rate
inference-input-contract.toml         # ONNX 入力 tensor 名/形状
language-id-map-contract.toml         # language_id (ja=0...) と export_onnx.py / 各 runtime const の parity
model-sha256-manifest.toml            # release artifact の SHA
onnx-export-contract.toml             # FP16 / opset / providers のデフォルト
ort-provider-contract.toml            # provider 列挙
phoneme-set-version.toml              # version 文字列
release-versions.toml                 # 5 registry の version 同期
streaming-api-contract.toml           # streaming API surface (Python / Rust)
swift-g2p-contract.toml               # Swift package surface
test-flake-retry-contract.toml        # retry 設定
```

### 真の障壁 (Claude Code 実装でも残るもの)

1. **「universal な validator」 は構造的に作れない**:
   - 各 toml が固有領域の語彙 (language_id_map は `{ja: 0, en: 1, ...}` 形式、 onnx-export-contract は ONNX opset / provider 名等) を持つ
   - 12 spec それぞれに専用パーサ + 実装側 const の抽出 logic が必要 → **個別 script 12 本** が現実解
2. **優先度の判断は user**:
   - 12 spec 全部に gate を追加すると CI minute / pre-commit 時間が線形に増える
   - ROI 順序 (例: `release-versions.toml` は高 ROI、 `test-flake-retry-contract.toml` は低 ROI) は user の運用判断
   - Claude Code は単独で「どの spec から手を付けるべきか」 を決められない
3. **既存 spec の解釈が必要なケース**:
   - 一部 spec は「**実装側にも canonical const が存在しないため、 妥当な抽出元が無い**」 (例: `release-versions.toml` は git tag が canonical、 toml は記録目的)
   - これらは「双方向 sync」 ではなく「**toml = git tag の post-hoc snapshot**」 として位置付け直す必要があり、 spec doc 側の rewrite が必要

### 推奨

**個別 spec ごとに別 PR**。 Claude Code が実装するなら spec 1 個あたり 2-4h で gate script + workflow 完成。 ただし **どの spec から手を付けるか** は user の優先度判断が必要。 推奨優先順:

1. `release-versions.toml` (高 ROI、 release 事故予防)
2. `language-id-map-contract.toml` (新言語追加時に効く)
3. `onnx-export-contract.toml` (export 設定 drift 検出)
4. `inference-input-contract.toml` (ONNX 入力契約)
5. 残 8 spec (ROI 順序を user と相談)

---

## #6 mkdocs-material 統合配信

### 目的 / 期待効果 (メリット)

- **散在 docs の navigability 劇的改善**: 現状 `docs/` 配下 ~150 .md は GitHub UI で順序なく並ぶだけ → mkdocs nav で「**Getting Started → Runtimes → API Reference → Migration → Spec**」 の階層化により、 新規 user が「自分が読むべき doc」 にたどり着く時間が劇的に短縮。
- **検索可能化**: mkdocs-material は内蔵 lunr / algolia 検索を持ち、 `docs.piper-plus.dev/search?q=ssml` のような full-text 検索が可能 → contributor は GitHub の repo-wide search より精度高く該当 doc に到達できる。
- **多言語 docs の正規化**: 現状 README.md (英) / README-ja.md (日) は手動 mirror → mkdocs-i18n plugin で **「英語が canonical、 日本語は翻訳 (Mark of canonical version)」** という関係を構造化、 翻訳遅延を可視化。
- **API doc 自動生成との統合**: Sphinx (Python) / Rustdoc / TypeDoc 等の生成物を `mkdocs.yml` の external section として埋め込めば、 「**1 サイトに全 runtime API doc**」 が実現可能 (現状は各 runtime 個別配信)。
- **release notes / CHANGELOG の publishing**: CHANGELOG.md を mkdocs page として配信すれば、 user が「v1.12.0 で何が変わったか」 を fragment URL で共有可能 (例: `docs.piper-plus.dev/changelog#1-12-0`)。

### 実装内容 (Claude Code が作るもの)

```text
mkdocs.yml                              # nav 階層 + i18n plugin + 検索 + theme
.github/workflows/docs-deploy.yml       # build + Pages deploy
docs/index.md                           # landing page (新規)
docs/getting-started/                   # quick start / install (新規ディレクトリ)
docs/runtimes/{python,rust,csharp,go,wasm,cpp,android,ios}.md  # 集約
docs/                                   # 既存 reference / spec / migration / guides を nav に組込
overrides/                              # mkdocs-material theme customization
```

加えて既存 ~150 .md の **link 修正** (相対 path → mkdocs nav-relative) を全部行う必要があり、 これだけで mass edit が ~500 箇所。

### 真の障壁 (Claude Code 実装でも残るもの)

1. **公開範囲の選別 (設計判断)**:
   - `.claude/` (skill / hook) は内部用 → 除外
   - `docs/proposals/` は roadmap doc → **公開すべきか非公開か** は user 判断 (公開すれば transparency 上がるが、 「採用されない proposal」 を user が roadmap と誤解する risk)
   - 実装途中の作業ノート (tickets / TODO 系) は公開判断
   - `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md` は公開、 内部運用 docs は非公開
2. **i18n 戦略の選択 (設計判断)**:
   - 現状の `README.md` / `README-ja.md` (二重 mirror) を維持するか、 mkdocs-i18n の `i18n/{en,ja}/` 構造に移行するか
   - 移行する場合、 既存 `README-ja.md` への inbound link (Issue / 外部 blog 記事) が dead link 化
   - 言語自動切替 vs URL 明示 (`/en/`, `/ja/`) も判断
3. **Pages 配信か別 host か**:
   - GitHub Pages 無料、 ただし `piper-plus.github.io/piper-plus/` のような repo-prefix URL
   - Cloudflare Pages / Netlify を使えば custom domain (`docs.piper-plus.dev`) が容易、 ただし account / DNS の人手設定
   - HuggingFace Spaces もオプション
4. **link 移行の inbound 影響**:
   - 既存 `https://github.com/ayutaz/piper-plus/blob/dev/docs/migration/v1.11-to-v1.12.md` への外部 link は維持されるが、 mkdocs 配信に user を誘導するなら canonical link 更新が広範囲
   - search engine indexing の重複コンテンツ問題

### 推奨

**別 milestone (Docs Infra) として独立**。 Claude Code が実装するなら mkdocs.yml + workflow + 既存 .md の link 修正で 1-2 日相当の change set、 ただし上記設計判断 4 件は user の明示的意思決定が必要 → **proposal → user 承認 → 実装の 2 phase** が望ましい。 本 PR (defensive foundations) とは性質が違うため別ライン推奨。

---

## #7 Code example execution test

### 目的 / 期待効果 (メリット)

- **README / docs の「実行可能性」 を構造的保証**: 「README 通りにコマンドを打ったが動かない」 を contributor が遭遇する事故を構造的に消せる。 piper-plus は 7 runtime × 8 言語の組合せが多く、 例の数も多いため、 manual maintenance では追いきれない領域。
- **migration guide の信頼性**: `docs/migration/v1.11-to-v1.12.md` の「**v1.11 用 code → v1.12 用 code**」 の対比例が、 実際に v1.12 で実行できることを CI で保証 → user の migration 体験が劇的に改善。
- **dead example の早期検出**: 過去の Python API (PR #320 系) を参照する古い例が docs に残存している場合、 doctest gate で即検出 → docs rot を防ぐ。
- **新規 contributor の onboarding**: 「README コピペで動く」 を保証することは、 OSS adoption の最大の onboarding 障壁を除去する直接的施策。

### 実装内容 (Claude Code が作るもの)

```python
# scripts/check_doc_examples.py (~200 lines)
import re, subprocess
from pathlib import Path

PLACEHOLDER_RE = re.compile(r'<[^>]+>')  # <path>, <model.onnx> 等は skip

for md in Path('docs').rglob('*.md'):
    for block in extract_fenced_blocks(md, lang_filter={'bash', 'python', 'rust', ...}):
        if PLACEHOLDER_RE.search(block.code):
            continue  # 人手置換必要、 skip
        if block.has_directive('# noexec'):
            continue  # 明示 skip
        run(block, working_dir=md.parent)
```

```yaml
# .github/workflows/doc-examples.yml
strategy:
  matrix:
    lang: [bash, python, rust, csharp, go, wasm]
```

### 真の障壁 (Claude Code 実装でも残るもの)

1. **既存 docs の audit が前提**:
   - 「動かない例」 が既存 docs に何件残存しているかは未知 (推定 10-30 件)
   - 一括 audit (Claude Code 実施可能、 ただし user 確認必要) → 「修正」 「skip directive 付与」 「placeholder 化」 のどれを取るかの判断が必要
   - audit 結果を user が確認しないと、 「修正したつもりだが意図と違う」 の事故 risk
2. **placeholder 規約の整備**:
   - 現状 docs に書かれた `<path>` / `/path/to/model.onnx` / `your-token-here` のフォーマットが不統一
   - doctest が skip すべき pattern を明確化する規約 (例: `<{placeholder}>` 形式に統一、 `# doctest:skip` directive) を user 合意のもと制定
3. **multi-runtime environment setup**:
   - 7 runtime + 8 言語 + ONNX model download + GPU optional の組合せを 1 workflow に詰め込むと CI 30+ min
   - matrix 分割しても各 runtime の setup overhead (Rust toolchain / dotnet / emsdk 等) を毎回 fetch するため、 cache 戦略が複雑
4. **model download 帯域**:
   - 「例」 が ONNX model (~250 MB) を要する場合、 doctest 実行ごとに HF download が走る
   - HF rate limit / 安定性に依存、 GitHub Actions cache に乗せる設計が必要
5. **falsy success の risk**:
   - bash 例が `&&` 連結でなく `;` 連結で書かれている場合、 中間 step が失敗しても exit 0 になる
   - doctest 側で `set -euo pipefail` を強制注入する設計判断

### 推奨

**単独 PR 可、 ただし phase 分割推奨**:

1. PR-A: audit 専用 (`check_doc_examples.py` を `--audit` mode で走らせて結果を Issue 化、 修正は user 判断)
2. PR-B: doctest gate を informational tier で導入 (audit 結果を反映した skip directive 付き)
3. PR-C: 1 ヶ月の informational 観測後に blocker 昇格

---

## #8 Test result aggregation

### 目的 / 期待効果 (メリット)

- **7 runtime の test 健康状態を 1 画面で**: 現状 contributor は PR の status check リストから 7 runtime の test 結果を 1 つずつクリックして確認 → aggregator により「**total 4321 pass / 12 skipped / 0 fail across 7 runtimes**」 と即座に把握可能。
- **runtime 横断 flake の発見**: 単一 runtime では flake と気付かない test が、 7 runtime aggregation で見ると「**特定の Python test が他 runtime の同等 test と比べて 3 倍 skip 率が高い**」 のような pattern を可視化可能。
- **release readiness の判断材料**: 「**全 runtime で last green commit が同じ commit か**」 を 1 画面で見れることは、 release 判断の重要な signal (現状は手動で各 runtime workflow を確認している)。
- **`/check-cross-runtime` skill との補完**: 既存 skill は **parity 検証** (loanword / PUA / G2P 出力一致)、 aggregation は **test 結果の統計** で機能補完関係。

### 実装内容 (Claude Code が作るもの)

```python
# scripts/aggregate_test_results.py (~150 lines)
import junitparser
results = {}
for runtime in RUNTIMES:
    suite = junitparser.JUnitXml.fromfile(glob(f'artifact/{runtime}/*.xml'))
    results[runtime] = {'total': ..., 'passed': ..., 'failed': ..., 'skipped': ..., 'duration': ...}
json.dump(results, open('test-aggregate.json', 'w'))
```

加えて 7 runtime 全部に **junit/xml 出力を統一実装**:

```text
Python:  pytest --junit-xml=test-results.xml         # 既出
Rust:    cargo test -- --format json | cargo2junit   # 追加
C#:      dotnet test --logger:junit                  # 既出
Go:      gotestsum --junitfile=test-results.xml      # 追加 (gotestsum 導入)
WASM:    jest --reporters=jest-junit                 # 追加
C++:     ctest --output-junit                        # 既出 (CMake 3.21+)
Kotlin:  gradle test (JUnit XML 自動出力)             # 既出
```

### 真の障壁 (Claude Code 実装でも残るもの)

1. **既存 `/check-cross-runtime` skill との機能重複**:
   - skill は loanword / PUA / G2P parity を runtime 横断検証
   - aggregator は test 統計 (pass/fail count) を集約
   - **「contributor が見るとき、 どちらを使えばいいか」** の住み分けが曖昧 → user 設計判断
2. **Pages 基盤前提**:
   - aggregated JSON を artifact として置くだけでは 「raw JSON が増えた」 だけで user-visible value 薄い
   - 真の value は dashboard 可視化 → mkdocs (#6) が前提
3. **Go test の junit 出力**:
   - `gotestsum` 追加導入が必要 (Go 標準ではない)
   - 既存 Go test workflow の修正範囲が広い (~793 test の出力 format 変更)
4. **WASM test runner の粒度問題**:
   - jest / mocha は statement-level 統計 (test 関数単位) のみ、 他 runtime と粒度が違う
   - Rust の `cargo test` は `mod` 単位、 C# は class 単位 → **「test 1 件」 の定義が runtime 間で揃わない**
5. **flake retry との関係**:
   - `test-flake-retry-contract.toml` で定めた retry policy が runtime ごとに違う
   - aggregator が「retry 1 回で pass」 を「pass」 とカウントすると flake 検出が機能しない → retry 履歴も集計対象に含める設計が必要

### 推奨

**#6 mkdocs と coupling、 後回し**。 単独 PR でも実装可能だが、 上記 problem 1 (skill 重複) と 2 (Pages 前提) により、 aggregator を入れても「user-visible 価値が薄い JSON が増えた」 で終わる risk。 `/check-cross-runtime` skill の機能拡張として redesign する選択肢もあるが、 これは別 RFC レベルの議論。

---

## 8 項目の優先度マトリクス (実装工数 = 0 前提)

実装工数を 0 として、 **設計判断必要度 / 外部依存 / production 影響 / review 範囲** の 4 軸で再評価:

| 項目 | 設計判断 | 外部依存 | production 影響 | review 範囲 | 推奨順位 |
|------|---------|---------|----------------|-----------|---------|
| #3 SHA drift + Rekor verify | 中 | GitHub API | 低 (informational) | 小 | **1 (最優先)** |
| #4 7 runtime CLI help | 中 (auto-commit 戦略) | なし | 低 (drift 検出のみ) | 中 (build matrix) | **2** |
| #7 Code example execution test | 高 (placeholder 規約) | model HF | 中 (informational 化で緩和) | 大 (audit 結果) | **3** |
| #5 spec sync gate | 中 (12 spec の優先度) | なし | 低 | 小 (1 spec ずつ) | **4 (個別 PR)** |
| #1 Distroless | 中 (image 戦略) | HF Space / HA | **高 (deploy 経路)** | 中 | **5 (個別 PR)** |
| #8 Test aggregation | **高 (skill 重複)** | なし | 低 | 中 | **6 (#6 と coupling)** |
| #6 mkdocs | **高 (公開範囲 / i18n)** | Pages | 低 | **大 (link 全修正)** | **7 (別 milestone)** |
| #2 SLSA L3 | 高 (hermetic build) | 5 registry | **高 (release 経路)** | 中 | **8 (個別 registry PR)** |

---

## 結論 — 何を本ブランチ後の next step として取るか

**Tier 1 (本 PR の次の PR、 単独 / 小規模)**:

- #3 Sigstore Rekor + Action SHA drift (informational tier、 ~2h Claude Code 実装)
- #4 7 runtime CLI help auto-extract (~半日 Claude Code 実装、 CI minute 影響を user 確認後)

**Tier 2 (個別 PR で 1 つずつ、 中規模)**:

- #5 spec sync gate (1 spec / 1 PR、 user の優先度判断要)
- #7 Code example execution test (audit phase A → gate phase B の 2 PR)

**Tier 3 (別 milestone、 設計判断必要)**:

- #1 Distroless (M-Stretch S5、 1 image / 1 PR)
- #2 SLSA L3 (M-Stretch S4、 1 registry / 1 PR)
- #6 mkdocs-material (Docs Infra milestone)
- #8 Test result aggregation (#6 mkdocs と coupling)

実装作業を Claude Code が引き受ける前提では、 **試行錯誤の人手工数は 0** だが **設計判断・production deploy 検証・review 帯域・外部依存** は依然として人間判断を要する。 これらの真の障壁を可視化することで、 「**何が技術的不可能 / 何が単に未着手か**」 の境界を明確化したのが本ドキュメントの貢献。

---

## 関連ドキュメント

- [`.claude/README.md`](../../.claude/README.md) — 既存 skill / hook / pre-commit gate
- [`CHANGELOG.md`](../../CHANGELOG.md) Unreleased セクション — PR #511 で実装された Top 10 + §3 軽量 5 件の workflow 一覧
- `git log --diff-filter=D -- docs/proposals/` — 前身ドキュメント (`ci-expansion-2026-05.md` / `ci-expansion-milestones.md`) の履歴

---

## 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-18 | 初版 — PR #511 (defensive foundations) で defer した 8 項目を Claude Code 実装前提で再評価 | Claude Code |
