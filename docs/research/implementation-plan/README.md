# Style Vector Conditioning + PE-A Emotion Loss 実装計画

**作成日**: 2026-04-22
**対象機能**: fork `yusuke-ai/piper-plus` の `feature/2026-04-14-2312-peav-style-conditioning` ブランチ実装を本家 `ayutaz/piper-plus` に取り込む
**前提調査**: `../peav-style-conditioning.md` (全体像・ライセンス・アーキテクチャ分析)
**実施方針**: ベース再学習なし、fine-tune のみで対応 (詳細は前提調査 §15)
**総工数目安**: 約 1.5 ヶ月 (分割 PR、段階 Phase)

---

## 目次

| Phase | ファイル | 内容 | 工数 |
|-------|--------|------|------|
| 0 | [phase-0-1.md](phase-0-1.md) (§Phase 0) | `facebook/pe-av-small` PoC | 1〜2h |
| 1 | [phase-0-1.md](phase-0-1.md) (§Phase 1) | Style vector conditioning 学習側統合 | 1 週間 |
| 2 | [phase-2.md](phase-2.md) | ONNX エクスポート + 5 ランタイム対応 | 2 週間 |
| 3 | [phase-3-4.md](phase-3-4.md) (§Phase 3) | Style bank 生成ツール (`build_pea_style_bank.py`) | 3 日 |
| 4 | [phase-3-4.md](phase-3-4.md) (§Phase 4) | PE-A emotion loss 学習側統合 | 1.5 週間 |
| 5 | [phase-5.md](phase-5.md) | 既存 6lang ベースへの Fine-tune 実験 | 3〜5 日 |

---

## 依存関係グラフ

```
Phase 0 (PoC) ──┬──→ Phase 1 (学習側統合) ──┬──→ Phase 2 (ONNX+ランタイム)
                │                          │
                └──→ Phase 3 (ツール)  ────┤
                                           │
                                           ▼
                                     Phase 4 (PE-A loss)
                                           │
                                           ▼
                                     Phase 5 (fine-tune、ベース再学習なし)
```

**並列可能**:
- Phase 1 と Phase 3 は Phase 0 完了後は並列開始可能
- Phase 2 と Phase 4 は独立 (両方とも Phase 1 完了が必要)

---

## 分割 PR 案

| PR | タイトル | Phase | 工数 | 依存 |
|----|---------|-------|-----|------|
| PR-A | `feat(pea): facebook/pe-av-small loader + minimal PoC` | 0 | 1〜2h | なし |
| PR-B | `feat(train): style vector conditioning (models.py + lightning.py + dataset.py + infer.py + CLI)` | 1 | 1 週間 | PR-A |
| PR-C | `feat(onnx): style_vector を ONNX 入力に追加 (mask パターン)` | 2 | 1.5 日 | PR-B |
| PR-D-Py | `feat(infer): support style_vector in Python ONNX inference` | 2 | 1 日 | PR-C |
| PR-D-Cpp | `feat(runtime): add style_vector support to C++ API` | 2 | 2 日 | PR-C |
| PR-D-Rust | `feat(rust): add style_vector to piper-core and CLI` | 2 | 1.5 日 | PR-C |
| PR-D-CSharp | `feat(csharp): add style_vector to PiperPlus.Core and CLI` | 2 | 1.5 日 | PR-C |
| PR-D-Go | `feat(go): add style_vector support to Go engine` | 2 | 1.5 日 | PR-C |
| PR-D-Wasm | `feat(wasm): export style_vector in JS/WASM API` | 2 | 1.5 日 | PR-C |
| PR-E | `feat(tools): build_pea_style_bank.py + inject_style_labels.py + CREMA-D loader` | 3 | 3 日 | PR-A |
| PR-F | `feat(train): PE-A emotion loss 統合 + CLI + docs` | 4 | 1.5 週間 | PR-B, PR-E |
| PR-G | `exp(finetune): CREMA-D fine-tune of 6lang base + evaluation report` | 5 | 3〜5 日 | PR-B, PR-E, PR-F |

PR-D-* は PR-C マージ後、**並列実施可能** (各ランタイム独立)。

---

## 成功基準 (Phase 5 採択判定)

以下をすべて満たせば本家統合成功と判定:

- 英語感情認識精度: **65% 以上** (自動分類器)
- MOS 自然性: **3.8 以上** (ベース 6lang 比で -0.2 以下)
- 学習収束 (validation loss 安定)
- 既存機能 (`style_vector_dim=0`) でのレグレッションなし

詳細は [phase-5.md §5.7](phase-5.md#57-成功基準) 参照。

---

## リスクと注意点 (全 Phase 共通)

| リスク | 優先度 | Phase | 対策 |
|-------|-------|-------|------|
| `facebook/pe-av-small` が transformers で自動ロード不可 | 高 | 0 | Phase 0 で要検証、`trust_remote_code=True` で試行 |
| CREMA-D DL が長時間 (27GB) | 中 | 3, 5 | 事前 DL、GitHub mirror 確認 |
| fine-tune で catastrophic forgetting | 中 | 5 | `--base_lr 2e-5` + `--freeze-dp` + `--ema-decay 0.9995` |
| PE-A loss が NaN で学習不安定 | 中 | 4, 5 | `--pea-emotion-warmup-steps 2000`、`every_n_steps 4` |
| 多言語感情の表現力不足 | 高 | 5 | シナリオ A → B → C 段階的実施、ベース再学習は次フェーズに委ねる |
| ONNX メタデータ読み込み未標準化 | 低 | 2 | `config.json` に `style_vector_dim` をフォールバック記載 |

---

## 参考リンク

### 前提資料
- 全体調査: `../peav-style-conditioning.md`
- Fork 元: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning

### 外部リソース
- `facebook/pe-av-small`: https://huggingface.co/facebook/pe-av-small (Apache-2.0)
- Perception Encoder 論文: https://arxiv.org/abs/2512.19687
- CREMA-D: https://github.com/CheyneyComputerScience/CREMA-D (ODbL、商用可)
- ESD: https://hltsingapore.github.io/ESD/ (研究目的)
- EmoV-DB: https://github.com/numediart/EmoV-DB (CC-BY)

### 本家先例
- `speaker_embedding` マスクパターン: `src/cpp/piper_plus.h`, `src/python/piper_train/export_onnx.py`
- 部分 weight ロード先行例: `src/python/piper_train/__main__.py` の `--resume-from-multispeaker-checkpoint`

---

## 補足: Phase 0 の重要性

Phase 0 は 1〜2 時間の PoC だが、以下を検証するため**最優先で実施すべき**:

1. `facebook/pe-av-small` の transformers でのロード方法 (標準 AutoModel か、カスタムコード必要か)
2. `get_audio_embeds()` API の正確なシグネチャ
3. 出力 embedding 次元 (256? 512?)
4. 推論速度と GPU メモリ消費

Phase 0 の結果次第で:
- Phase 1 の `--style-vector-dim` 推奨値が決まる
- Phase 3 の `build_pea_style_bank.py` 実装詳細が決まる
- Phase 4 の PE-A model loader 実装が決まる

したがって、**Phase 0 の完了前に Phase 1 以降を進めないこと**。
