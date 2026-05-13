---
name: check-cross-runtime
description: Python canonical (`src/python_run/piper/`, `src/python/piper_train/`, `src/python/g2p/piper_plus_g2p/`) を変更した PR で、 ONNX I/O 以外の追随漏れ (phonemizer / config schema / CLI flag / data 形式 / API 変更) を 7 ランタイム + 2 docker image 範囲で fail-fast 検出する。PR #443 (Python のみ修正 → 4 runtime + 2 docker で同バグ) / PR #391 (Python のみ修正 → 5 runtime 古いまま) の silent regression パターンへの対策。`/check-runtime-parity` (ONNX グラフ I/O 限定) と `/check-new-runtime-asset` (新規アセット配布) を補完する 3 つ目の sibling skill。
disable-model-invocation: true
allowed-tools: Bash(git diff *) Bash(git status *) Bash(grep *) Bash(ls *) Bash(python *) Bash(uv run *)
---

<!-- editorconfig-checker-disable-file -->

# Python 変更 → N ランタイム追随漏れチェック

`src/python_run/piper/*.py`、 `src/python/piper_train/*.py`、 または
`src/python/g2p/piper_plus_g2p/*.py` を変更した PR で、 他 7 ランタイム
(C# / Rust × 2 crate / Go / JS-WASM / C API / iOS SPM / Kotlin-Android /
Swift G2P) + 2 docker image (python-inference / webui) が **同じ振る舞いに
追随しているか** を PR 提出前に確認する。

## なぜこの skill が必要か (既存 2 skill との関係)

| skill | スコープ | 補完範囲 |
|---|---|---|
| `/check-runtime-parity` | **ONNX グラフ I/O** (入出力名・形状・dtype) の変更 | 推論バックエンドだけ |
| `/check-new-runtime-asset` | **新規データファイル** (JSON/TOML/TSV) の 7 箇所 metadata 配布 | wheel/sdist 同梱漏れだけ |
| **`/check-cross-runtime` (本 skill)** | **それ以外の Python 変更** = phonemizer ロジック / config field / CLI flag / data file 形式変更 / API 変更 / docker recipe | 既存 2 skill の網からこぼれる広い領域 |

3 skill を組み合わせると、 Python canonical の変更が 7 ランタイム + 2 docker
全部に伝播しているかを 1 PR ごとにチェックできる。

## 過去事故サマリ

| PR | Python 修正内容 | 追随漏れ | 検出方法 |
|---|---|---|---|
| **#391** | speaker_embedding 形状修正 | 5 ランタイム (Rust / Go / C# / C++ / WASM) が古い形状のまま | PR #443 で偶然発見 (silent regression) |
| **#443** | MB-iSTFT speaker_embedding 未対応の修正 | 4 runtime (Rust / Go / C# / WASM) + 2 docker image (python-inference / webui) で同じバグ | 手動レビューでようやく発見 |
| **#384** | ZH-EN loanword 辞書 schema 拡張 | Rust / Go / C# / WASM / C++ で旧 schema のままパース失敗 | CI gate を後付けで作成 |

共通パターン:

1. Python で 1 関数 / 1 schema を 「サクッと」 修正
2. ローカル `pytest` は green、 CI も Python 観点だけ通る
3. レビュアーも Python diff しか見ない
4. 別 PR / リリース後ユーザー報告で 「他ランタイム壊れている」 が判明

この skill は **PR 提出前** に local で同じ修正が他ランタイムにも入っているか
チェックリスト化する。

## スコープ判定 (何を見るか)

### Canonical Python の 3 source of truth

| カテゴリ | パス | 対応する他ランタイム |
|---|---|---|
| **A. ランタイム推論** | `src/python_run/piper/*.py` (voice.py, http_server.py, text_splitter.py, timing.py, model_manager.py) | C# / Rust core / Go / WASM / C API / iOS SPM |
| **B. G2P / phonemizer** | `src/python/g2p/piper_plus_g2p/*.py` (japanese.py, chinese.py, multilingual.py, ssml.py 等) | Rust piper-plus-g2p / Go phonemize / C# Phonemize / WASM g2p / C++ *_phonemize.cpp / Kotlin / Swift G2P |
| **C. モデルエクスポート / 学習** | `src/python/piper_train/*.py` (export_onnx.py / vits/models.py / infer_onnx.py) | **ONNX I/O 変更なら `/check-runtime-parity` を使う**。 それ以外の周辺ロジック (chunking / scaling / sentence split 等) が本 skill 対象 |

