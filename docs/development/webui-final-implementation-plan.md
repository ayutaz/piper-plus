# Piper WebUI 最終実装計画

## エグゼクティブサマリー

Issue #114に基づき、Gradioを使用したシンプルで実用的なWebUIを実装する。初期実装は推論機能に特化し、1週間以内の完成を目指す。

## スコープ（MVP）

### 含まれる機能
1. **テキストから音声生成**
   - 単一/複数行テキスト入力
   - リアルタイム音声再生
   - WAVファイルダウンロード

2. **モデル管理**
   - インストール済みモデルの自動検出
   - モデル情報表示（言語、話者数）
   - 簡単なモデル切り替え

3. **パラメータ調整**
   - Speaker ID（マルチスピーカーモデル用）
   - Length Scale（話速調整: 0.5-2.0）
   - Noise Scale（音質調整: 0.0-1.0）

4. **Docker対応**
   - ワンコマンド起動
   - モデルのvolume マウント
   - 自動ポート設定

### 含まれない機能（将来の拡張）
- 学習機能
- モデルダウンロード機能
- バッチ処理
- API認証
- カスタムテーマ

## 技術設計

### ファイル構成（最小限）
```
src/python_run/piper/
├── webui.py                    # メインアプリケーション
└── requirements_webui.txt      # gradio>=4.0.0

docker/
└── webui/
    ├── Dockerfile
    └── docker-compose.yml
```

### 実装例（webui.py）
```python
#!/usr/bin/env python3
"""Gradio WebUI for Piper TTS"""

import argparse
import json
from pathlib import Path
from typing import List, Tuple

import gradio as gr
import numpy as np

from piper import PiperVoice


def get_available_models(data_dir: Path) -> List[Tuple[str, str]]:
    """Scan directory for available ONNX models"""
    models = []
    for onnx_file in data_dir.rglob("*.onnx"):
        config_file = onnx_file.with_suffix(".onnx.json")
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
            display_name = f"{config.get('language', 'unknown')} - {onnx_file.stem}"
            models.append((display_name, str(onnx_file)))
    return models if models else [("No models found", "")]


def synthesize_speech(
    text: str,
    model_path: str,
    speaker_id: int,
    length_scale: float,
    noise_scale: float,
    noise_w: float,
    sample_rate: int = 22050
) -> Tuple[int, np.ndarray]:
    """Generate speech from text"""
    if not text.strip():
        raise gr.Error("Please enter some text")
    
    if not model_path or not Path(model_path).exists():
        raise gr.Error("Please select a valid model")
    
    # Load voice and generate audio
    voice = PiperVoice.load(model_path)
    audio_generator = voice.synthesize(
        text,
        speaker_id=speaker_id,
        length_scale=length_scale,
        noise_scale=noise_scale,
        noise_w=noise_w
    )
    
    # Convert generator to numpy array
    audio = np.array(list(audio_generator), dtype=np.int16)
    
    return voice.config.sample_rate, audio


def create_interface(data_dir: Path) -> gr.Interface:
    """Create Gradio interface"""
    available_models = get_available_models(data_dir)
    
    with gr.Blocks(title="Piper TTS WebUI") as interface:
        gr.Markdown("# Piper TTS WebUI")
        gr.Markdown("Generate high-quality speech from text using Piper TTS models.")
        
        with gr.Row():
            with gr.Column(scale=2):
                text_input = gr.Textbox(
                    label="Text to synthesize",
                    placeholder="Enter your text here...",
                    lines=5
                )
                
                model_dropdown = gr.Dropdown(
                    choices=available_models,
                    label="Select Model",
                    value=available_models[0][1] if available_models else None
                )
                
                with gr.Accordion("Advanced Settings", open=False):
                    speaker_id = gr.Number(
                        label="Speaker ID",
                        value=0,
                        precision=0,
                        minimum=0,
                        maximum=99
                    )
                    
                    length_scale = gr.Slider(
                        label="Speed (Length Scale)",
                        minimum=0.5,
                        maximum=2.0,
                        value=1.0,
                        step=0.1
                    )
                    
                    noise_scale = gr.Slider(
                        label="Noise Scale",
                        minimum=0.0,
                        maximum=1.0,
                        value=0.667,
                        step=0.01
                    )
                    
                    noise_w = gr.Slider(
                        label="Noise Width",
                        minimum=0.0,
                        maximum=1.0,
                        value=0.8,
                        step=0.01
                    )
                
                synthesize_btn = gr.Button("Generate Speech", variant="primary")
            
            with gr.Column(scale=1):
                audio_output = gr.Audio(
                    label="Generated Speech",
                    type="numpy"
                )
                
                gr.Markdown("""
                ### Tips:
                - Lower speed values = faster speech
                - Higher noise scale = more expressive
                - Speaker ID only works with multi-speaker models
                """)
        
        # Event handlers
        synthesize_btn.click(
            fn=synthesize_speech,
            inputs=[
                text_input,
                model_dropdown,
                speaker_id,
                length_scale,
                noise_scale,
                noise_w
            ],
            outputs=audio_output
        )
        
        # Examples
        gr.Examples(
            examples=[
                ["Hello, welcome to Piper text to speech system.", None, 0, 1.0, 0.667, 0.8],
                ["The quick brown fox jumps over the lazy dog.", None, 0, 0.8, 0.5, 0.8],
                ["人工知能による音声合成のデモンストレーションです。", None, 0, 1.0, 0.667, 0.8],
            ],
            inputs=[text_input, model_dropdown, speaker_id, length_scale, noise_scale, noise_w],
        )
    
    return interface


def main():
    parser = argparse.ArgumentParser(description="Piper TTS WebUI")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("models"),
        help="Directory containing ONNX models"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to run the server on"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Port to run the server on"
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Create a public shareable link"
    )
    
    args = parser.parse_args()
    
    # Create and launch interface
    interface = create_interface(args.data_dir)
    interface.launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share
    )


if __name__ == "__main__":
    main()
```

