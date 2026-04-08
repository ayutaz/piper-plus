# M1-M2 一から作り直すとしたら — エージェントチーム議論レポート

**作成日**: 2026-04-08
**対象**: M1 (v1.12.0) + M2a (v1.13.0) + M2b (v1.14.0) 全18チケットの実装
**レビュー観点**: API設計/DX、コード品質、市場戦略、アーキテクチャ

---

## エグゼクティブサマリー

4つのエージェントチーム (API設計、コード品質、市場戦略、アーキテクチャ) が独立に分析した結果、**最大の問題は推論ロジックの重複**であり、「一から作るなら推論エンジンの共通化を最優先すべき」という結論で一致した。

### 全チーム共通の最重要指摘

| # | 指摘 | 重要度 | 影響範囲 |
|---|------|--------|---------|
| 1 | **推論ロジックが4箇所に存在** (infer_onnx, api.py, handler.py, Rust) | CRITICAL | 保守性 |
| 2 | **Wyoming が PiperPlus を使わず推論を再実装** | HIGH | DRY違反 |
| 3 | **モデル解決ロジックが4言語で独立実装** | HIGH | 一貫性 |
| 4 | **ベンチマーク表の暫定値が信頼性を損なう** | MEDIUM | 認知度 |
| 5 | **README が日本語デフォルトで国際認知度のボトルネック** | MEDIUM | 成長 |

---

## 1. アーキテクチャ: 推論エンジンの共通化

### 現状の問題

Python 側の推論ロジックが3箇所に分散:

```
現状 (問題あり)
┌──────────────────┐     ┌──────────────────────┐
│ piper_plus.api   │     │ piper_wyoming.handler │
│ (PiperPlus)      │     │ (PiperPlusSynthesizer)│
└───────┬──────────┘     └──────────┬───────────┘
        │ imports                   │ 再実装 (重複!)
   ┌────▼─────────────┐     ┌──────▼──────────┐
   │ piper_train      │     │ piper_plus_g2p  │
   │ .infer_onnx      │     │ .registry       │
   │ .ort_utils       │     └─────────────────┘
   └──────────────────┘
```

- `api.py` は `piper_train` の内部関数 (`_detect_dominant_language`) を直接 import
- `handler.py` は `piper_plus_g2p.registry` から独自にパイプラインを構築
- 音声変換 (`audio_float_to_int16`) も handler.py で再実装

### 一から作るなら

```
理想設計
┌──────────────────┐     ┌──────────────────────┐
│ piper_plus.api   │     │ piper_wyoming.handler │
│ (PiperPlus)      │     │ (薄いアダプタ ~50行)  │
└───────┬──────────┘     └──────────┬───────────┘
        │ uses                      │ uses
   ┌────▼───────────────────────────▼──────────┐
   │        piper_plus.engine                   │
   │  (推論専用モジュール、piper_train非依存)    │
   │  - onnxruntime + piper_plus_g2p のみ依存   │
   │  - PyTorch 不要                            │
   └───────────────────────────────────────────┘
```

**設計原則:**
1. `piper_plus.engine` が唯一の推論実装 (Single Source of Truth)
2. `piper_train` への依存を排除 → PyTorch の推移的依存を回避
3. Wyoming は `PiperPlus.synthesize()` を呼ぶだけの薄いアダプタに
4. FastAPI サーバー (`inference.py`) も同じエンジンを使用

**得られる効果:**
- バグ修正が1箇所で済む
- `pip install piper-plus` で PyTorch が入らない
- Wyoming アダプタが200行→50行に削減

---

## 2. API設計: PiperPlus クラス

### 現状の問題点

| 問題 | 詳細 |
|------|------|
| ファサードが基盤に依存しすぎ | `piper_train` の3モジュールから直接 import |
| AudioResult が薄い | `play()` がブロッキング、フォーマット変換なし、結合不可 |
| 入力バリデーション不足 | noise_scale, speaker_id の範囲チェックなし |
| 空テキスト処理なし | 空文字列で無言のまま AudioResult を返す |

### 一から作るなら

