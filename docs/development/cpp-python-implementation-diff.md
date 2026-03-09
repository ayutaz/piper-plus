# C++ / Python 実装差分調査レポート

> **調査日**: 2026-03-08（初版）/ 2026-03-09（M1+M1.5完了更新）/ 2026-03-10（M2+M3+M4完了更新）
> **対象ブランチ**: `fix/cpp-python-sync`（PR #229）
> **調査方法**: 15エージェント並行調査 + Docker推論実測比較
> **検証モデル**: `ayousanz/piper-plus-tsukuyomi-chan` (tsukuyomi-wavlm-300epoch.onnx)

---

## 全マイルストーン完了サマリー（2026-03-10）

**全差分が解消済み。全マイルストーン（M1〜M4）完了。** M1（コミット `c251b1d`）およびM1.5（コミット `2997b1b`）により、C++推論パイプラインとPython学習パイプラインの音素化処理が完全に同期された。**全8テストケースで phoneme_ids が完全一致（PASS）** を確認。

- **M1**: 疑問詞マーカー、Nバリアント、プロソディマーク挿入を C++ に実装
- **M1.5**: OpenJTalkフロントエンドを pyopenjtalk-plus（Cライブラリ直接リンク）に統一し、A1/A2/A3値の差異を解消
- **M2**: テスト・ログ整合性を確保。新規テスト58件（Nバリアント38件 + 疑問詞マーカー20件）を追加し全てPASS。prosody_features型テストもint64に修正済み。openjtalk_phonemize_utils.cpp として独立ユーティリティに分離。
- **M3**: インターフェース改善。JSON入力でprosody_featuresをサポート（ProsodyFeatureをpiper.hppに移動、textToAudio/textToWavFileにexternalProsodyパラメータ追加）。カスタム辞書の日本語単語境界をマルチバイトUTF-8対応に修正。
- **M4**: Docker回帰テスト。`regression_test.sh`（8テストケース、ハードコード期待値）を作成し8/8 PASS。CI（`docker-test.yml`）にC++ユニットテストジョブを追加。

---

## エグゼクティブサマリー

~~Python（学習・前処理）とC++（推論）の実装差分を包括的に調査した結果、**C++推論パイプラインがPython側の最新機能に追従できていない箇所が複数発見された**。~~ M1+M1.5の実装により、**Critical差分は全て解消済み**。Docker推論による実測比較（8テストケース）で**全テストケースでphoneme_ids列が完全一致**していることを確認した。

### 対応状況（2026-03-09更新）

| 重要度 | 差分 | 状態 | 備考 |
|--------|------|:---:|------|
| ~~**Critical**~~ | ~~疑問詞マーカー未実装~~ | ✅ 解消 | M1で実装済み（`c251b1d`） |
| ~~**Critical**~~ | ~~Nバリアント未実装~~ | ✅ 解消 | M1で実装済み（`c251b1d`） |
| ~~**Critical**~~ | ~~プロソディマーク未実装~~ | ✅ 解消 | M1で実装済み（`c251b1d`） |
| ~~**Critical**~~ | ~~OpenJTalkフロントエンド差異~~ | ✅ 解消 | M1.5で pyopenjtalk-plus に統一（`2997b1b`） |
| ~~**Medium**~~ | ~~JSON入力で prosody_features 未サポート~~ | ✅ 解消 | M3で実装済み |
| ~~**Medium**~~ | ~~カスタム辞書の日本語単語境界~~ | ✅ 解消 | M3で実装済み |
| ~~**Low**~~ | ~~puaToPhoneme未登録~~ | ✅ 解消 | M1で実装済み（`c251b1d`） |
| ~~**Info**~~ | ~~prosody_features テンソル型の整合性~~ | ✅ 解消 | テスト修正済み（`31b586c`） |

### ~~新規発見: OpenJTalkフロントエンド差異~~ → ✅ M1.5で解消済み

~~M1実装後のDockerテストで、音素化ロジック自体は正しいにもかかわらず、**OpenJTalkバイナリ（C++）とpyopenjtalk（Python）で異なるA1/A2/A3値が返される**ことが判明:~~

| テキスト | 差異の種類 | 詳細 | 状態 |
|---------|-----------|------|:---:|
| そうなの？。 | ~~A1値オフセット~~ | ~~C++: a1=-2開始, Python: a1=0開始 → `]`位置ずれ~~ | ✅ 解消 |
| あんないします。 | ~~アクセント句分割~~ | ~~C++: 2句(4+3モーラ), Python: 1句(7モーラ) → 余分な`[`~~ | ✅ 解消 |

