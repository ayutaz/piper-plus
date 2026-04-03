# M5-18: Dart FFI サンプル

> **Phase:** 5 -- 低優先度改善
> **利用者視点の優先度:** 高 -- Flutter は C API の主要ユースケース
> **見積り:** 中
> **依存:** Phase 3 完了 (配布バイナリ必要)
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

`examples/dart/` に Flutter での piper-plus C API 利用例を作成し、`dart:ffi` によるワンショット合成・ストリーミング合成のリファレンス実装を提供する。

**現状:** C API 共有ライブラリは Phase 1-3 で提供されるが、Flutter/Dart からの利用方法を示すサンプルがない。Dart の `dart:ffi` は C 関数の呼び出しに特化しており、piper_plus.h のバインディング生成 (`ffigen`) + 実際の呼び出しパターンを示す必要がある。

**ゴール:** Flutter 開発者が `examples/dart/` を参照して即座に piper-plus を統合できるリファレンスプロジェクトを提供する。

---

## 2. 実装する内容の詳細

### 2.1 ディレクトリ構成

```
examples/dart/
  README.md
  pubspec.yaml
  ffigen.yaml               # piper_plus.h からバインディング自動生成
  lib/
    piper_plus_bindings.dart # ffigen 生成
    piper_plus.dart          # 高レベル Dart API ラッパー
  example/
    main.dart                # ワンショット合成デモ
    streaming.dart           # ストリーミング合成デモ (NativeCallable.listener)
```

### 2.2 高レベル Dart API (`lib/piper_plus.dart`)

```dart
class PiperPlus {
  /// ワンショット合成
  Uint8List synthesize(String text, {int speakerId = 0});

  /// ストリーミング合成 (NativeCallable.listener)
  Stream<Uint8List> synthesizeStream(String text, {int speakerId = 0});

  void dispose();
}
```

### 2.3 ストリーミングの実装パターン

`NativeCallable.listener` を使用してコールバックを Dart 側の `StreamController` に変換:

```dart
Stream<Uint8List> synthesizeStream(String text) {
  final controller = StreamController<Uint8List>();
  final callback = NativeCallable<PiperPlusAudioCallbackFunction>.listener(
    (Pointer<PiperPlusAudioChunk> chunk, Pointer<Void> _) {
      final samples = chunk.ref.samples.asTypedList(chunk.ref.num_samples);
      controller.add(Uint8List.fromList(samples.buffer.asUint8List()));
      if (chunk.ref.is_last == 1) controller.close();
    },
  );
  _bindings.piper_plus_synthesize_streaming(
      _engine, textPtr, synthConfig, callback.nativeFunction, nullptr);
  return controller.stream;
}
```

### 2.4 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `examples/dart/` (新規ディレクトリ) | Dart FFI サンプルプロジェクト一式 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | Dart サンプル作成 + ffigen 設定 |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### スコープ

- Dart FFI バインディング生成設定 (ffigen.yaml)
- 高レベル Dart ラッパー
- ワンショット + ストリーミングのデモスクリプト
- README (ビルド手順、依存関係)

### テスト項目

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| ffigen 生成 | `dart run ffigen` | バインディング生成成功 |
| ワンショット合成 | `dart run example/main.dart` | WAV ファイル出力 |
| ストリーミング合成 | `dart run example/streaming.dart` | Stream でチャンク受信 |
| メモリリーク確認 | `dispose()` 後にネイティブリソースが解放 | valgrind / Instruments で確認 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| `NativeCallable.listener` の Dart バージョン要件 | 中 | Dart 3.1+ 必須。pubspec.yaml で `sdk: '>=3.1.0'` を指定 |
| 共有ライブラリのパス解決 | 中 | `DynamicLibrary.open()` のパスをプラットフォーム別に分岐。README に記載 |
| ffigen の piper_plus.h パース | 低 | マクロ定義 (`PIPER_PLUS_API`) を ffigen.yaml で除外設定 |

### レビュー時の確認項目

1. `NativeCallable.listener` のコールバックが正しく close されること
2. ネイティブメモリ (samples ポインタ) のライフタイム管理が正しいこと
3. `dispose()` で `piper_plus_free()` が呼ばれること

---

## 6. 一から作り直すとしたら

サンプルではなく `pub.dev` パッケージとして提供する選択肢もある。ただし、パッケージ化にはネイティブアセット配布の仕組み (Dart native assets RFC) が必要で、2026 年時点ではまだ experimental。サンプルとして提供し、パッケージ化は Dart native assets の安定化を待つのが妥当。

---

## 7. 後続タスクへの連絡事項

- **M5-20 (Android AAR):** Flutter Android では AAR 経由で共有ライブラリを配布する。Dart FFI サンプルの Android 対応は M5-20 完了後に追記。
- **godot-piper-plus:** Dart サンプルの `NativeCallable.listener` パターンは GDExtension のコールバック実装の参考になる。