```python
# 理想の PiperPlus API
class PiperPlus:
    def __init__(self, model="tsukuyomi", *, device="auto", download=True):
        # piper_plus.engine を使用 (piper_train 非依存)
        self._engine = Engine(model_path, config, device)
    
    def synthesize(self, text: str, **params) -> AudioResult:
        if not text or not text.strip():
            raise ValueError("Text must not be empty")
        # パラメータバリデーション
        params = SynthesisParams(**params)  # 範囲チェック付き
        return self._engine.synthesize(text, params)

class AudioResult:
    audio: np.ndarray  # immutable (frozen dataclass)
    sample_rate: int
    metadata: dict  # RTF, テキスト, タイミング情報
    
    def __add__(self, other): ...  # ストリーミング結果の結合
    def to_mp3_bytes(self): ...   # pydub optional
    async def play_async(self): ...  # ノンブロッキング再生
```

**モデルエイリアスの管理:**
- ハードコードではなく JSON ファイル (`piper_plus_models.json`) から読み込み
- GitHub Releases またはレジストリエンドポイントから更新可能に
- Rust CLI / C# CLI と共通のエイリアス定義

---

## 3. README / オンボーディング戦略

### 現状の問題点

1. **選択肢の麻痺**: 3パターン同時提示で初回訪問者の認知負荷が高い
2. **Quick Start 重複**: 「30秒で試す」と「クイックスタート」が別セクションに存在
3. **ベンチマーク暫定値**: 「数値は暫定値」の注記が信頼性を損なう
4. **Python 高レベル API が未反映**: M2-01 で完成した `PiperPlus` クラスが README の「30秒で試す」に未反映

### 一から作るなら

**README 構成:**

```
1. ヒーローセクション (1行で何をするツールか)
   "MIT License • No espeak-ng • 8 Languages • Single 38MB Model"

2. 「Piper は archived。MIT で続くのは piper-plus だけ。」
   (最強のポジショニング文を冒頭に)

3. ワンライナーで音を出す
   pip install piper-plus
   python -c "from piper_plus import PiperPlus; PiperPlus('tsukuyomi').tts_to_file('Hello', 'out.wav')"

4. <details> で他のプラットフォーム
   - Rust CLI / C# CLI / C++ CLI / npm (ブラウザ)

5. 検証済み事実のみ
   モデルサイズ: 38MB (FP16) | 言語: 8 (G2P) / 6 (学習済み) | ライセンス: MIT
   (ベンチマーク表は docs/benchmarks.md に移動、実測値が揃ってから)

6. 主要機能 (以下は現状通り)
```

**多言語 README 戦略:**
- テンプレートから生成するスクリプトで11言語の同期を自動化
- 「30秒で試す」ブロックを共通パーシャルとして管理

---

## 4. CI/CD アーキテクチャ

### 現状の問題点

| 問題 | 詳細 |
|------|------|
| 7つの `-required` ジョブ | 68行の同一ボイラープレート |
| CI config 変更で全ジョブ実行 | `.github/workflows/**` が全9フィルタをトリガー |
| 38ファイルが未整理 | テスト/ビルド/デプロイ/リリースが混在 |

### 一から作るなら

```yaml
# ci.yml を ~30行に削減
jobs:
  changes:
    # dorny/paths-filter (現状と同じ)
  
  # 言語別テストは全て reusable workflow に
  test:
    strategy:
      matrix:
        lang: [python, rust, csharp, cpp, go, wasm]
    if: needs.changes.outputs[matrix.lang] == 'true'
    uses: ./.github/workflows/_test-${{ matrix.lang }}.yml

  # 1つの汎用バリデータで7つの -required ジョブを置換
  validate:
    if: always()
    needs: [test]
    runs-on: ubuntu-latest
    steps:
      - run: '[[ "${{ needs.test.result }}" != "failure" ]]'
```

**CI config トリガーの細分化:**
```yaml
ci-config-python:
  - '.github/workflows/python-*.yml'
ci-config-rust:
  - '.github/workflows/rust-*.yml'
# → ワークフロー編集で全テスト実行を防止
```

---

## 5. エコシステム統合

### 現状の問題点

| 問題 | 詳細 |
|------|------|
| Wyoming が推論を再実装 | PiperPlus を使っていない (DRY 違反) |
| Wyoming が同期呼び出し | `asyncio.to_thread()` 未使用でイベントループをブロック |
| Ollama stack がモデル手動DL | `docker compose up` だけでは動かない |
| HACS アドオン未提供 | HA ユーザーの最大の導入経路を逃している |