> **解決方法**: M1.5（コミット `2997b1b`）で pyopenjtalk-plus の open_jtalk フォーク（Cライブラリ）を直接リンクし、フロントエンドを統一。`apply_original_rule_before_chaining` + `modify_acc_after_chaining` の適用により、Python と完全同一の A1/A2/A3 値を出力するようになった。

---

## 1. 音素化パイプラインの差分（最重要）

### 1.1 疑問詞マーカー（Issue #204）— ✅ M1で実装済み

**Python側の実装** (`japanese.py:40-78`):

テキスト末尾のパターンから5種類の疑問詞を区別:

| マーカー | ID | PUA | テキストパターン |
|---------|-----|-----|----------------|
| `$` (平叙文) | 2 | なし | 疑問符なし |
| `?` (汎用疑問) | 3 | なし | `?`, `？` |
| `?!` (強調疑問) | 4 | U+E016 | `?!`, `！？`, `？！` |
| `?.` (平叙疑問) | 5 | U+E017 | `?.`, `。？`, `？。` |
| `?~` (確認疑問) | 6 | U+E018 | `?~`, `～？`, `？～` |

**C++側の状況**: ✅ M1（コミット `c251b1d`）で実装完了。`phonemeToPua` マップに `?!`, `?.`, `?~` のエントリを追加済み。テキスト末尾の句読点パターン解析ロジック（Python `_get_question_type()` と同等）を実装済み。全5種類の疑問詞タイプを正しく分類。

### 1.2 文脈依存「ん」バリアント（Issue #207）— ✅ M1で実装済み

**Python側の実装** (`japanese.py:85-130`):

`_apply_n_phoneme_rules()` で後続音素に基づき `N` を4種に分類:

| バリアント | ID | PUA | 条件（後続音素） |
|-----------|-----|-----|----------------|
| `N_m` | 26 | U+E019 | m, my, b, by, p, py |
| `N_n` | 27 | U+E01A | n, ny, t, ty, d, dy, ts, ch |
| `N_ng` | 28 | U+E01B | k, ky, kw, g, gy, gw |
| `N_uvular` | 29 | U+E01C | 語末 / 母音 / その他 |

**C++側の状況**: ✅ M1（コミット `c251b1d`）で実装完了。`phonemeToPua` マップに `N_m`, `N_n`, `N_ng`, `N_uvular` のエントリを追加済み。後続音素に基づくN分類ロジックを実装済み。

### 1.3 プロソディマーク挿入（栗原方式）— ✅ M1で実装済み

**Python側の実装** (`japanese.py:222-240`):

OpenJTalkラベルのA2値を先読みして3種のプロソディマークを挿入:

| 条件 | マーク | ID | 意味 |
|------|--------|-----|------|
| `a1 == 0 and a2_next == a2 + 1` | `]` | 9 | アクセント核（ピッチ下降点） |
| `a2 == a3 and a2_next == 1` | `#` | 7 | アクセント句境界 |
| `a2 == 1 and a2_next == 2` | `[` | 8 | ピッチ上昇点（句頭） |

**C++側の状況**: ✅ M1（コミット `c251b1d`）で実装完了。A2値の先読みによるプロソディマーク挿入ロジックを実装済み。挿入されたマークの prosody_features は `[0, 0, 0]` として処理。全8テストケースで Python と同一のプロソディマーク出力を確認。

---

## 2. PUA マッピングの差分

### 2.1 完全な対応表

