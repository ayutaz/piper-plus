# M5-21: 音声回帰テスト

> **Phase:** 5 -- 低優先度改善
> **利用者視点の優先度:** 中 -- 音質劣化の早期検出
> **見積り:** 中
> **依存:** Phase 2 完了 (合成 API 必要)
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

C API 経由の合成出力をゴールデンオーディオと比較し、リファクタリングやバージョンアップによる音質劣化を自動検出するテストフレームワークを構築する。

**現状:** C API の合成テストは「音声サンプル数 > 0」「サンプルレート一致」等のスモークテストのみ。リファクタリング (M5-16 等) で音声出力が変化しても検出する手段がない。npm パッケージ (`src/wasm/openjtalk-web/`) では `audio-regression-baseline.json` による回帰テストが既に実装済み (参考: `tests/fixtures/g2p/audio-regression-baseline.json`)。

**ゴール:** C API 合成結果のハッシュ比較またはメトリクスベースの音声回帰テストを CI に組み込む。

---

## 2. 実装する内容の詳細

### 2.1 テスト方式

**方式 A: サンプルハッシュ比較 (推奨、初期実装)**

deterministic 合成 (`noise_scale = 0`, `noise_w = 0`) の出力バイト列の SHA-256 ハッシュをベースラインと比較。

```cpp
// test_c_api_audio_regression.cpp
TEST(AudioRegression, JA_Deterministic) {
    // deterministic 合成 (noise_scale=0, noise_w=0)
    auto audio = synthesize_deterministic(engine, "こんにちは");
    auto hash = sha256(audio.data(), audio.size() * sizeof(int16_t));
    EXPECT_EQ(hash, BASELINE_JA_HASH);
}
```

**方式 B: メトリクスベース (将来拡張)**

PESQ (知覚品質) / STOI (明瞭度) メトリクスで定量評価。閾値を超える劣化で FAIL。

| メトリクス | 閾値 | ライブラリ |
|-----------|------|-----------|
| PESQ | >= 3.5 (WB) | pypesq / pesq (Python) |
| STOI | >= 0.85 | pystoi (Python) |

方式 B は Python 依存が増えるため、初期実装は方式 A を採用し、方式 B は将来拡張とする。

### 2.2 ベースラインファイル (新規作成)

本チケットで新規作成するファイル。現時点ではディレクトリ・ファイルとも存在しない。

```
tests/fixtures/c-api/                     ← 新規ディレクトリ
  audio-regression-baseline.json          ← 新規ファイル
```

```json
{
  "version": "1.0",
  "model": "multilingual-test-medium.onnx",
  "test_cases": [
    {
      "id": "ja_greeting",
      "text": "こんにちは",
      "language": "ja",
      "speaker_id": 0,
      "noise_scale": 0.0,
      "noise_w": 0.0,
      "expected_sha256": "a1b2c3...",
      "expected_num_samples_approx": 22050,
      "sample_rate": 22050
    },
    {
      "id": "en_greeting",
      "text": "Hello",
      "language": "en",
      "speaker_id": 0,
      "noise_scale": 0.0,
      "noise_w": 0.0,
      "expected_sha256": "d4e5f6...",
      "expected_num_samples_approx": 16000,
      "sample_rate": 22050
    }
  ]
}
```

### 2.3 ベースライン更新ワークフロー

意図的な音質変更時のベースライン更新手順:

0. **初回のみ:** ベースラインファイルが未生成の状態で `UPDATE_BASELINE=1 ctest -R AudioRegression` を実行し、初期ベースラインを生成する
1. `UPDATE_BASELINE=1 ctest -R AudioRegression` でテスト実行
2. テストが新しいハッシュをベースラインファイルに書き込み
3. `git diff tests/fixtures/c-api/audio-regression-baseline.json` で差分確認
4. コミット

### 2.4 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/tests/test_c_api_audio_regression.cpp` | 新規: 音声回帰テスト |
| `tests/fixtures/c-api/audio-regression-baseline.json` | 新規: ベースラインデータ |
| `CMakeLists.txt` (or `cmake/Testing.cmake`) | テストターゲット追加 |
| `.github/workflows/cpp-tests.yml` | 回帰テストの CI 統合 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | テストフレームワーク + ベースライン生成 |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### スコープ

- deterministic 合成のハッシュ比較テスト
- ベースラインファイル生成・更新メカニズム
- CI 統合

### テストケース

| テスト | テキスト | 言語 | 期待結果 |
|--------|---------|------|----------|
| `JA_Greeting` | "こんにちは" | ja | ハッシュ一致 |
| `EN_Greeting` | "Hello" | en | ハッシュ一致 |
| `JA_Long` | "今日は良い天気ですね。散歩に行きましょう。" | ja | ハッシュ一致 |
| `EN_Long` | "The quick brown fox jumps over the lazy dog." | en | ハッシュ一致 |
| `Streaming_vs_Oneshot` | "テスト" | ja | サンプル数近似 (±5%) |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| プラットフォーム間の浮動小数点差異 | 高 | deterministic 合成でも CPU アーキテクチャ (x86 vs ARM) で微小差異が出る可能性。プラットフォーム別ベースラインまたは許容差付き比較を検討。初期実装ではプラットフォーム別ベースライン (`audio-regression-baseline-x86_64.json`, `audio-regression-baseline-arm64.json` 等) の採用を検討し、CI マトリクスごとに対応するベースラインを参照する方式が現実的 |
| ONNX Runtime バージョン更新での出力変化 | 中 | ORT 更新時にベースラインも更新する運用ルールを設定 |
| テストモデルの変更 | 低 | テストモデル (`multilingual-test-medium.onnx`) が変更された場合はベースラインも再生成 |

### レビュー時の確認項目

1. deterministic 合成のパラメータ (`noise_scale=0`, `noise_w=0`) が正しく設定されていること
2. SHA-256 計算がエンディアン非依存であること (リトルエンディアンに統一)
3. ベースライン更新手順が README に記載されていること
4. CI でモデル未存在時に SKIP (FAIL ではない) すること

---

## 6. 一から作り直すとしたら

ハッシュ比較は脆弱 (浮動小数点の微小差異で破綻) なので、最初から PESQ/STOI メトリクスベースにすべきかもしれない。ただし Python 依存の追加は C++ テストの CI を複雑化する。妥協案として、ハッシュ比較 (厳密一致) + サンプル数近似チェック (許容差あり) の二段構えが実用的。

---

## 7. 後続タスクへの連絡事項

- **M5-16 (textToAudioStreaming 移行):** リファクタリング前後で回帰テストを実行し、音声出力の変化を確認すること。
- **npm パッケージとの整合:** `tests/fixtures/g2p/audio-regression-baseline.json` と同様のフォーマットを採用し、将来的にクロスプラットフォーム (C++ / JS) のベースライン統一を検討。
- **方式 B (PESQ/STOI):** C++ テストから Python スクリプトを呼び出す方式 (CTest の `add_test` + Python wrapper) で実装可能。CI に Python 環境が必要になるため、別チケットで対応。
