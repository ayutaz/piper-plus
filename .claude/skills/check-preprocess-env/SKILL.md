---
name: check-preprocess-env
description: 学習前処理 (dataset 構築) を実行する環境の事前検証を 1 コマンドで行う。GPU instance をレンタルして prepare_multilingual_dataset / prepare_bilingual_dataset / extract_speaker_embedding を走らせる前、または前処理が「静かに」おかしな出力を出したときに呼ぶ。g2p inventory / NLTK data / audio_norm cache 形式 / parquet 依存を検査。
disable-model-invocation: false
allowed-tools: Bash(python *) Bash(uv run *) Bash(ssh *) Bash(scp *)
---

# Preprocess Environment Check

学習用データセット前処理を実行する環境 (主に vast.ai 等のレンタル GPU instance) の事前検証を行います。

## 背景 (なぜ必要か)

v8 dataset 再構築 (2026-08-01/02) で、環境不備による**全滅が exit 0 の「静かな成功」として通過**する障害が 3 連発しました (数時間 × 3 回の手戻り):

| 障害 | 症状 | 数秒で検出できた方法 |
|---|---|---|
| PyPI の古い piper-plus-g2p | ja 'fy' / zh 24 音素 / ko 全 inventory 欠落 → 該当言語が dataset から黙って消える | extended map の symbol 数検証 |
| NLTK data 未 DL | g2p-en が全発話 LookupError (str(e) が改行始まりでログ上「空エラー」) → EN 0 件 | EN 1 発話の phonemize 実行 |
| audio_norm cache 形式不整合 | `.npy` cache を旧リーダーが読めず GPU spec / CAM++ 抽出が全件失敗 | write→read roundtrip |

## 実行方法

**ローカル (リポジトリ環境):**

```bash
uv run python scripts/check_preprocess_env.py
```

**リモート instance (前処理をこれから走らせるマシン上で):**

```bash
ssh <instance> '<venv>/bin/python /path/to/piper-plus/scripts/check_preprocess_env.py --require-ko'
```

`--require-ko` は KO phonemize (g2pk2/mecab) を必須化する。ローカル開発機 (特に Windows) には mecab-ko が無いことが多いため default では WARN 止まり。**ko を前処理する環境では必ず付ける。**

exit 0 (ALL PASS) を確認してから前処理を開始してください。FAIL があれば出力中の fix コマンドを適用します。

## チェック項目

1. **遅延 import 依存** — pyarrow.parquet / soundfile / soxr / onnxruntime / torchaudio
2. **g2p extended inventory** — `get_phoneme_id_map("ja-en-zh-es-fr-pt-sv-ko")` が契約シンボル数 (185) と一致 (不一致 = stale PyPI 版 → `pip install -e src/python/g2p[all]`)
3. **EN phonemize** — NLTK data 込みで 1 発話が実際に通る
4. **KO phonemize** — g2pk2 + mecab backend
5. **audio_norm cache roundtrip** — `.npy` write → 共有ローダー read (+ legacy `.pt`)

## ランタイム側の fail-fast (このスキルと対)

前処理ツール自体にも防御を実装済み (`tests/test_preprocess_failfast.py` で契約 pin):

- ソース 0 件 parse / 音素化成功率 <50% / assemble 成功率 <50% → RuntimeError
- CAM++ 抽出全滅 → RuntimeError (dataset.jsonl を書き換えない)

事前検証をすり抜けた環境問題も途中で止まる設計ですが、**開始前にこのスキルを通す方が安い** (前処理は数時間、検証は数秒)。