| PUA | トークン | カテゴリ | C++ phonemeToPua | Python FIXED_PUA | C++ phoneme_parser |
|-----|---------|---------|:---:|:---:|:---:|
| U+E000 | `a:` | 長母音 | ✅ | ✅ | ✅ |
| U+E001 | `i:` | 長母音 | ✅ | ✅ | ✅ |
| U+E002 | `u:` | 長母音 | ✅ | ✅ | ✅ |
| U+E003 | `e:` | 長母音 | ✅ | ✅ | ✅ |
| U+E004 | `o:` | 長母音 | ✅ | ✅ | ✅ |
| U+E005 | `cl` | 促音 | ✅ | ✅ | ✅ |
| U+E006 | `ky` | 口蓋化子音 | ✅ | ✅ | ✅ |
| U+E007 | `kw` | 口蓋化子音 | ✅ | ✅ | ✅ |
| U+E008 | `gy` | 口蓋化子音 | ✅ | ✅ | ✅ |
| U+E009 | `gw` | 口蓋化子音 | ✅ | ✅ | ✅ |
| U+E00A | `ty` | 口蓋化子音 | ✅ | ✅ | ✅ |
| U+E00B | `dy` | 口蓋化子音 | ✅ | ✅ | ✅ |
| U+E00C | `py` | 口蓋化子音 | ✅ | ✅ | ✅ |
| U+E00D | `by` | 口蓋化子音 | ✅ | ✅ | ✅ |
| U+E00E | `ch` | 破擦音 | ✅ | ✅ | ✅ |
| U+E00F | `ts` | 破擦音 | ✅ | ✅ | ✅ |
| U+E010 | `sh` | 摩擦音 | ✅ | ✅ | ✅ |
| U+E011 | `zy` | 口蓋化有声破擦音 | ✅ | ✅ | ✅ |
| U+E012 | `hy` | 口蓋化摩擦音 | ✅ | ✅ | ✅ |
| U+E013 | `ny` | 口蓋化鼻音 | ✅ | ✅ | ✅ |
| U+E014 | `my` | 口蓋化鼻音 | ✅ | ✅ | ✅ |
| U+E015 | `ry` | 口蓋化流音 | ✅ | ✅ | ✅ |
| U+E016 | `?!` | 強調疑問マーカー | ✅ | ✅ | ✅ |
| U+E017 | `?.` | 平叙疑問マーカー | ✅ | ✅ | ✅ |
| U+E018 | `?~` | 確認疑問マーカー | ✅ | ✅ | ✅ |
| U+E019 | `N_m` | 両唇音同化 | ✅ | ✅ | ✅ |
| U+E01A | `N_n` | 歯茎音同化 | ✅ | ✅ | ✅ |
| U+E01B | `N_ng` | 軟口蓋音同化 | ✅ | ✅ | ✅ |
| U+E01C | `N_uvular` | 口蓋垂音 | ✅ | ✅ | ✅ |

### 2.2 差分の構造

```
Python (学習時)        C++ (推論時)
─────────────         ──────────────
token_mapper.py       openjtalk_phonemize.cpp
 FIXED_PUA_MAPPING      phonemeToPua
 29エントリ              29エントリ  ← ✅ M1で全エントリ追加済み
 (0xE000-0xE01C)        (0xE000-0xE01C)

phoneme_parser.cpp は 29エントリ全対応（--raw-phonemes 入力時のみ有効）
```

**結論**: ✅ `phonemeToPua` と `phoneme_parser` の両方が全29エントリに対応済み。テキスト→音素の主要パイプラインでも全PUA (0xE000-0xE01C) を正しく処理する。

---

## 3. ONNX 推論パイプラインの差分

### 3.1 入力テンソル構成

| 入力名 | 型 | 形状 | C++ | Python | 備考 |
|--------|-----|------|:---:|:---:|------|
| `input` | int64 | `[1, N]` | ✅ | ✅ | phoneme_ids |
| `input_lengths` | int64 | `[1]` | ✅ | ✅ | |
| `scales` | float32 | `[3]` | ✅ | ✅ | `[noise_scale, length_scale, noise_w]` |
| `sid` | int64 | `[1]` | ✅ | ✅ | マルチスピーカー時のみ |
| `prosody_features` | int64 | `[1, N, 3]` | ✅ | ✅ | prosody有効時のみ |

**入力テンソル構成は完全一致。** 両方とも ONNX モデルの入力ノード名を動的に検出し、必要な入力のみを構築する。

### 3.2 scales パラメータのデフォルト値

| パラメータ | C++ デフォルト | Python デフォルト | 一致 |
|-----------|:---:|:---:|:---:|
| noise_scale | 0.667 | 0.667 | ✅ |
| length_scale | 1.0 | 1.0 | ✅ |
| noise_w | 0.8 | 0.8 | ✅ |

### 3.3 prosody_features テンソル型

| 項目 | C++ | Python | 状態 |
|------|-----|--------|------|
| テンソル型 | int64 | int64 | ✅ 一致 |
| ONNX内部変換 | なし（モデルのCastノードで吸収） | なし（同上） | ✅ |
| ゼロフォールバック | 全ゼロ配列 | `np.zeros(...)` | ✅ |

