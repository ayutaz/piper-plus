# COLD-M4: 辞書バイナリ形式化（JSON → bincode）

> **マイルストーン一覧:** [coldstart-milestones.md](coldstart-milestones.md)
> **チケット番号:** COLD-M4
> **ブランチ候補:** `feat/coldstart-m4-bincode-dict`
> **前提:** M1, M2, M3 完了推奨
> **期間:** 2週間
> **期待削減量:** ~350–600ms（英語辞書 200ms → 30ms、中国語辞書 400ms → 50ms）
> **対象:** Rust（主要）/ WASM（応用）
> **リスク:** 中

---

## 1. タスク目的とゴール

### 目的

英語 CMU 辞書（15万エントリ）と中国語 Pinyin 辞書（20万+エントリ）の JSON パース処理を、`bincode` バイナリフォーマットへ置き換える。これにより辞書ロードのボトルネックを排除し、コールドスタート時の初回発話レイテンシを短縮する。

### 現状の問題

現在の辞書ロードは以下3ステップで構成されており、ステップ2の JSON パースがボトルネックとなっている:

1. `std::fs::read_to_string()` — ファイル I/O（~10–20ms）
2. `serde_json::from_str()` — JSON パース（**最大ボトルネック: ~180–380ms**）
3. `HashMap` 構築（~10–20ms）

`bincode` はバイナリ直列化フォーマットのため、ステップ2のコストを 5–10 倍削減できる（JSON の文字列解析が不要になり、メモリレイアウトに近い形で直接デシリアライズされる）。

### ゴール

| 辞書 | 現状 | 目標 |
|------|------|------|
| 英語 CMU Dict（~15万エントリ） | ~200ms | ~30ms 以下 |
| 中国語 Pinyin 単字辞書 | ~150ms | ~20ms 以下 |
| 中国語 Pinyin 句辞書 | ~250ms | ~30ms 以下 |
| **合計削減量** | **~600ms** | **~80ms（削減 ~520ms）** |

M3（並列化）完了後でも辞書ロード自体は高速化されないため、M4 を適用することで辞書ロード時間がほぼゼロになる。

---

## 2. 実装する内容の詳細

### 2-1. 対象ファイルと該当箇所

#### 英語辞書 — `english.rs`

- **ファイル:** `src/rust/piper-core/src/phonemize/english.rs`
- **対象:** `load_cmu_dict()` 関数（行 554–576）および `CMU_DICT_CACHE: OnceLock<HashMap<String, String>>` の初期化（行 549）

現在の実装:
```rust
// 行 549
static CMU_DICT_CACHE: OnceLock<HashMap<String, String>> = OnceLock::new();

// 行 554–576
fn load_cmu_dict(dict_path: &Path) -> Result<HashMap<String, String>, PiperError> {
    let content = std::fs::read_to_string(dict_path)...;
    let raw: serde_json::Value = serde_json::from_str(&content)...;
    // ... HashMap 構築
}
```

変更後の実装案:
```rust
fn load_cmu_dict(dict_path: &Path) -> Result<HashMap<String, String>, PiperError> {
    // .bincode ファイルが隣接していれば使用、なければ JSON フォールバック
    let bincode_path = dict_path.with_extension("bincode");
    if bincode_path.exists() {
        let bytes = std::fs::read(&bincode_path).map_err(|_| PiperError::DictionaryLoad {
            path: bincode_path.display().to_string(),
        })?;
        return bincode::decode_from_slice::<HashMap<String, String>, _>(
            &bytes,
            bincode::config::standard(),
        )
        .map(|(dict, _)| dict)
        .map_err(|e| PiperError::DictionaryLoad {
            path: format!("{}: bincode decode error: {}", bincode_path.display(), e),
        });
    }
    // フォールバック: 既存の JSON ロード
    let content = std::fs::read_to_string(dict_path)...;
    // ... 以降は現状と同じ
}
```

#### 中国語辞書 — `chinese.rs`

- **ファイル:** `src/rust/piper-core/src/phonemize/chinese.rs`
- **対象:** `load_single_char_dict()` 関数（行 666–709）と `load_phrase_dict()` 関数（行 717–758）

各関数に対して英語辞書と同様のパターンを適用する。型は以下の通り:
- `load_single_char_dict` の戻り値: `HashMap<char, String>`（bincode はプリミティブ型に対応）
- `load_phrase_dict` の戻り値: `HashMap<String, Vec<String>>`

