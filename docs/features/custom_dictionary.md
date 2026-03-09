# カスタム辞書機能

Piperのカスタム辞書機能を使用すると、技術用語や固有名詞の読みを正確に制御できます。

## 概要

カスタム辞書機能は、MeCabの辞書に登録されていない単語（特に技術用語）の読みを指定できる機能です。これにより、「Docker」を「ドッカー」、「GitHub」を「ギットハブ」のように、正しい読みで音声合成を行うことができます。

## 特徴

- **デフォルト辞書**: 200以上の技術用語を含む充実したデフォルト辞書
- **柔軟な辞書形式**: JSON形式で簡単に編集・管理
- **優先度制御**: 単語の優先度を設定して競合を解決
- **大文字小文字の処理**: 適切な大文字小文字の処理
- **複数辞書のサポート**: 複数の辞書ファイルを同時に使用可能

## 使用方法

### コマンドライン（C++版）

```bash
# デフォルト辞書を使用
./piper --model ja_JP-test-medium.onnx --output_file output.wav < input.txt

# カスタム辞書を指定
./piper --model ja_JP-test-medium.onnx --custom-dict my_dict.json --output_file output.wav < input.txt

# 複数の辞書を使用
./piper --model ja_JP-test-medium.onnx --custom-dict dict1.json,dict2.json --output_file output.wav < input.txt
```

### Python版

```python
from piper_train.phonemize import CustomDictionary, phonemize_japanese

# デフォルト辞書を使用
dict_obj = CustomDictionary()
phonemes = phonemize_japanese("DockerとGitHubを使います", custom_dict=dict_obj)

# カスタム辞書ファイルを指定
phonemes = phonemize_japanese("DockerとGitHubを使います", custom_dict="my_dict.json")

# 複数の辞書を使用
phonemes = phonemize_japanese("DockerとGitHubを使います", custom_dict=["dict1.json", "dict2.json"])

# プログラムで単語を追加
dict_obj = CustomDictionary()
dict_obj.add_word("MyAPI", "マイエーピーアイ", priority=10)
text = dict_obj.apply_to_text("MyAPIを呼び出す")
```

## 辞書フォーマット

### バージョン 2.0（推奨）

```json
{
  "version": "2.0",
  "description": "カスタム辞書の説明",
  "metadata": {
    "created": "2025-01-03",
    "author": "作成者名",
    "license": "MIT"
  },
  "entries": {
    "Docker": {
      "pronunciation": "ドッカー",
      "priority": 9
    },
    "GitHub": {
      "pronunciation": "ギットハブ",
      "priority": 9
    },
    "// コメント": "",
    "MyCompany": {
      "pronunciation": "マイカンパニー",
      "priority": 10
    }
  }
}
```

### バージョン 1.0（互換性のため）

```json
{
  "version": "1.0",
  "entries": {
    "Docker": "ドッカー",
    "GitHub": "ギットハブ"
  }
}
```

## デフォルト辞書

Piperには以下のデフォルト辞書が含まれています：

### default_tech_dict.json
- プログラミング言語: Python, JavaScript, Rust, Go など
- 開発ツール: Docker, GitHub, VSCode, npm など
- フレームワーク: React, Django, PyTorch など
- クラウドサービス: AWS, GCP, Azure など
- AI/ML用語: GPU, CUDA, NLP, LLM など

### default_common_dict.json
- 一般的な外来語: Server, Client, Browser など
- 動作・処理: Download, Upload, Install など
- ステータス: Online, Offline, Active など
- セキュリティ: Password, Authentication など

### additional_tech_dict.json（新規追加）
- **最新AI/LLM用語**: ChatGPT, Claude, Anthropic, OpenAI, Gemini, Copilot, Stable Diffusion, Midjourney など
- **最新フレームワーク**: Next.js, Vite, Svelte, Bun, Deno, Prisma, tRPC, Tailwind など
- **クラウド/DevOps**: GitHub Actions, Terraform, ArgoCD, Prometheus, Grafana など
- **データ分析**: BigQuery, Snowflake, Databricks, Kafka, Airflow など
- **セキュリティ**: OWASP, Zero Trust, MFA, SSO, WAF など
- **モバイル開発**: Flutter, React Native, SwiftUI など
- **その他トレンド**: Web3, NFT, Webhook, gRPC, SaaS, DX など