~~**注意**: `test_prosody_inference.cpp` では `float32` でテストしているが、実際の `piper.cpp` の推論コードでは `int64` として渡している。~~ ✅ コミット `31b586c` で `test_prosody_inference.cpp` の型を `float` → `int64` に修正済み。テストと実装の型が一致している。

### 3.4 音声後処理

| 処理 | C++ | Python |
|------|-----|--------|
| 正規化方式 | `maxAudioValue` でスケーリング → MAX_WAV_VALUE (32767) | ピーク正規化 → 32767 |
| クリッピング | int16 クランプ | `np.clip(-32767, 32767)` |
| NEON最適化 | ARM64 対応あり | なし |

基本的な処理は同等。

---

## 4. BOS/EOS/パディング処理の差分

### 4.1 日本語

| 処理 | C++ | Python | 一致 |
|------|-----|--------|:---:|
| BOS挿入 | `sil` → 音素列には含めず、`phonemes_to_ids` でBOS(1)追加 | `sil` → `^`(BOS) としてトークン列に含む | ✅ 結果一致 |
| EOS挿入 | `sil` → 疑問詞タイプに応じて `$`/`?`/`?!`/`?.`/`?~` を生成 | `sil` → `$`/`?`/`?!`/`?.`/`?~` としてトークン列に含む | ✅ 結果一致 |
| interspersePad | `false` (OpenJTalk) | なし（日本語はpost_process_idsがno-op） | ✅ 結果一致 |

✅ M1で疑問詞タイプに応じた EOS トークン（ID 2-6）の分類を実装済み。C++ と Python で同一の EOS が生成される。

### 4.2 英語

| 処理 | C++ | Python | 一致 |
|------|-----|--------|:---:|
| BOS挿入 | `phonemes_to_ids` で BOS(1) 追加 | `post_process_ids` で `^` + pad 追加 | ⚠️ 要確認 |
| EOS挿入 | `phonemes_to_ids` で EOS(2) 追加 | `post_process_ids` で `$` 追加 | ⚠️ 要確認 |
| interspersePad | `true` (eSpeak) | `post_process_ids` で各音素間にpad挿入 | ⚠️ 要確認 |

---

## 5. CLI / インターフェースの差分

| 機能 | C++ (main.cpp) | Python (infer_onnx.py) |
|------|----------------|----------------------|
| テキスト直接入力 | stdin のみ | `--text` オプションあり |
| phoneme_ids 直接入力 | `--raw-phonemes`（スペース区切り文字列） | JSONL内 `phoneme_ids` 配列 |
| prosody_features 外部入力 | **未サポート**（内部自動生成のみ） | JSONL内 `prosody_features` |
| JSON入力フィールド | `text`, `speaker_id`, `speaker`, `output_file` | `phoneme_ids`, `prosody_features`, `speaker_id` |
| 言語指定 | モデル設定から自動判定 | `--language` オプション |
| ストリーミング | `--streaming` + `--output_raw` | なし |
| カスタム辞書 | `--custom-dict` | 内部呼び出しのみ |
| phonemeタイミング出力 | `--output-timing` (JSON/TSV) | なし |
| CUDA指定 | `--use-cuda`, `--gpu-device-id` | なし（CPU固定） |

---

## 6. カスタム辞書の差分

| 項目 | C++ | Python |
|------|-----|--------|
| JSON解析 | 自前の正規表現パーサー | `json.load()` 標準ライブラリ |
| デフォルト辞書読込 | 4ファイル固定名リスト | `*.json` globで全ファイル |
| 単語境界 | 常に `\b` を使用 | 日本語: 境界なし / 英語: look-around |
| **日本語対応** | **`\b` は日本語で問題あり（潜在バグ）** | 日本語文字は `ord(c) > 127` で検出し適切に処理 |

---

## 7. 修正推奨事項

### Priority 1: Critical（モデル品質に直接影響）— ✅ 全て完了

#### 7.1 疑問詞マーカーの実装 — ✅ 完了（M1: `c251b1d`）

~~**対象ファイル**: `src/cpp/openjtalk_phonemize.cpp`~~

~~必要な変更:~~
1. ~~`phonemeToPua` マップに3エントリ追加~~
2. ~~テキスト末尾の句読点パターン解析ロジックを実装~~
3. ~~末尾 `sil` の変換時に疑問詞タイプに応じたトークンを生成~~