### スコープ外 (本 skill では skip)

- ONNX 入出力名 / 形状 / dtype の追加・改名 → `/check-runtime-parity`
- 新規 JSON/TOML データファイル追加 → `/check-new-runtime-asset`
- ruff format / type stub のみ → 何もしない
- `tests/`, `docs/`, `.github/workflows/`, `CHANGELOG.md` のみ → 何もしない

## 影響度の 3 段階分類

| 影響度 | 例 | 推奨アクション |
|---|---|---|
| **軽微 (Low)** | 内部リファクタ・docstring・型注釈・テスト追加 | 他 runtime touch 不要、 PR description に明記して skip |
| **中 (Medium)** | 新規 phonemizer 関数追加 / 既存関数の挙動拡張 / 新規 CLI flag / 公開 API への field 追加 | **Rust + Go + C# を同 PR で実装**、 WASM/C++/iOS/Kotlin/Swift は follow-up issue 化 |
| **重大 (High)** | config schema 変更 / data file 形式変更 / model schema 変更 / 互換性破壊 | **全 7 runtime + 2 docker 同 PR が望ましい**。 不可なら release blocker issue を立ててから merge |

判定の目安:

- **「他 runtime に同じバグが潜むか?」** → Yes なら Medium 以上
- **「version field を bump したか?」** → Yes なら High
- **「ユーザーが直接触る面 (CLI / HTTP / library API) か?」** → Yes なら Medium 以上

## 実行手順

### 1. canonical Python が触られているか確認

```bash
CANONICAL_PATTERN='^(src/python_run/piper/|src/python/piper_train/|src/python/g2p/piper_plus_g2p/).*\.py$'

CANONICAL_TOUCHED=$(git diff --name-only origin/dev...HEAD | grep -E "$CANONICAL_PATTERN" || true)

if [ -z "$CANONICAL_TOUCHED" ]; then
  echo "canonical Python は変更されていない — このチェックは skip 可"
  exit 0
fi

echo "=== Canonical Python 変更検出 ==="
echo "$CANONICAL_TOUCHED"
```

### 2. ONNX グラフ I/O 変更なら別 skill に委譲

```bash
# /check-runtime-parity が担う領域は skip して責務分離
ONNX_IO_CHANGE=$(git diff origin/dev...HEAD -- \
  src/python/piper_train/export_onnx.py \
  src/python/piper_train/vits/models.py | \
  grep -E '^[+-].*(speaker_embedding|prosody_features|language_id|input_names|output_names)' || true)

if [ -n "$ONNX_IO_CHANGE" ]; then
  echo "WARNING: ONNX I/O 変更を検出。 /check-runtime-parity も併用すること"
fi
```

### 3. 7 ランタイム + 2 docker の touch 状況を一覧表示

```bash
declare -A RUNTIME_PATHS=(
  ["Python runtime"]="src/python_run/piper/"
  ["C# Core"]="src/csharp/PiperPlus.Core/"
  ["C# CLI"]="src/csharp/PiperPlus.Cli/"
  ["Rust core"]="src/rust/piper-core/"
  ["Rust CLI"]="src/rust/piper-cli/"
  ["Rust G2P"]="src/rust/piper-plus-g2p/"
  ["Rust WASM"]="src/rust/piper-wasm/"
  ["Go runtime"]="src/go/piperplus/"
  ["Go CLI"]="src/go/cmd/piper-plus/"
  ["Go G2P"]="src/go/phonemize/"
  ["WASM npm (TTS)"]="src/wasm/openjtalk-web/"
  ["WASM npm (G2P)"]="src/wasm/g2p/"
  ["C API"]="src/cpp/"
  ["iOS SPM"]="Sources/PiperPlus/"
  ["Swift G2P"]="Sources/PiperPlusG2P/"
  ["Kotlin Android"]="android/piper-plus-g2p/"
  ["Docker python-inference"]="docker/python-inference/"
  ["Docker webui"]="docker/webui/"
)

echo ""
echo "=== 7 runtime + 2 docker の touch 状況 ==="
CHANGED_FILES=$(git diff --name-only origin/dev...HEAD)
for label in "${!RUNTIME_PATHS[@]}"; do
  path="${RUNTIME_PATHS[$label]}"
  if echo "$CHANGED_FILES" | grep -q "^${path}"; then
    echo "  [TOUCHED  ] $label  ($path)"
  else
    echo "  [UNTOUCHED] $label  ($path)  <-- 追随確認"
  fi
done
```

