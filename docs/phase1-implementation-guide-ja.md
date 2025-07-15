# Phase 1 実装ガイド（1週間で完了）

## 概要

Phase 1では、すでに作成済みのコンポーネントの統合と、軽量な新規実装を行います。モデルサイズへの影響を最小限に抑えながら、MOS +0.13-0.22の改善を目指します。

## Day 1-2: EMA統合

### 作業内容
1. `ema.py`（作成済み）を学習パイプラインに統合
2. PyTorch Lightningコールバックとして実装

### 実装手順

#### Step 1: __main__.pyの修正
```python
# src/python/piper_train/__main__.py

# インポート追加
from .vits.ema import EMACallback

# 引数追加（line 42付近）
parser.add_argument(
    "--use-ema",
    action="store_true",
    help="Enable EMA (Exponential Moving Average) for training stability"
)
parser.add_argument(
    "--ema-decay",
    type=float,
    default=0.9995,
    help="EMA decay rate (default: 0.9995)"
)

# コールバック設定（line 160付近）
callbacks = []
if args.checkpoint_epochs is not None:
    callbacks.append(
        ModelCheckpoint(
            every_n_epochs=args.checkpoint_epochs,
            save_top_k=args.save_top_k
        )
    )

# EMAコールバック追加
if args.use_ema:
    callbacks.append(
        EMACallback(
            decay=args.ema_decay,
            apply_ema_every_n_steps=1,
            start_step=1000  # ウォームアップ後に開始
        )
    )

trainer = Trainer.from_argparse_args(args, callbacks=callbacks)
```

### テストコマンド
```bash
# EMA有効で学習
python -m piper_train \
    --dataset-dir ./datasets/test \
    --use-ema \
    --ema-decay 0.9995 \
    --max-steps 100 \
    --batch-size 4
```

## Day 2: AccentProcessor統合

### 作業内容
1. `accent_processor.py`（作成済み）を前処理に統合
2. 日本語データのみで有効化

### 実装手順

#### Step 1: preprocess.pyの修正
```python
# src/python/piper_train/preprocess.py

# インポート追加（line 42付近）
from .phonemize.accent_processor import JapaneseAccentProcessor

# 引数追加（line 120付近）
parser.add_argument(
    "--use-accent-processor",
    action="store_true",
    help="Enable enhanced accent processing for Japanese"
)

# phonemize_batch_openjtalk関数の修正（line 501付近）
def phonemize_batch_openjtalk(
    args: argparse.Namespace, queue_in: JoinableQueue, queue_out: Queue
):
    # アクセント処理器の初期化
    accent_processor = None
    if getattr(args, 'use_accent_processor', False):
        accent_processor = JapaneseAccentProcessor()
        _LOGGER.info("AccentProcessor enabled for Japanese")
    
    # 既存のコード...
    
    for utt in utt_batch:
        try:
            # 基本的な音素化
            utt.phonemes = phonemize_japanese(casing(utt.text))
            
            # アクセント処理器を適用
            if accent_processor:
                enhanced_phonemes, prosody_ids = accent_processor.process_text_with_accent(
                    utt.text,
                    utt.phonemes
                )
                utt.phonemes = enhanced_phonemes
                # prosody_idsは将来のF0予測器用に保存
                
            # 既存のphoneme_id変換...
```

### テストコマンド
```bash
# AccentProcessor有効で前処理
python -m piper_train.preprocess \
    --input-dir ./datasets/jsut_raw \
    --output-dir ./datasets/jsut_accent \
    --language ja \
    --use-accent-processor \
    --dataset-format ljspeech
```

## Day 3-4: アクセント強度レベル実装

### 作業内容
既存の二値アクセントを3段階に拡張

### 実装手順

#### Step 1: japanese.pyの修正
```python
# src/python/piper_train/phonemize/japanese.py

# 定数追加（line 10付近）
ACCENT_STRENGTH_MARKS = {
    '[1': 'weak_rise',
    '[2': 'medium_rise', 
    '[3': 'strong_rise',
    ']1': 'weak_fall',
    ']2': 'medium_fall',
    ']3': 'strong_fall',
}

# _get_accent_strength関数を追加（line 80付近）
def _get_accent_strength(a1: int, a2: int, a3: int) -> int:
    """アクセント強度を3段階で判定"""
    if a1 == 0:
        return 0  # アクセントなし
    
    # アクセント位置による強度判定
    relative_position = a2 / a3 if a3 > 0 else 0
    
    if relative_position < 0.3:
        return 1  # 弱いアクセント（句頭付近）
    elif relative_position > 0.7:
        return 3  # 強いアクセント（句末付近）
    else:
        return 2  # 中程度のアクセント

# _phonemes_with_kurihara_prosody関数内の修正（line 120付近）
# 既存の [ と ] を強度付きに変更
if a2 == 2:
    strength = _get_accent_strength(a1, a2, a3)
    if strength > 0:
        phonemes.append(f"]{strength}")
elif a1 > 0 and a2 == 1:
    strength = _get_accent_strength(a1, a2, a3)
    phonemes.append(f"[{strength}")
```