### 一から作るなら

**Wyoming アダプタ (50行に削減):**
```python
class PiperPlusWyomingHandler(AsyncEventHandler):
    def __init__(self, tts: PiperPlus):
        self.tts = tts
    
    async def handle_event(self, event):
        synth = Synthesize.from_event(event)
        # asyncio.to_thread でブロッキング回避
        result = await asyncio.to_thread(
            self.tts.synthesize, synth.text,
            language=_resolve_lang(synth)
        )
        await self._stream_audio(result)
```

**Ollama stack の自動モデルDL:**
```yaml
# docker-compose.yml
services:
  piper-api:
    # init コンテナでモデル自動DL
    entrypoint: |
      python -c "from piper_plus import PiperPlus; PiperPlus('tsukuyomi')" &&
      python /app/inference.py --server
```

**HACS アドオン (最大インパクトの統合):**
- Piper 本家がアーカイブされ、HA ユーザーが代替を探している
- Wyoming アダプタ + HACS パッケージングで「ワンクリック移行」を実現
- **推定インパクト**: 数千ユーザーの獲得可能性

---

## 6. 市場ポジショニング

### 現状の最大の課題

| 現状 | 一から作るなら |
|------|-------------|
| 日本語 README がデフォルト | **英語 README をデフォルトに** (国際認知度のボトルネック) |
| 暫定ベンチマークを掲載 | **検証済み事実のみ掲載** (サイズ/言語数/ライセンス) |
| Kokoro.js と品質比較 | **品質比較を避け、サイズ/ライセンス/多言語で差別化** |
| Qiita/Zenn を優先 | **r/selfhosted と Show HN を優先** (成長ボトルネックは国際) |
| Docker Hub + ghcr.io 両方 | **ghcr.io 一本** (管理コスト削減) |

### 一から作る場合の優先順位

1. **Week 1**: README を英語デフォルト化 + 「Piper archived, piper-plus is MIT」を冒頭に
2. **Week 2**: HACS アドオン公開 (Wyoming 基盤は完成済み)
3. **Week 3**: 推論エンジン共通化 (`piper_plus.engine`)
4. **Week 4**: Show HN + r/selfhosted 投稿 (英語 README 完成後)

---

## 7. コード品質: 具体的修正項目

### CRITICAL (即時対応推奨)

| # | ファイル | 行 | 問題 | 修正 |
|---|---------|-----|------|------|
| 1 | handler.py | 30-36 | `audio_float_to_int16` 重複 | PiperPlus を使用する形に書き換え |
| 2 | handler.py | 87-99 | 同期推論がイベントループをブロック | `asyncio.to_thread()` 使用 |
| 3 | _model_resolver.py | 162,167 | HF ダウンロードにタイムアウトなし | `timeout=300` 追加 |

### HIGH (次リリースで対応)

| # | ファイル | 行 | 問題 | 修正 |
|---|---------|-----|------|------|
| 4 | api.py | 188 | 空テキストのバリデーションなし | `ValueError` を raise |
| 5 | api.py | 114-116 | noise_scale 等の範囲チェックなし | bounds checking 追加 |
| 6 | _model_resolver.py | 147 | モデルキャッシュの競合状態 | `FileLock` またはアトミック操作 |
| 7 | __main__.py (Wyoming) | 186-190 | モデルファイル存在チェックなし | 起動時バリデーション追加 |

### MEDIUM (品質改善)

| # | ファイル | 問題 | 修正 |
|---|---------|------|------|
| 8 | api.py | 正規表現による文分割が脆い | `pysbd` ライブラリ検討 |
| 9 | benchmark.py | スレッド数ハードコード (4) | `--threads` 引数追加 |
| 10 | llm-ecosystem.md | Ollama stack を「準備中」と記載 | 実装済みに更新 |

---

## 8. モデル解決ロジックの統一

### 現状: 4言語で独立実装

| 言語 | 実装 | 行数 |
|------|------|------|
| Python (高レベル) | `_model_resolver.py` | 170行 |
| Python (中レベル) | `model_manager.py` | 261行 |
| Rust | `model_download` モジュール | ~200行 |
| C# | `ModelManager.cs` | ~150行 |

### 一から作るなら