#### `Cargo.toml` への依存追加

- **ファイル:** `src/rust/piper-core/Cargo.toml`

```toml
[dependencies]
# 既存の serde_json は JSON フォールバック用として維持
bincode = { version = "2.0", features = ["std", "serde"] }
```

**注意:** bincode v2 は v1 と非互換。`version = "2.0"` でバージョン固定すること。

### 2-2. ビルド時 JSON → bincode 変換スクリプト

`piper-core/build.rs` を新規作成し、ビルド時に辞書 JSON を bincode に変換する。

```rust
// src/rust/piper-core/build.rs（新規作成）
use std::path::PathBuf;
use std::collections::HashMap;

fn convert_json_to_bincode<K, V>(json_path: &PathBuf, bincode_path: &PathBuf)
where
    K: serde::de::DeserializeOwned + serde::Serialize,
    V: serde::de::DeserializeOwned + serde::Serialize,
{
    if !json_path.exists() {
        return; // 辞書が存在しない環境（WASM ビルド等）はスキップ
    }
    // ソース JSON より bincode が新しければスキップ（差分ビルド）
    if let (Ok(jm), Ok(bm)) = (json_path.metadata(), bincode_path.metadata()) {
        if bm.modified().ok() > jm.modified().ok() {
            return;
        }
    }
    let json_str = std::fs::read_to_string(json_path).expect("JSON read failed");
    let dict: HashMap<K, V> = serde_json::from_str(&json_str).expect("JSON parse failed");
    let encoded = bincode::encode_to_vec(&dict, bincode::config::standard())
        .expect("bincode encode failed");
    std::fs::write(bincode_path, encoded).expect("bincode write failed");

    println!("cargo:rerun-if-changed={}", json_path.display());
}

fn main() {
    // 辞書ファイルの探索パスは環境変数 CMUDICT_PATH / PINYIN_PATH を参照
    // テスト環境では `tests/fixtures/` 配下の小サイズ辞書も変換
    println!("cargo:rerun-if-changed=build.rs");
}
```

### 2-3. 辞書配布形式の変更

現在の配布:
```
cmudict_data.json          (~6 MB)
pinyin_single.json         (~1 MB)
pinyin_phrases.json        (~8 MB)
```

変更後の配布（JSON + bincode 両方を同梱。旧バージョンとの互換性維持）:
```
cmudict_data.json          (~6 MB)  ← フォールバック用として維持
cmudict_data.bincode       (~3 MB)  ← 追加
pinyin_single.json         (~1 MB)  ← フォールバック用として維持
pinyin_single.bincode      (~0.5 MB)← 追加
pinyin_phrases.json        (~8 MB)  ← フォールバック用として維持
pinyin_phrases.bincode     (~4 MB)  ← 追加
```

### 2-4. WASM への応用（応用フェーズ）

WASM では辞書はネットワーク経由でフェッチされる。bincode はバイナリサイズの観点で gzip 圧縮 JSON より大きくなる可能性があるため、以下のトレードオフを計測してから判断する:

| フォーマット | サイズ (CMU Dict) | パース時間 |
|-------------|-----------------|-----------|
| JSON        | ~6 MB / gzip ~1.2 MB | ~200ms |
| bincode     | ~3 MB / gzip ~0.9 MB | ~20ms |

WASM での bincode 適用は計測結果次第で検討する（本チケットの必須スコープ外）。

---

## 3. エージェントチームの役割と人数

本チケットは2名体制を推奨する。

| 役割 | 担当範囲 |
|------|---------|
| **エージェント A（Rust 実装）** | `build.rs` 作成、`english.rs` / `chinese.rs` のローダー変更、`Cargo.toml` 依存追加、Unit テスト作成 |
| **エージェント B（計測・検証）** | 計測ベンチマーク整備、JSON フォールバック動作確認、WASM トレードオフ計測、ドキュメント更新 |

エージェント A と B は独立して並行作業できる（A が実装、B が計測環境整備）。A のブランチを B がレビュー後、マージという流れを推奨。

---

## 4. 提供範囲・テスト項目

### 4-1. 提供範囲（スコープ）

| 項目 | 対象 | 対象外 |
|------|------|--------|
| 英語辞書 bincode 化 | ✅ | |
| 中国語辞書 bincode 化 | ✅ | |
| JSON フォールバック維持 | ✅ | |
| build.rs による自動変換 | ✅ | |
| WASM bincode 化 | 計測結果次第 | 必須スコープ外 |
| C# 辞書（DotNetG2P 内部） | | ✅ 対象外 |
| 日本語辞書（jpreprocess） | | ✅ 形式が異なるため対象外 |