#### 7.2 文脈依存Nバリアントの実装 — ✅ 完了（M1: `c251b1d`）

~~**対象ファイル**: `src/cpp/openjtalk_phonemize.cpp`~~

~~必要な変更:~~
1. ~~`phonemeToPua` マップに4エントリ追加~~
2. ~~`_apply_n_phoneme_rules()` と同等の後続音素に基づくN分類ロジックを実装~~
3. ~~分類ルール~~

#### 7.3 プロソディマーク挿入の実装 — ✅ 完了（M1: `c251b1d`）

~~**対象ファイル**: `src/cpp/openjtalk_phonemize.cpp`~~

~~**実測で未実装が確認済み。** Python `japanese.py:222-240` の栗原方式ロジックを移植する必要がある~~

### Priority 2: High — ✅ 全て完了

#### 7.4 puaToPhoneme ログ表示用マップの更新 — ✅ 完了（M1: `c251b1d`）

~~**対象ファイル**: `src/cpp/piper.cpp`~~

~~`puaToPhoneme` マップに7エントリ追加~~

#### 7.5 テストコードの prosody_features 型修正 — ✅ 完了（`31b586c`）

~~**対象ファイル**: `src/cpp/tests/test_prosody_inference.cpp`~~

~~`ProsodyTensorDataType` テストが float32 を期待しているが、実際のパイプラインは int64 を使用。~~ コミット `31b586c` で int64 に修正済み。

### Priority 3: Medium — 🔲 M3スコープ

#### 7.6 JSON入力で prosody_features をサポート

**対象ファイル**: `src/cpp/main.cpp`

`--json-input` モードで `prosody_features` フィールドをパースし、テキスト自動生成の代わりに使用する機能を追加。

#### 7.7 カスタム辞書の日本語単語境界修正

**対象ファイル**: `src/cpp/custom_dictionary.cpp`

日本語文字（マルチバイト）を含む辞書エントリに対して、`\b` の代わりに適切な境界パターンを使用。

---

## 8. 音素ID体系の完全リスト（Python基準）

### 8.1 日本語（65トークン、ID 0-64）

| ID | トークン | PUA | カテゴリ |
|----|---------|-----|---------|
| 0 | `_` | - | パディング/ポーズ |
| 1 | `^` | - | BOS |
| 2 | `$` | - | EOS（平叙） |
| 3 | `?` | - | EOS（疑問） |
| 4 | `?!` | U+E016 | EOS（強調疑問） |
| 5 | `?.` | U+E017 | EOS（平叙疑問） |
| 6 | `?~` | U+E018 | EOS（確認疑問） |
| 7 | `#` | - | アクセント句境界 |
| 8 | `[` | - | ピッチ上昇 |
| 9 | `]` | - | ピッチ下降 |
| 10-14 | `a`-`o` | - | 有声母音 |
| 15-19 | `A`-`O` | - | 無声母音 |
| 20-24 | `a:`-`o:` | U+E000-E004 | 長母音 |
| 25 | `N` | - | 撥音（汎用） |
| 26-29 | `N_m`-`N_uvular` | U+E019-E01C | 撥音バリアント |
| 30 | `cl` | U+E005 | 促音 |
| 31 | `q` | - | 促音（別ラベル） |
| 32-64 | 子音群 | 各種PUA | k, ky, kw, g, gy, ... |

### 8.2 C++側の対応状況

- **ID 0-64**: ✅ 全ID が C++ 側で生成可能（M1で完全対応）
- ~~**ID 4-6** (`?!`, `?.`, `?~`): ❌ C++未実装~~ → ✅ M1で実装済み
- ~~**ID 26-29** (`N_m`, `N_n`, `N_ng`, `N_uvular`): ❌ C++未実装~~ → ✅ M1で実装済み

---

## 9. アーキテクチャ比較図

### 9.1 Python 推論パイプライン (infer_onnx.py)

```
テキスト入力
  │
  ├── [カスタム辞書適用] (optional)
  │
  ├── pyopenjtalk.extract_fullcontext(text)
  │     └── フルコンテキストラベル取得
  │
  ├── 音素抽出 + A1/A2/A3抽出
  │     ├── sil → ^(BOS) / $/?/?!/?./?(EOS)
  │     ├── pau → _
  │     └── プロソディマーク挿入 ([, ], #)  ← 栗原方式
  │
  ├── _apply_n_phoneme_rules()  ← N → N_m/N_n/N_ng/N_uvular
  │
  ├── map_sequence()  ← 多文字トークン → PUA文字
  │
  ├── phoneme_id_map で ID変換
  │
  ├── post_process_ids()  ← 英語のみBOS/EOS/PAD挿入
  │
  └── ONNX Runtime 推論
        input, input_lengths, scales, [sid], [prosody_features]
```

