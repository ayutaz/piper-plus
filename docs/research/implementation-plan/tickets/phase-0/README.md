# Phase 0: facebook/pe-av-small PoC — チケット INDEX

| 項目 | 値 |
|------|-----|
| Phase | 0 |
| マイルストーン | [#10 (https://github.com/ayutaz/piper-plus/milestone/10)](https://github.com/ayutaz/piper-plus/milestone/10) |
| 期日 | 2026-04-25 |
| Claude Code 工数目安 | 合計 30分〜1h (HF Hub ダウンロード待ち含む) |
| 人間エンジニア想定 (参考) | 1〜2h |
| 関連 PR | PR-A (`feat(pea): facebook/pe-av-small loader + minimal PoC`) |
| 前提調査 | `../../peav-style-conditioning.md` §4, §12 |
| 元設計書 | `../../phase-0-1.md §Phase 0` (行 14〜223) |

---

## 1. 概要

Fork `yusuke-ai/piper-plus` の `feature/2026-04-14-2312-peav-style-conditioning` ブランチが採用している `facebook/pe-av-small` (Meta Perception Encoder Audio-Visual、arxiv:2512.19687) を、本家 `ayutaz/piper-plus` の transformers 環境で実際にロード・推論できるかを事前検証する Phase。

Phase 0 は 30分〜1h の小タスクだが、**Phase 1〜5 すべての設計決定の前提**となる。具体的には:

- Phase 1 の `--style-vector-dim` デフォルト値 (embedding 次元の決定)
- Phase 3 の `build_pea_style_bank.py` で使用する model loader コード
- Phase 4 の PE-A loss の input preprocessing (sample rate、正規化)
- Phase 5 の fine-tune 時の GPU メモリ余裕見積

したがって、**Phase 0 完了前に Phase 1 以降を開始しないこと** (`phase-0-1.md §補足: Phase 0 の重要性`)。

---

## 2. チケット一覧

| # | タイトル | 優先度 | 工数 | 依存 | ステータス |
|---|---------|-------|------|------|----------|
| [P0-T01](./P0-T01.md) | facebook/pe-av-small モデルの HF Hub ロード検証 | 高 | 15分 | なし | 未着手 |
| [P0-T02](./P0-T02.md) | 音声入力 + Embedding 抽出推論の検証 | 高 | 15分 | P0-T01 | 未着手 |
| [P0-T03](./P0-T03.md) | ベンチマーク + PoC レポート作成 | 高 | 15〜30分 | P0-T01, P0-T02 | 未着手 |

**合計工数**: 45分〜1h (Claude Code 前提、HF Hub からのモデルダウンロード待ち時間を含む)

---

## 3. 依存関係図

```
P0-T01 (ロード検証)
   │
   │ モデルインスタンス + クラス名を共有
   ▼
P0-T02 (推論検証)
   │
   │ API 名 + embedding 次元を共有
   ▼
P0-T03 (ベンチマーク + レポート)
   │
   ▼
Phase 1 / Phase 3 / Phase 4 / Phase 5
```

**並列化の余地**: なし。T01 の成果物 (モデルインスタンス) が T02 の入力、T02 の成果物 (API 名) が T03 の入力となるため、完全な直列。すべて同一スクリプト `src/python/piper_train/tools/test_pe_av_small.py` への段階的追加となる。

---

## 4. 一から考えたら (代替設計の検討)

Phase 0 を白紙から設計し直す場合、以下の選択肢が考えられる。各選択肢のトレードオフを明記し、現在の設計が「fork との 1:1 互換性」「工数 30分〜1h」「Phase 1 以降の設計材料を確実に取得」の 3 条件をすべて満たす最小構成であることを明らかにする。

### 4.1 HF Hub 依存を避けて ONNX 版を自前で作る

**案**: `facebook/pe-av-small` を一度ロードし、ONNX / TorchScript に export したものを piper-plus リポジトリに同梱 (Git LFS) して、以降は ONNX Runtime で使う。

- 利点: `transformers` 依存・`trust_remote_code=True` を排除、CI でオフライン実行可、Phase 2 (ONNX 化) の先行投資になる
- 欠点:
    - Phase 4 の PE-A loss は **勾配が流れる前向き推論** を要求する。ONNX では勾配計算不可、TorchScript でも fork コードとの互換性調整コストが発生
    - Phase 0 の 30分〜1h には収まらない (少なくとも半日)
    - アップストリームのモデル更新追従コストが増える
- 判定: **Phase 0 では見送り**。Phase 4 完了後、学習時のみ PyTorch モデルを使い、style bank 生成 (Phase 3) のみ ONNX 化する分割設計なら検討価値あり

### 4.2 PE-A ではなく別の embedding で代替する

**案**: `wav2vec2-large-xlsr` / `WavLM-Base+` / ECAPA-TDNN (既存 `src/python/piper_train/speaker_encoder/`) のいずれかで代用。

- 利点: piper-plus 内の既存実装・実績を流用可、追加依存ゼロ、Phase 0 自体が不要
- 欠点:
    - fork の PE-A loss (direction + centroid + margin) の数式が **知覚感情空間に最適化された 256/512 次元 embedding** を前提としており、非最適化 embedding では感情分類精度 65% 目標 (`README.md §成功基準`) 達成困難
    - fork とのコード差分が大きくなり、Phase 1 の cherry-pick が複雑化
    - ECAPA-TDNN は話者特徴に最適化されており、感情と話者が混在するリスク
- 判定: **採用しない**。Fork との 1:1 対応を維持するため、PE-A を使う。ただし Phase 0 で PE-A 読み込みが完全に不可能と判明した場合、Phase 5 の実験計画で ECAPA-TDNN フォールバックを検討する余地あり

### 4.3 PoC を Python ではなく shell script で最小化する

**案**: `huggingface-cli download facebook/pe-av-small` + `python -c "import transformers; ..."` の 2 行で済ませる。

- 利点: コード量極小、レビュー対象が小さい、CI 追加不要
- 欠点:
    - ベンチマーク (latency、GPU memory) が書きにくく、Phase 3/4/5 の判断材料が不足
    - `test_inference` の API 探索 (2D vs 3D 入力、`get_audio_embeds` vs `forward`) を複数回試行するロジックが shell では煩雑
    - Phase 4 の PE-A loader 実装への流用性ゼロ
- 判定: **採用しない**。`test_pe_av_small.py` は Phase 4 で PE-A loader モジュール化 (`src/python/piper_train/perception/pe_av_loader.py`) する際の素案となるため、Python 実装が妥当

### 4.4 工数圧縮のための手抜き可能ポイント

| 手抜きポイント | 削減時間 | トレードオフ |
|-------------|---------|-----------|
| CPU 実行のみで完結 (GPU memory 測定省略) | -5分 | Phase 5 GPU メモリ見積が欠ける。許容可だが Phase 5 で再計測必要 |
| T02 の入力 shape 2D/3D の両方試行をやめ、2D のみ試す | -3分 | 3D 必須モデルだった場合 PoC 失敗、切り分けに余計な時間 |
| ベンチマーク `n_runs=5` を `n_runs=3` に縮小 | -1分 | 統計ばらつきが増える。初回測定では許容可 |
| `peav-style-conditioning.md` への追記を省略し PR 本文のみに記載 | -5分 | Phase 3/4 で参照しづらい。短期的には OK、中期的に情報散逸リスク |
| T01 の fallback (Option B: `perception_models` 手動インポート) を省略 | -0分 (失敗時のみ発生) | `trust_remote_code=True` で成功した場合は影響なし |

**推奨**: 手抜きは行わず、30分〜1h の標準工数で完遂する。Phase 0 で得られる情報の質が Phase 1〜5 全体の工数を左右するため、費用対効果が圧倒的に高い。

### 4.5 現在の設計を採用する理由 (まとめ)

- Fork `yusuke-ai/piper-plus` コミット `314b3355` との 1:1 互換性を維持 (Phase 1 cherry-pick の差分最小化)
- 3 チケット直列で 30分〜1h に収まり、Phase 0 の期日 2026-04-25 に十分間に合う
- `test_pe_av_small.py` は Phase 4 の PE-A loader の素案として再利用可能
- ベンチマーク結果を `peav-style-conditioning.md` に追記することで、後続 Phase の情報再調査コストを削減

---

## 5. 成功基準 (Phase 0 全体)

以下をすべて満たせば Phase 1 以降に進める:

- [ ] `src/python/piper_train/tools/test_pe_av_small.py` が `uv run python` で exit code 0 で完走
- [ ] ログに以下の情報がすべて出力されていること:
    - モデルクラス名 (例: `PeAvModel`)
    - 使用 API 名 (例: `get_audio_embeds_2d`)
    - 入力 shape (2D or 3D)
    - 出力 embedding 次元 (例: 256 or 512)
    - L2 normalize 前後の norm (特に normalize 後が 1.0 付近)
    - 平均推論レイテンシ (ms)
    - Peak GPU memory (MB、CUDA 実行時のみ)
- [ ] `docs/research/peav-style-conditioning.md` もしくは `P0-T03.md §10` に実測値表が追記されていること
- [ ] Phase 1 先頭タスクに、`--style-vector-dim` デフォルト値 (embedding 次元) と L2 normalize 要否が連絡されていること
- [ ] ライセンスが Apache-2.0 であることを HF Hub モデルカードで再確認済み (`peav-style-conditioning.md §12` と整合)

**失敗時の対応**: `AutoModel.from_pretrained(..., trust_remote_code=True)` でロード不可だった場合、`phase-0-1.md §0.2 Option B` の `perception_models` リポジトリからの手動インポートを試行。それも失敗した場合、Phase 0 の範囲で `facebook/pe-av-small` 以外の代替 embedding (§4.2) への切り替えを検討し、実装計画全体を再評価する (Phase 1-5 の差分量が増える可能性あり)。

---

## 6. 参考リンク

### 前提資料

- 全体調査: `../../peav-style-conditioning.md`
- 元設計書 Phase 0 章: `../../phase-0-1.md` (行 14〜223)
- 実装計画 INDEX: `../../README.md`

### 外部リソース

- `facebook/pe-av-small`: https://huggingface.co/facebook/pe-av-small (Apache-2.0)
- Perception Encoder 論文: https://arxiv.org/abs/2512.19687
- Fork 元コミット: https://github.com/yusuke-ai/piper-plus/commit/314b3355

### 関連 Phase

- Phase 1: `../phase-1/` (style vector conditioning 学習側統合)
- Phase 3: `../phase-3/` (style bank 生成ツール)
- Phase 4: `../phase-4/` (PE-A emotion loss 統合)
