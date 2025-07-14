# uPiper パッケージ構造設計

## Unity Package Manager 準拠構造

uPiper は Unity Package Manager (UPM) の標準に準拠したパッケージ構造を採用しています。

## パッケージ構成

### ルート構造
```
Assets/uPiper/
├── package.json          # パッケージマニフェスト
├── package.json.meta     # Unity メタファイル
├── README.md            # パッケージドキュメント
├── README.md.meta       
├── LICENSE              # ライセンスファイル
├── LICENSE.meta         
├── CHANGELOG.md         # 変更履歴
├── CHANGELOG.md.meta    
└── (以下、各ディレクトリ)
```

### Runtime ディレクトリ
すべてのランタイムコードを含みます。

```
Runtime/
├── uPiper.Runtime.asmdef    # ランタイムアセンブリ定義
├── Core/                    # コア機能
├── Phonemizers/            # 音素化システム
├── Synthesis/              # 音声合成
├── Models/                 # モデル管理
├── Native/                 # ネイティブ連携
└── Utils/                  # ユーティリティ
```

### Editor ディレクトリ
Unity エディタ専用の拡張機能を含みます。

```
Editor/
├── uPiper.Editor.asmdef    # エディタアセンブリ定義
├── Inspector/              # インスペクター拡張
└── Windows/                # エディタウィンドウ
```

### Plugins ディレクトリ
プラットフォーム別のネイティブライブラリを配置します。

```
Plugins/
├── Windows/x64/            # Windows 64ビット
├── Linux/x64/              # Linux 64ビット
├── Android/                # Android (arm64-v8a, armeabi-v7a)
├── iOS/                    # iOS ユニバーサルバイナリ
└── WebGL/                  # WebAssembly
```

### Models ディレクトリ
Piper TTS モデルファイルを配置します。

```
Models/
└── ja_JP/                  # 日本語モデル
    ├── *.onnx             # ONNX モデルファイル
    └── *.onnx.json        # モデル設定ファイル
```

### Tests ディレクトリ
ユニットテストとエディタテストを含みます。

```
Tests/
├── Runtime/                # ランタイムテスト
│   └── uPiper.Tests.asmdef
└── Editor/                 # エディタテスト
    └── uPiper.EditorTests.asmdef
```

### Samples~ ディレクトリ
Package Manager でインポート可能なサンプルプロジェクト。

```
Samples~/
└── BasicTTS/              # 基本的な TTS サンプル
    ├── BasicTTSDemo.unity
    ├── Scripts/
    └── README.md
```

## アセンブリ定義

### uPiper.Runtime.asmdef
```json
{
    "name": "uPiper.Runtime",
    "rootNamespace": "uPiper",
    "references": [
        "Unity.InferenceEngine",
        "Unity.Burst",
        "Newtonsoft.Json"
    ],
    "includePlatforms": [],
    "excludePlatforms": [],
    "allowUnsafeCode": true,
    "overrideReferences": false,
    "precompiledReferences": [],
    "autoReferenced": true,
    "defineConstraints": [],
    "versionDefines": [],
    "noEngineReferences": false
}
```

### uPiper.Editor.asmdef
```json
{
    "name": "uPiper.Editor",
    "rootNamespace": "uPiper.Editor",
    "references": [
        "uPiper.Runtime"
    ],
    "includePlatforms": [
        "Editor"
    ],
    "excludePlatforms": [],
    "allowUnsafeCode": false,
    "overrideReferences": false,
    "precompiledReferences": [],
    "autoReferenced": true,
    "defineConstraints": [],
    "versionDefines": [],
    "noEngineReferences": false
}
```

## メタファイル規則

すべてのファイルとディレクトリには対応する `.meta` ファイルが必要です：
- GUID は一意である必要があります
- バージョン管理に含める必要があります
- Unity が自動生成しますが、手動で調整が必要な場合があります

## バージョニング

Semantic Versioning (SemVer) に従います：
- MAJOR.MINOR.PATCH (例: 1.2.3)
- MAJOR: 破壊的変更
- MINOR: 機能追加（後方互換性あり）
- PATCH: バグ修正

## 依存関係管理

package.json で明示的に依存関係を定義：
```json
"dependencies": {
    "com.unity.ai.inference": "2.2.1",
    "com.unity.burst": "1.8.20",
    "com.unity.nuget.newtonsoft-json": "3.2.1"
}
```

## ベストプラクティス

1. **名前空間**: すべてのコードは `uPiper` 名前空間を使用
2. **プラットフォーム分岐**: 条件付きコンパイルは最小限に
3. **リソース管理**: Resources フォルダの使用は避け、Addressables を推奨
4. **エラーハンドリング**: 明確な例外メッセージとログ出力
5. **パフォーマンス**: メインスレッドをブロックしない非同期設計

## 配布準備

1. 不要なファイルの削除（.DS_Store, Thumbs.db など）
2. すべてのメタファイルの確認
3. ドキュメントの更新
4. CHANGELOG.md の更新
5. バージョン番号の更新