### 4. カテゴリ別 grep ヒント (詳細調査)

#### A. ランタイム推論 (`src/python_run/piper/` を変更したとき)

```bash
# 変更された関数名を抽出
git diff origin/dev...HEAD -- src/python_run/piper/voice.py | \
  grep -E '^[+-][[:space:]]*def ' | sort -u

# 同名 / 類似シグネチャを他 runtime で grep
SYMBOL='synthesize'  # ← 上で見つけたシンボル名で置き換え
echo "=== Rust ==="; grep -rn "$SYMBOL" src/rust/piper-core/src/ 2>/dev/null | head
echo "=== Go ==="; grep -rn "$SYMBOL" src/go/piperplus/ 2>/dev/null | head
echo "=== C# ==="; grep -rn "$SYMBOL" src/csharp/PiperPlus.Core/ 2>/dev/null | head
echo "=== WASM ==="; grep -rn "$SYMBOL" src/wasm/openjtalk-web/src/ 2>/dev/null | head
echo "=== C++ ==="; grep -rn "$SYMBOL" src/cpp/ 2>/dev/null | head
```

#### B. G2P / phonemizer (`src/python/g2p/piper_plus_g2p/` を変更したとき)

```bash
# 変更された言語ファイル名を取得
G2P_FILES=$(git diff --name-only origin/dev...HEAD | \
  grep -E '^src/python/g2p/piper_plus_g2p/[a-z_]+\.py$' | \
  xargs -I{} basename {} .py)

for lang in $G2P_FILES; do
  echo "=== $lang phonemizer の 8 runtime 同期確認 ==="
  echo "  Python:    src/python/g2p/piper_plus_g2p/${lang}.py  [canonical]"
  ls -la "src/rust/piper-plus-g2p/src/${lang}.rs"           2>/dev/null && echo "  Rust:      OK" || echo "  Rust:      MISSING"
  ls -la "src/go/phonemize/${lang}.go"                       2>/dev/null && echo "  Go:        OK" || echo "  Go:        MISSING"
  ls -la "src/csharp/PiperPlus.Core/Phonemize/"              2>/dev/null | grep -i "$lang" || echo "  C#:        要確認"
  ls -la "src/wasm/g2p/src/${lang}"                          2>/dev/null && echo "  WASM:      OK" || echo "  WASM:      MISSING"
  ls -la "src/cpp/${lang}_phonemize.cpp"                     2>/dev/null && echo "  C++:       OK" || echo "  C++:       MISSING"
  ls -la "android/piper-plus-g2p/src/main/"                  2>/dev/null | grep -i "$lang" || echo "  Kotlin:    要確認"
  ls -la "Sources/PiperPlusG2P/"                             2>/dev/null | grep -i "$lang" || echo "  Swift:     要確認"
done
```

#### C. モデルエクスポート / 学習周辺 (`src/python/piper_train/` の非 ONNX-I/O 変更)

```bash
# 例: infer_onnx.py の chunking / scaling ロジックを変更したとき、
# 同じロジックが他 runtime にも存在するかを確認
git diff origin/dev...HEAD -- src/python/piper_train/infer_onnx.py | \
  grep -E '^\+' | grep -iE '(scale|chunk|silence|split|trim)' | head
```