### 9.2 C++ 推論パイプライン (piper.cpp) — ✅ M1+M1.5更新済み

```
テキスト入力 (stdin)
  │
  ├── [カスタム辞書適用] (optional)
  │
  ├── openjtalk_text_to_phonemes_with_prosody()
  │     ├── pyopenjtalk-plus open_jtalk API 直接呼び出し  ← ✅ M1.5: system()廃止
  │     │     ├── apply_original_rule_before_chaining      ← ✅ M1.5: Python同等の前処理
  │     │     └── modify_acc_after_chaining                ← ✅ M1.5: Python同等の後処理
  │     ├── フルコンテキストラベルパース
  │     ├── 音素抽出 + A1/A2/A3抽出
  │     ├── プロソディマーク挿入 ([, ], #)  ← ✅ M1: 栗原方式実装済み
  │     └── PUA変換 (phonemeToPua: 29エントリ)  ← ✅ M1: 全エントリ対応
  │
  ├── ✅ Nバリアント分類  ← M1: N → N_m/N_n/N_ng/N_uvular
  │
  ├── ✅ 疑問詞マーカー分類  ← M1: $/?/?!/?./? 5種対応
  │
  ├── phonemes_to_ids()  (piper-phonemize ライブラリ)
  │     └── phonemeIdMap + interspersePad + BOS/EOS
  │
  └── ONNX Runtime 推論
        input, input_lengths, scales, [sid], [prosody_features]
```

---

## 10. ONNXモデルの入出力仕様（リファレンス）

### 入力

| 名前 | 型 | 形状 | dynamic_axes | 条件 |
|------|-----|------|-------------|------|
| `input` | int64 | `[B, T]` | B, T | 常に |
| `input_lengths` | int64 | `[B]` | B | 常に |
| `scales` | float32 | `[3]` | なし | 常に |
| `sid` | int64 | `[B]` | B | num_speakers > 1 |
| `prosody_features` | int64 | `[B, T, 3]` | B, T | prosody_dim > 0 |

### 出力

| 名前 | 型 | 形状 | 説明 |
|------|-----|------|------|
| `output` | float32 | `[B, 1, time]` | 音声波形 |
| `durations` | float32 | `[B, T]` | 各音素のデュレーション（フレーム数） |

### モデル内部処理

```
input (phoneme_ids) → TextEncoder → x, m_p, logs_p
prosody_features → Linear(3→16) → prosody_proj
x + prosody_proj → Duration Predictor → logw → w
w × length_scale → alignment → attn
attn × (m_p, logs_p) → z_p
z_p → Flow(reverse) → z
z → Generator → audio
```

---

## 11. Docker 推論比較結果（実測データ）

> **検証環境**: Docker Desktop v29.2.1 (Windows)
> **モデル**: `ayousanz/piper-plus-tsukuyomi-chan` (`tsukuyomi-wavlm-300epoch.onnx`, 61MB)
> **C++イメージ**: `piper-cpp-inference:test`
> **Pythonイメージ**: `piper-inference:latest`

### 11.1 テストケース別比較

> **注記**: 以下の「M1実装前（参考）」列は初版調査（2026-03-08）の C++ 結果を履歴として保存したもの。「M1.5実装後」列が最新の C++ 結果であり、全テストで Python と完全一致。

#### テスト1: 「こんにちは、今日は良い天気ですね。」（基本文） — ✅ PASS

| 項目 | Python | C++ (M1.5実装後) | M1実装前（参考） |
|------|--------|-----------------|-----------------|
| トークン数 | **38** | **38** | ~~31~~ |
| Nバリアント | N_n(ID=27), N_ng(ID=28) | N_n(ID=27), N_ng(ID=28) | ~~N(ID=25), N(ID=25)~~ |
| プロソディマーク | `[`, `]` 計7個 | `[`, `]` 計7個 | ~~なし~~ |
| EOS | `$`(ID=2) | `$`(ID=2) | `$`(ID=2) |
| phoneme_ids 一致 | — | **✅ 完全一致** | ~~❌ 不一致~~ |