### Docker設定
```dockerfile
# docker/webui/Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy application
COPY src/python_run /app/python_run
WORKDIR /app

# Create models directory
RUN mkdir -p /models

# Expose Gradio default port
EXPOSE 7860

# Run WebUI
CMD ["python", "-m", "python_run.piper.webui", "--host", "0.0.0.0", "--data-dir", "/models"]
```

## 実装手順

### Phase 1: 基本実装（3日）
1. webui.pyの実装
2. 基本的なテスト
3. requirements_webui.txtの作成

### Phase 2: Docker対応（2日）
1. Dockerfile作成
2. docker-compose.yml作成
3. ビルド・テスト

### Phase 3: ドキュメント・CI（2日）
1. 使用方法ドキュメント
2. CIワークフロー追加
3. リリース準備

## 成功基準

1. **使いやすさ**
   - 初見で使い方が分かる
   - エラーメッセージが分かりやすい

2. **パフォーマンス**
   - 1秒以内に音声生成開始
   - メモリ使用量1GB以下

3. **互換性**
   - 既存のCLIと同じ音質
   - 全モデルフォーマット対応

## リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| Gradioバージョン互換性 | 中 | バージョン固定、定期更新 |
| 大規模テキストでのメモリ不足 | 低 | テキスト長制限（5000文字） |
| モデルファイルの誤選択 | 低 | 自動検証、エラーハンドリング |

## 今後の拡張可能性

1. **短期（1-2ヶ月）**
   - バッチ処理タブ
   - モデル情報詳細表示
   - 音声ファイルアップロード

2. **中期（3-6ヶ月）**
   - ストリーミング生成
   - モデルダウンロード機能
   - 多言語UI

3. **長期（6ヶ月以上）**
   - 学習機能統合
   - クラウドデプロイ対応
   - プラグインシステム

## まとめ

この計画は、実装の複雑さを最小限に抑えつつ、ユーザーに即座に価値を提供することを重視しています。Gradioの強力な機能を活用し、1週間以内に実用的なWebUIを提供できます。