合計で**300以上の技術用語**が登録されており、MeCabの標準辞書では対応できない最新の技術用語も正確に読み上げることができます。

## 優先度について

優先度は0から10の整数で、大きいほど優先されます：

- 10: 最高優先度（プロジェクト固有の用語など）
- 8-9: 高優先度（一般的な技術用語）
- 5-7: 中優先度（デフォルト）
- 1-4: 低優先度

同じ単語が複数の辞書に存在する場合、最も高い優先度の読みが使用されます。

## カスタム辞書の作成

1. テンプレートをコピー:
```bash
cp data/dictionaries/user_custom_dict.json my_dict.json
```

2. エントリを追加:
```json
{
  "version": "2.0",
  "entries": {
    "MyProduct": {
      "pronunciation": "マイプロダクト",
      "priority": 10
    },
    "APIKey": {
      "pronunciation": "エーピーアイキー",
      "priority": 9
    }
  }
}
```

3. 使用:
```bash
./piper --model ja_JP-test-medium.onnx --custom-dict my_dict.json < input.txt
```

## 注意事項

1. **文字エンコーディング**: 辞書ファイルはUTF-8で保存してください
2. **カタカナ表記**: 読みは全角カタカナで記述してください
3. **単語境界**: 単語の境界が正しく認識されるよう、前後にスペースや句読点がある状態でテストしてください
4. **大文字小文字**: 
   - 全て大文字または小文字の単語は、大文字小文字を区別しません
   - 混在する場合（例：PyTorch）は、厳密に一致する必要があります

## トラブルシューティング

### 単語が置換されない場合

1. 辞書ファイルのパスが正しいか確認
2. JSONフォーマットが正しいか確認（JSONバリデータを使用）
3. 単語の前後に適切な区切り（スペース、句読点など）があるか確認
4. 優先度が他の辞書より低くないか確認

### エラーが発生する場合

1. ファイルのエンコーディングがUTF-8か確認
2. JSONの構文エラーがないか確認
3. ファイルの読み取り権限があるか確認

## 貢献方法

デフォルト辞書に追加したい単語がある場合は、GitHubでIssueまたはPull Requestを作成してください。特に以下のような単語を歓迎します：

- よく使われる技術用語
- 新しいフレームワークやツール
- 読み方が分かりにくい略語

## カスタム辞書の更新ワークフロー

### 少数の単語追加（再学習不要）

固有名詞の追加や少数の誤読修正（目安: 1-10語程度）であれば、辞書を更新するだけでそのまま使用できます。

```bash
# 1. 辞書を更新
vim data/dictionaries/user_custom_dict.json

# 2. 音声生成テストで確認
echo "テストテキスト" | uv run python -m piper --model model.onnx --output_file output.wav
```

### 大規模な辞書変更（再学習が必要な場合）

頻出語の読み修正や新しい分野の専門用語を大量に追加する場合は、データセットの再前処理とモデルの再学習が必要になることがあります。詳細は[学習ガイド](../guides/training/training-guide.md)を参照してください。

### ベストプラクティス

- 辞書更新前に現在の辞書とモデルチェックポイントをバックアップ
- 一度に大量の変更を避け、重要な語句から優先的に修正
- 各更新後に音声生成テストを実施し、品質を確認

## 関連情報

- [OpenJTalk](http://open-jtalk.sourceforge.net/)
- [MeCab](https://taku910.github.io/mecab/)
- [Style-Bert-VITS2](https://github.com/litagin02/Style-Bert-VITS2)
- [VITS論文: Conditional Variational Autoencoder with Adversarial Learning for End-to-End Text-to-Speech](https://arxiv.org/abs/2106.06103)
- [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) - pyopenjtalk使用