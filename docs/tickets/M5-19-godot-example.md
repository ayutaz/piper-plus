# M5-19: Godot GDExtension サンプル

> **Phase:** 5 -- 低優先度改善
> **利用者視点の優先度:** 高 -- godot-piper-plus の保守コスト削減に直結
> **見積り:** 中
> **依存:** Phase 3 完了 (配布バイナリ + pkg-config 必要)
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

`examples/godot/` に GDExtension ラッパーの基本構造を作成し、godot-piper-plus のソースコピー方式からの移行パスを示す。

**現状:** [godot-piper-plus](https://github.com/ayutaz/godot-piper-plus) は piper-plus の C++ ソース 25+ ファイルをコピーして GDExtension に直接コンパイルしている。C API 共有ライブラリを使えば、GDExtension 側は 4 ファイル (~200 行) + SConstruct (~30 行) に大幅簡素化される。

**ゴール:** C API 経由の GDExtension ラッパーを `examples/godot/` にリファレンス実装として提供し、godot-piper-plus の移行を促進する。

---

## 2. 実装する内容の詳細

### 2.1 ディレクトリ構成

```
examples/godot/
  README.md
  SConstruct                  # SCons ビルドスクリプト (~30行)
  src/
    register_types.h          # GDExtension エントリーポイント
    register_types.cpp
    piper_tts_node.h          # PiperTTS ノード (AudioStreamPlayer 派生)
    piper_tts_node.cpp
  demo/
    project.godot             # Godot デモプロジェクト
    main.tscn
    main.gd                   # GDScript デモ
```

### 2.2 PiperTTS ノード API

```cpp
class PiperTTS : public AudioStreamPlayer {
    GDCLASS(PiperTTS, AudioStreamPlayer)
public:
    // プロパティ (Inspector 公開)
    void set_model_path(const String &p_path);
    void set_speaker_id(int p_id);

    // メソッド
    void speak(const String &p_text);        // ワンショット合成 + 再生
    void speak_streaming(const String &p_text); // ストリーミング合成

    // シグナル
    // "synthesis_complete" — 合成完了通知
};
```

### 2.3 SConstruct (pkg-config 利用)

```python
env = SConscript("godot-cpp/SConstruct")
env.ParseConfig("pkg-config --cflags --libs piper_plus")
env.SharedLibrary("demo/bin/piper_tts", Glob("src/*.cpp"))
```

### 2.4 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `examples/godot/` (新規ディレクトリ) | GDExtension サンプル一式 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | GDExtension ラッパー + デモプロジェクト |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### スコープ

- GDExtension ラッパー (register_types + PiperTTS ノード)
- SConstruct (pkg-config ベース)
- Godot デモプロジェクト (GDScript)
- README (ビルド手順、godot-piper-plus からの移行ガイド)

### テスト項目

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| SConstruct ビルド | `scons` | GDExtension .so/.dylib/.dll 生成 |
| Godot エディタ | デモプロジェクトを開く | PiperTTS ノードがインスペクタに表示 |
| ワンショット合成 | GDScript から `speak("テスト")` | 音声再生 |
| ストリーミング合成 | GDScript から `speak_streaming("テスト")` | 逐次音声再生 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| godot-cpp バージョン依存 | 中 | Godot 4.3+ を前提。README にバージョン要件を明記 |
| 共有ライブラリのパス配置 | 中 | Godot エクスポート時に .so/.dylib を PCK に含める方法を README に記載 |
| スレッドセーフティ | 中 | Godot のメインスレッドから C API を呼び出す前提。バックグラウンドスレッドでの合成は非推奨とドキュメント化 |

### レビュー時の確認項目

1. `register_types` の初期化/クリーンアップが正しいこと
2. PiperTTS ノードの `_exit_tree()` で `piper_plus_free()` が呼ばれること
3. pkg-config パスの解決が 3 プラットフォームで動作すること
4. godot-piper-plus との機能差分が README に明記されていること

---

## 6. 一から作り直すとしたら

godot-piper-plus を最初から C API ベースで設計していれば、ソースコピーの保守コストは発生しなかった。C API 共有ライブラリの提供が前提条件だったため、順序としては妥当。godot-kokoro (sherpa-onnx C API 利用) のアーキテクチャを参考にすべき。

---

## 7. 後続タスクへの連絡事項

- **godot-piper-plus リポジトリ:** 本サンプル完成後、godot-piper-plus の README に C API 方式への移行案内を追記。段階的に C API 方式に置き換え、最終的にソースコピー方式を廃止。
- **M5-20 (Android AAR):** Godot Android エクスポートでは AAR ではなく .so を直接バンドルする。M5-20 の Android NDK ビルドが Godot Android エクスポートでも利用可能。