#### Step 2: jp_id_map.pyの更新
```python
# src/python/piper_train/phonemize/jp_id_map.py

def get_japanese_id_map():
    # 既存のマッピング...
    
    # アクセント強度マークを追加
    next_id = len(id_map)
    for strength in [1, 2, 3]:
        id_map[f"[{strength}"] = [next_id]
        next_id += 1
        id_map[f"]{strength}"] = [next_id]
        next_id += 1
    
    return id_map
```

## Day 4: 質問文検出改善

### 実装手順

#### japanese.pyに追加
```python
# 定数定義（line 15付近）
QUESTION_PARTICLES = {'か', 'かな', 'かしら', 'だろうか', 'でしょうか', 'の？', 'かい'}
WH_WORDS = {'なに', '何', 'いつ', 'どこ', 'だれ', '誰', 'なぜ', 'どう', 'どんな'}
RHETORICAL_ENDINGS = {'じゃない', 'じゃん', 'でしょ', 'だろ', 'よね'}

def detect_question_type(text: str) -> tuple[str, str]:
    """質問タイプを詳細に判定"""
    # 修辞疑問文
    if any(text.endswith(ending) for ending in RHETORICAL_ENDINGS):
        return 'rhetorical', '?↓'  # 下降調
    
    # Yes/No疑問文
    if any(text.endswith(p) for p in QUESTION_PARTICLES):
        return 'yes_no', '?↑'  # 上昇調
    
    # WH疑問文
    if any(word in text for word in WH_WORDS):
        return 'wh', '?→'  # 平坦調
    
    # 通常の疑問文
    if text.strip().endswith('？') or text.strip().endswith('?'):
        return 'general', '?'
    
    return 'statement', '$'

# phonemize_japanese関数内で使用（line 45付近）
# 既存の_is_question関数を置き換え
question_type, end_mark = detect_question_type(text)
```

## Day 5: 統合テストとベンチマーク

### テストスクリプト
```bash
#!/bin/bash
# test_phase1.sh

echo "=== Phase 1 統合テスト ==="

# 1. 前処理（全改善有効）
echo "Step 1: 前処理実行中..."
python -m piper_train.preprocess \
    --input-dir ./datasets/jsut_sample \
    --output-dir ./datasets/jsut_phase1 \
    --language ja \
    --use-accent-processor \
    --dataset-format ljspeech

# 2. 学習（EMA有効）
echo "Step 2: 学習開始..."
python -m piper_train \
    --dataset-dir ./datasets/jsut_phase1 \
    --use-ema \
    --ema-decay 0.9995 \
    --quality medium \
    --batch-size 16 \
    --validation-split 0.1 \
    --num-test-examples 3 \
    --max-epochs 10

# 3. 推論テスト
echo "Step 3: 推論テスト..."
TEST_TEXTS=(
    "こんにちは、今日はいい天気ですね。"
    "明日は雨が降るでしょうか？"
    "なぜそんなことを言うの？"
    "そんなわけないじゃない。"
)

for text in "${TEST_TEXTS[@]}"; do
    echo "$text" | python -m piper.infer \
        --model ./checkpoints/best.ckpt \
        --output "test_${RANDOM}.wav"
done

echo "=== テスト完了 ==="
```

## トラブルシューティング

### EMA関連
- メモリ不足: `ema-decay`を0.999に下げる
- 学習が不安定: `start_step`を増やす（例: 5000）

### AccentProcessor関連
- phoneme_id_mapエラー: `jp_id_map.py`の更新を確認
- 処理速度低下: バッチサイズを調整

### アクセント強度関連
- 既存モデルとの互換性: 後方互換性のため、通常の`[`/`]`も残す

## Phase 1 完了チェックリスト

- [ ] EMAが正常に動作し、チェックポイントに保存される
- [ ] AccentProcessorで拡張アクセントマークが生成される
- [ ] アクセント強度が3段階で出力される
- [ ] 質問文の種類が正しく判定される
- [ ] 全改善を有効にして学習が完走する
- [ ] 推論時のモデルサイズが+3MB以内
- [ ] 推論速度が5%以上低下していない

## 期待される成果

- **実装期間**: 5営業日
- **モデルサイズ増加**: +2.5MB
- **推論速度**: 100%（変化なし）
- **MOS向上**: +0.13-0.22
- **特に改善される点**:
  - 学習の安定性（EMA）
  - 日本語のアクセント表現（AccentProcessor、強度レベル）
  - 質問文のイントネーション（質問文検出）

Phase 1完了後、すぐに効果を実感できるはずです。