#### テスト2: 「本当ですか？」（汎用疑問文） — ✅ PASS

| 項目 | Python | C++ (M1.5実装後) | M1実装前（参考） |
|------|--------|-----------------|-----------------|
| トークン数 | **16** | **16** | ~~14~~ |
| Nバリアント | N_n(ID=27) | N_n(ID=27) | ~~N(ID=25)~~ |
| プロソディマーク | `[` x 1 | `[` x 1 | ~~なし~~ |
| EOS | `?`(ID=3) | `?`(ID=3) | ~~`$`(ID=2)~~ |
| phoneme_ids 一致 | — | **✅ 完全一致** | ~~❌ 不一致~~ |

#### テスト3: 「本当?!」（強調疑問） — ✅ PASS

| 項目 | Python | C++ (M1.5実装後) | M1実装前（参考） |
|------|--------|-----------------|-----------------|
| トークン数 | **9** | **9** | ~~8~~ |
| Nバリアント | N_n(ID=27) | N_n(ID=27) | ~~N(ID=25)~~ |
| EOS | **`?!`(ID=4)** | **`?!`(ID=4)** | ~~`$`(ID=2)~~ |
| phoneme_ids 一致 | — | **✅ 完全一致** | ~~❌ 不一致~~ |

#### テスト4: 「そうなの？。」（平叙疑問） — ✅ PASS

| 項目 | Python | C++ (M1.5実装後) | M1実装前（参考） |
|------|--------|-----------------|-----------------|
| トークン数 | **11** | **11** | ~~9~~ |
| プロソディマーク | `]` x 1, `[` x 1 | `]` x 1, `[` x 1 | ~~なし~~ |
| EOS | **`?.`(ID=5)** | **`?.`(ID=5)** | ~~`$`(ID=2)~~ |
| phoneme_ids 一致 | — | **✅ 完全一致** | ~~❌ 不一致~~ |

#### テスト5: 「さんぽに行きましょう。」（N_m: 両唇音同化） — ✅ PASS

| 項目 | Python | C++ (M1.5実装後) | M1実装前（参考） |
|------|--------|-----------------|-----------------|
| トークン数 | **21** | **21** | ~~17~~ |
| Nバリアント | **N_m(ID=26)** | **N_m(ID=26)** | ~~N(ID=25)~~ |
| プロソディマーク | `]` x 1, `[` x 2 | `]` x 1, `[` x 2 | ~~なし~~ |
| phoneme_ids 一致 | — | **✅ 完全一致** | ~~❌ 不一致~~ |

#### テスト6: 「あんないします。」（N_n: 歯茎音同化） — ✅ PASS

| 項目 | Python | C++ (M1.5実装後) | M1実装前（参考） |
|------|--------|-----------------|-----------------|
| トークン数 | **15** | **15** | ~~13~~ |
| Nバリアント | **N_n(ID=27)** | **N_n(ID=27)** | ~~N(ID=25)~~ |
| プロソディマーク | `[` x 1, `]` x 1 | `[` x 1, `]` x 1 | ~~なし~~ |
| phoneme_ids 一致 | — | **✅ 完全一致** | ~~❌ 不一致~~ |

#### テスト7: 「ぎんこうに行きます。」（N_ng: 軟口蓋音同化） — ✅ PASS

| 項目 | Python | C++ (M1.5実装後) | M1実装前（参考） |
|------|--------|-----------------|-----------------|
| トークン数 | **20** | **20** | ~~17~~ |
| Nバリアント | **N_ng(ID=28)** | **N_ng(ID=28)** | ~~N(ID=25)~~ |
| プロソディマーク | `[` x 2 | `[` x 2 | ~~なし~~ |
| phoneme_ids 一致 | — | **✅ 完全一致** | ~~❌ 不一致~~ |

#### テスト8: 「本を読みました。」（N_uvular: 口蓋垂音） — ✅ PASS

| 項目 | Python | C++ (M1.5実装後) | M1実装前（参考） |
|------|--------|-----------------|-----------------|
| トークン数 | **20** | **20** | ~~16~~ |
| Nバリアント | **N_uvular(ID=29)** | **N_uvular(ID=29)** | ~~N(ID=25)~~ |
| プロソディマーク | `]` x 1, `[` x 2 | `]` x 1, `[` x 2 | ~~なし~~ |
| phoneme_ids 一致 | — | **✅ 完全一致** | ~~❌ 不一致~~ |