### 5. CLI / config / schema の version field 変更チェック

`docs/spec/*.toml` 内の `version` / `schema_version` を bump したかを確認:

```bash
SPEC_VERSION_CHANGE=$(git diff origin/dev...HEAD -- 'docs/spec/*.toml' | \
  grep -E '^[+-].*(version|schema_version) *=' || true)

if [ -n "$SPEC_VERSION_CHANGE" ]; then
  echo "=== Spec version 変更検出 — 影響度 High の可能性 ==="
  echo "$SPEC_VERSION_CHANGE"
  echo ""
  echo "対応する sync gate を必ず手動実行:"
  echo "  uv run python scripts/check_phoneme_set_version.py"
  echo "  uv run python scripts/check_language_id_map_contract.py"
  echo "  uv run python scripts/check_dictionary_versions.py"
fi
```

### 6. 既存 sync gate を手動実行 (影響度 Medium 以上)

該当する canonical 変更ごとに、 対応する sync gate を **PR 提出前に local で**
通しておく (CI で気付くと cycle of shame):

```bash
# 全 sync gate を一気に回す (推奨)
uv run python scripts/check_loanword_consistency.py
uv run python scripts/check_loanword_forward_compat.py
uv run python scripts/check_pua_consistency.py
uv run python scripts/check_dictionary_consistency.py
uv run python scripts/check_dictionary_versions.py
uv run python scripts/check_cli_flag_parity.py
uv run python scripts/check_phoneme_set_version.py
uv run python scripts/check_language_id_map_contract.py
uv run python scripts/check_inference_input_contract.py
uv run python scripts/check_short_text_contract.py
uv run python scripts/check_text_splitter_contract.py
uv run python scripts/check_streaming_api_contract.py
uv run python scripts/check_ssml_contract.py
uv run python scripts/check_speaker_encoder_contract.py
uv run python scripts/check_audio_format_contract.py
uv run python scripts/check_swift_g2p_contract.py
uv run python scripts/check_pt_dialect_contract.py
```

該当領域別の gate 早見表:

| Python 変更箇所 | 走らせるべき gate |
|---|---|
| `chinese.py` (loanword 関連) | `check_loanword_consistency.py` + `check_loanword_forward_compat.py` |
| `phonemize/` の PUA テーブル | `check_pua_consistency.py` |
| 言語コード追加・変更 | `check_language_id_map_contract.py` |
| 辞書フォーマット変更 | `check_dictionary_consistency.py` + `check_dictionary_versions.py` |
| 新規 CLI flag 追加 | `check_cli_flag_parity.py` |
| SSML 機能拡張 | `check_ssml_contract.py` |
| `text_splitter.py` 変更 | `check_text_splitter_contract.py` |
| streaming API 変更 | `check_streaming_api_contract.py` |
| `speaker_encoder/` 変更 | `check_speaker_encoder_contract.py` |
| 短テキスト戦略変更 | `check_short_text_contract.py` |
| PT BR/EU 切替変更 | `check_pt_dialect_contract.py` |
| Swift G2P 変更 | `check_swift_g2p_contract.py` |

### 7. Docker image の追随確認 (PR #443 の盲点)

`src/python_run/piper/` 変更時は、 ベースとなる docker image 2 個も touch されて
いるかを確認 (Python ランタイムを wheel として再 install するだけで OK な場合と、
recipe を変える必要がある場合がある):

```bash
echo "=== Docker image の touch 状況 ==="
for d in docker/python-inference docker/webui; do
  if git diff --name-only origin/dev...HEAD | grep -q "^${d}/"; then
    echo "  [TOUCHED  ] $d"
  else
    echo "  [UNTOUCHED] $d  ← Python wheel の bump で十分か確認"
  fi
done

# requirements.txt / pyproject 内の piper-plus pin が古いか確認
grep -rn 'piper-plus' docker/python-inference/ docker/webui/ 2>/dev/null | \
  grep -E '(==|>=|~=)' | head
```

## 確認すべき事項 (チェックリスト)

PR 提出前にメンタルチェック:

- [ ] canonical Python の変更カテゴリ (A: 推論 / B: G2P / C: 学習) を分類した
- [ ] 影響度 (Low / Medium / High) を判定した
- [ ] Low 以外なら他 runtime の touch 状況を `git diff --name-only` で確認した
- [ ] Medium なら Rust / Go / C# を同 PR で更新 (or follow-up issue 化)
- [ ] High なら全 7 runtime + 2 docker を同 PR で更新 (or release blocker 立て)
- [ ] 該当する `scripts/check_*.py` sync gate を local で pass
- [ ] `docs/spec/*.toml` の version bump が必要か検討した
- [ ] PR description に 「Python canonical + N 他ランタイム追随」 を明記
- [ ] follow-up issue がある場合は PR description にリンク
- [ ] ONNX I/O 変更なら `/check-runtime-parity` も併用した
- [ ] 新規データファイル追加なら `/check-new-runtime-asset` も併用した

## 影響度別 quick action

### Low (内部リファクタ・テスト追加・docstring)

```text
PR description に以下を明記:
  > Python のみ変更。 他 runtime への追随不要 (内部リファクタ)。
  > /check-cross-runtime: skip (Low)
```

### Medium (新機能・CLI flag・API field 追加)

1. Rust + Go + C# を **同 PR で実装**
2. WASM / C++ / iOS / Kotlin / Swift G2P は **follow-up issue 化**
3. PR description に follow-up issue link

```bash
# follow-up issue を作る例
gh issue create --title "[follow-up] <feature> を WASM/C++/iOS/Kotlin/Swift に追随" \
  --body "PR #XXX で Python + Rust + Go + C# に実装済み。 残り 5 runtime に追随必要。"
```

### High (config schema / data 形式 / 互換性破壊)

1. **全 7 runtime + 2 docker を同 PR** が原則
2. 不可なら release blocker label を付けて release から外す
3. `docs/spec/*.toml` の version bump
4. `docs/migration/` にマイグレーションガイド追加

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| Python 変更が大きすぎて何が canonical か分からない | `git diff --stat origin/dev...HEAD` で行数の多いファイルから 3 カテゴリ (A/B/C) に分類 |
| 影響度判定に迷う | 「他 runtime に同じバグが潜むか?」 を考える。 Yes なら Medium 以上 |
| sync gate が無い領域を触ってしまった | `scripts/check_dictionary_consistency.py` をテンプレートに新規 gate を作成 (`/check-new-runtime-asset` 参照) |
| 全 runtime 同 PR が大きすぎる | High なら release blocker、 Medium なら Rust/Go/C# だけ同 PR + follow-up issue |
| docker image の wheel pin が古い | `docker/*/requirements.txt` または `pyproject.toml` で `piper-plus==X.Y.Z` を bump |
| CI で sync gate fail | 該当 sync gate の PAIRS / mirror に追加する canonical entry が漏れている可能性 |

## 関連ドキュメント / skill

- 姉妹 skill: [`/check-runtime-parity`](../check-runtime-parity/SKILL.md) — ONNX グラフ I/O 限定
- 姉妹 skill: [`/check-new-runtime-asset`](../check-new-runtime-asset/SKILL.md) — 新規データファイル 7 箇所配布
- 姉妹 skill: [`/check-loanword`](../check-loanword/SKILL.md) — ZH-EN loanword 7 mirror 同期
- 姉妹 skill: [`/check-pua`](../check-pua/SKILL.md) — PUA テーブル / fixture / config 整合
- 仕様: `docs/spec/inference-input-contract.toml`
- 仕様: `docs/spec/short-text-contract.toml`
- 仕様: `docs/spec/text-splitter-contract.toml`
- 仕様: `docs/spec/phoneme-timing-contract.toml`
- マイグレーション: `docs/migration/v1.11-to-v1.12.md`
- memory: `feedback_data_asset_distribution.md` (7 箇所配布の背景)
- PR #391 / PR #443 — Python のみ修正 → N runtime 追随漏れ silent regression の参考事例
- PR #384 — ZH-EN loanword schema 拡張で 5 runtime fail の事例