### 4-2. Unit テスト

**既存テスト（変更後も全パスを確認）:**

- `src/rust/piper-core/tests/test_english.rs` — CMU Dict ロードと発音変換
- `src/rust/piper-core/tests/test_chinese.rs` — Pinyin 辞書ロードと変換
- `src/rust/piper-core/tests/test_multilingual.rs` — 多言語 phonemizer 統合

**新規追加する Unit テスト（`test_english.rs` および `test_chinese.rs` に追記）:**

```rust
// test_english.rs に追加
#[test]
fn test_load_cmu_dict_bincode_preferred_over_json() {
    // bincode ファイルが存在するとき JSON より bincode が使われることを確認
    // tempfile で一時ディレクトリを作成し bincode を置いてロード
}

#[test]
fn test_load_cmu_dict_falls_back_to_json_when_no_bincode() {
    // bincode ファイルが存在しないとき JSON フォールバックで正常ロードできること
}

#[test]
fn test_load_cmu_dict_bincode_roundtrip_correctness() {
    // JSON でロードした辞書と bincode でロードした辞書が同一内容であること
}

#[test]
fn test_load_cmu_dict_bincode_corrupt_falls_back_or_errors() {
    // 壊れた bincode ファイルが適切にエラーを返すこと（サイレント無視しない）
}
```

同様のテストを `test_chinese.rs` にも追加する。

### 4-3. E2E テスト

1. **音質回帰テスト:** 変更前後で同じテキストから生成した音声の波形一致を確認（`tests/test_voice_api.rs` で参照音声と比較）
2. **ロード時間ベンチマーク:** bincode 化後の辞書ロード時間が目標値（英語 ~30ms、中国語 ~50ms）以内であることを `std::time::Instant` で計測し PR コメントに記載する
3. **フォールバック E2E:** 辞書ディレクトリに JSON のみが存在する状態で CLI が正常に動作することを確認

---

## 5. 実装に関する懸念事項とレビュー項目

### 5-1. 技術的懸念事項

| 懸念 | 詳細 | 対策 |
|------|------|------|
| **bincode v2/v1 非互換** | bincode v2 は v1 と API・バイナリフォーマット両方で非互換 | `Cargo.toml` で `version = "2.0"` を固定、ロックファイルもコミット |
| **`char` 型の bincode シリアライズ** | Rust の `char` は Unicode スカラー値。bincode v2 では `serde` feature が必要 | `bincode = { version = "2.0", features = ["serde"] }` で対応 |
| **ビルド時辞書パス解決** | `build.rs` は辞書 JSON の場所を知る必要があるが、インストール先はプラットフォーム依存 | `CMUDICT_PATH` 環境変数を `build.rs` でも参照し、存在しない場合はスキップ（辞書なし環境でのビルドを妨げない） |
| **差分ビルド** | build.rs が毎回 JSON を読むとビルドが遅くなる | `cargo:rerun-if-changed` で JSON ファイルの更新時のみ再実行 |
| **WASM サイズ** | bincode はバイナリのため gzip 圧縮後のサイズ削減が JSON より小さい可能性 | 計測後に判断。WASM は本チケット必須スコープ外 |
| **旧バージョンのユーザー互換性** | bincode ファイルがないユーザーは JSON フォールバックで動作するため後方互換性あり | フォールバックを必ず維持すること。bincode 不在でもエラーにしない |

### 5-2. レビュー項目チェックリスト

- [ ] `bincode::config::standard()` を使用しており、エンコード/デコードで同一設定を使っているか
- [ ] `build.rs` が辞書不在環境でビルドを失敗させていないか（`return` で早期スキップ）
- [ ] JSON フォールバックのパスが削除されていないか
- [ ] 壊れた bincode ファイルがサイレントに無視されず、適切なエラーを返すか
- [ ] bincode 変換後の辞書エントリ数が JSON と一致するか（roundtrip テスト）
- [ ] `char` の bincode シリアライズが全 Unicode 範囲で正しく機能するか（CJK テスト）
- [ ] CI でビルドが通ることを確認（辞書なし環境でのビルドテスト）

---

## 6. 一から作り直すとしたら

もし辞書形式をゼロから設計し直すとした場合の選択肢と評価:

### 選択肢比較

| 形式 | ロード時間 | バイナリサイズ | 実装コスト | WASM 対応 | 評価 |
|------|-----------|-------------|----------|---------|------|
| **JSON（現状）** | ~200–400ms | ~15 MB / gzip ~3 MB | ゼロ | ◎ | ベースライン |
| **bincode（本チケット）** | ~20–50ms | ~7 MB / gzip ~2 MB | 低 | △ | 今回の選択 |
| **FlatBuffers / Cap'n Proto** | ~5ms（ゼロコピー） | ~5 MB | 高（スキーマ定義・codegen必要） | ◎ | 大規模プロジェクト向け |
| **メモリマップ（mmap）** | ~1ms（初回ページフォルトのみ） | 辞書サイズそのまま | 中（`memmap2` crate） | ✗（ブラウザ非対応） | デスクトップ専用なら最速 |
| **SQLite（rusqlite）** | ~50–100ms（インデックス有効時）| ~10 MB | 高（スキーマ設計・SQL） | ✗ | 部分更新が必要な場合のみ |
| **PHF（完全ハッシュ、phf crate）** | ~1ms（コンパイル時構築） | ~5 MB（バイナリ組み込み） | 中（build.rs 必要） | ◎ | 辞書が静的に確定している場合に最適 |

### 推奨アーキテクチャ（もし再設計するなら）

辞書は読み取り専用かつ静的（更新なし）のため、**PHF（Perfect Hash Function）コンパイル時構築** が最適解となる。`phf_codegen` を使い `build.rs` でコンパイル時に辞書を Rust ソースコードとして埋め込む。これによりランタイムのデシリアライズが不要になり、ロード時間がほぼゼロになる。

ただし PHF は辞書を Rust バイナリに静的に組み込むため:
- バイナリサイズが大きくなる（CMU Dict で +5 MB 程度）
- 辞書更新のたびに再コンパイルが必要
- WASM バイナリサイズへの影響が大きい

本チケットで選択した bincode は「実装コスト低・効果十分・後方互換性あり」という観点で現実的な落としどころである。将来的に辞書のバイナリ組み込みを進める M5 以降のフェーズで PHF 採用を検討することを推奨する。

---

## 7. 後続タスクへの連絡事項

### M5（事前最適化済みモデル配布）への影響

- M4 で確立した `build.rs` による「ビルド時変換 + JSON フォールバック」パターンは M5 での ORT モデル最適化キャッシュ設計と類似する。M5 でも同様の「最適化ファイルが存在すればロード、なければ生成してキャッシュ」パターンを採用できる。
- M4 完了後、辞書ロード時間は ~80ms 程度となり M3 並列化との組み合わせで全体ロード時間は ORT セッション作成時間（~1,000ms）に収束する。M5 はこの残りのボトルネックを解消するフェーズとなる。

### WASM 担当者への連絡

- bincode を WASM に適用するかどうかは本チケットで計測結果を踏まえて判断し、結果を PR に記載すること。WASM での辞書は現在 IndexedDB キャッシュ経由でフェッチされるため、JSON の gzip 転送サイズ vs bincode の生サイズのトレードオフが重要。
- `src/wasm/openjtalk-web/src/dict-manager.js` の辞書フェッチロジックを変更する場合は別チケットを立てること。

### ドキュメント更新（必須）

- `README.md`（または相当するユーザー向けドキュメント）の辞書セットアップ手順に `.bincode` ファイルの説明を追加
- 辞書配布パッケージ（tarball / zip）の構成に `.bincode` ファイルを追加
- `CLAUDE.md` の「Rust 推論エンジン」セクションに bincode 辞書の旨を追記

---

## 関連ファイル

| ファイル | 変更種別 |
|---------|---------|
| `src/rust/piper-core/src/phonemize/english.rs` | 変更（`load_cmu_dict` 関数、行 554–576） |
| `src/rust/piper-core/src/phonemize/chinese.rs` | 変更（`load_single_char_dict` 行 666–709、`load_phrase_dict` 行 717–758） |
| `src/rust/piper-core/Cargo.toml` | 変更（`bincode = "2.0"` 追加） |
| `src/rust/piper-core/build.rs` | 新規作成 |
| `src/rust/piper-core/tests/test_english.rs` | 変更（bincode テスト追加） |
| `src/rust/piper-core/tests/test_chinese.rs` | 変更（bincode テスト追加） |