### 11.2 prosody_features 比較（テスト1: 「こんにちは...」）

| 位置 | Python (phoneme) | Python A1/A2/A3 | C++ (phoneme) | C++ A1/A2/A3 | 一致 |
|------|-----------------|-----------------|---------------|-------------|:---:|
| [0] | `^` (BOS) | [0,0,0] | BOS | [0,0,0] | ✅ |
| [1] | `k` | [-4,1,5] | `k` | [-4,1,5] | ✅ |
| [2] | `o` | [-4,1,5] | `o` | [-4,1,5] | ✅ |
| [3] | `[` (プロソディマーク) | [0,0,0] | `[` (プロソディマーク) | [0,0,0] | ✅ |
| [4] | `N_n` (0xE01A) | [-3,2,4] | `N_n` (0xE01A) | [-3,2,4] | ✅ |
| [5] | `n` | [-2,3,3] | `n` | [-2,3,3] | ✅ |

✅ M1.5以降、prosody_features の A1/A2/A3 値、プロソディマーク、Nバリアント、疑問詞EOS の全てが C++/Python で完全一致。

### 11.3 差分の定量サマリー

| 差分カテゴリ | M1.5実装後 | M1実装前（参考） |
|-------------|:----------:|:----------------:|
| Nバリアント | ✅ 0/8 不一致 (0%) | ~~8/8 (100%)~~ |
| プロソディマーク | ✅ 0/8 不一致 (0%) | ~~8/8 (100%)~~ |
| 疑問詞マーカー | ✅ 0/8 不一致 (0%) | ~~3/8 (37.5%)~~ |
| トークン数の差 | ✅ 0/8 不一致 (0%) | ~~8/8 (平均 -3.1 tokens)~~ |
| **phoneme_ids 完全一致** | **✅ 8/8 PASS (100%)** | ~~0/8 (0%)~~ |

---

## 付録A: 調査対象ファイル一覧

### C++ ソース

| ファイル | 行数 | 調査タスク |
|---------|------|----------|
| `src/cpp/piper.hpp` | ~116 | #1 |
| `src/cpp/piper.cpp` | ~1100 | #1 |
| `src/cpp/openjtalk_phonemize.hpp` | ~40 | #2 |
| `src/cpp/openjtalk_phonemize.cpp` | ~200 | #2 |
| `src/cpp/phoneme_parser.hpp` | - | #3 |
| `src/cpp/phoneme_parser.cpp` | - | #3 |
| `src/cpp/main.cpp` | - | #15 |
| `src/cpp/custom_dictionary.hpp` | - | #10 |
| `src/cpp/custom_dictionary.cpp` | - | #10 |
| `src/cpp/openjtalk_wrapper.h` | - | #12 |
| `src/cpp/openjtalk_wrapper_functions.h` | - | #12 |
| `src/cpp/openjtalk_api.h` | - | #12 |
| `src/cpp/openjtalk_optimized.h` | - | #12 |
| `src/cpp/openjtalk_security.h` | - | #12 |
| `src/cpp/openjtalk_error.h` | - | #12 |
| `src/cpp/openjtalk_dictionary_manager.h` | - | #12 |
| `src/cpp/tests/` (9ファイル) | - | #11 |

### Python ソース

| ファイル | 行数 | 調査タスク |
|---------|------|----------|
| `src/python/piper_train/phonemize/japanese.py` | ~370 | #4 |
| `src/python/piper_train/phonemize/jp_id_map.py` | ~110 | #5 |
| `src/python/piper_train/phonemize/token_mapper.py` | ~80 | #5 |
| `src/python/piper_train/phonemize/english.py` | ~433 | #9 |
| `src/python/piper_train/phonemize/base.py` | ~57 | #13 |
| `src/python/piper_train/phonemize/registry.py` | ~44 | #13 |
| `src/python/piper_train/infer_onnx.py` | ~250 | #6 |
| `src/python/piper_train/export_onnx.py` | ~290 | #7 |
| `src/python/piper_train/vits/models.py` | ~994 | #8 |
| `src/python/piper_train/vits/lightning.py` | ~470 | #14 |
| `src/python/piper_train/vits/dataset.py` | ~300 | #14 |
| `src/python/piper_train/phonemize/custom_dict.py` | - | #10 |