**仕様駆動テスト方式 (Option C):**

```json
// test_vectors/model_resolution.json
[
  {"input": "tsukuyomi", "expected_repo": "ayousanz/piper-plus-tsukuyomi-chan"},
  {"input": "/path/to/model.onnx", "expected": "direct_path"},
  {"input": "ayousanz/piper-plus-base", "expected": "hf_download"},
  {"input": "nonexistent", "expected_error": "ModelNotFoundError"}
]
```

- 解決アルゴリズムを仕様書 (Markdown + 擬似コード) として文書化
- テストベクトル (JSON) を全4言語実装で共有
- 各実装は同じテストスイートを実行 → 一貫性を保証

---

## 9. 結論: 一から作る場合のフェーズ設計

### Phase 0: 基盤 (1週間)
- `piper_plus.engine` 推論エンジンを `piper_train` から独立させて実装
- Wyoming アダプタを `PiperPlus` のラッパーに書き換え
- モデル解決テストベクトル JSON を作成

### Phase 1: オンボーディング (1週間)
- README を英語デフォルト化、日本語は README_JA.md に
- 「Piper archived, MIT で続くのは piper-plus だけ」を冒頭に
- `PiperPlus` API のワンライナーを Quick Start に
- ベンチマーク表を docs/benchmarks.md に移動 (実測値が揃うまで)

### Phase 2: エコシステム (2週間)
- HACS アドオンを公開 (Wyoming 基盤は完成済み)
- 英語版 LLM エコシステムガイド
- Ollama stack にモデル自動DL追加

### Phase 3: 認知度 (1週間)
- Show HN 投稿
- r/selfhosted, r/LocalLLaMA 投稿
- (Qiita/Zenn は Phase 3 以降に後回し)

### Phase 4: CI/DX (1週間)
- CI を reusable workflow + matrix に再構成
- 7つの `-required` ジョブを1つに統合
- CI config トリガーを言語別に細分化

**総期間: 5週間** (現状の M1 2週間 + M2 2ヶ月 = 10週間から約半減)

---

## 付録: レビューチーム構成

| チーム | 担当 | 主要発見 |
|--------|------|---------|
| API設計/DX | API設計、ユーザー体験 | 推論ロジック重複、AudioResult の薄さ |
| コード品質 | コードレビュー、バグ探索 | バリデーション不足、Wyoming 同期問題 |
| 市場戦略 | ポジショニング、成長戦略 | 英語デフォルト化、HACS が最大機会 |
| アーキテクチャ | 構造設計、技術的負債 | 4箇所の推論重複、モデル解決の非統一 |

---

## M3 振り返り (2026-04-09 追記)

### M3 実装済み項目

M3チケット計画段階で先行実装されたコア機能:

| チケット | 機能 | 状態 | 備考 |
|---------|------|------|------|
| M3-7 | SSML `<break>` + `<prosody>` | 完了 | Python + Rust + C# + Go の全4言語で動作確認済み |
| M3-15 | Unity UPM パッケージ | 完了 | git URL でインストール可能 |
| M3-5 | VITS2 adversarial DP | コード実装済み | モデル学習は未開始 |
| M3-1 | Speaker Encoder (ECAPA-TDNN) | コード実装済み | ONNX統合完了、品質検証 (GATE) は未実施 |
| M3-8 | MOS ベンチマーク | ツール実装済み | `tools/benchmark/` にサンプル生成・MOS調査・メトリクス計算スクリプト |

### M3 に向けての指摘事項

M1-M2 レトロスペクティブの指摘は M3 計画にも影響する:

1. **推論エンジン共通化が未着手**: Voice Cloning (M3-1〜4) で推論パスがさらに増える前に `piper_plus.engine` の分離が望ましい
2. **Speaker Encoder の GATE 判定基準**: cosine similarity > 0.85 の閾値が設定済みだが、テストベクトルの準備が必要
3. **VITS2 + Voice Cloning の学習順序**: M3-5 (VITS2) → M3-3 (再学習) のクリティカルパスは GPU ~100h のボトルネック。早期着手が鍵
4. **モデル解決ロジックの統一**: M3-4 (全ランタイム統合) の前に、テストベクトル JSON による仕様駆動テスト方式 (本レポート Section 8) の導入を推奨
