# OpenJTalk実装の改善内容

## 実施した改善

### 1. セキュリティ修正 (Issue #70)

#### Windows一時ファイルの安全性向上
- `GetCurrentProcessId()` を使用した予測可能なファイル名を廃止
- `GetTempFileName()` を使用して一意の一時ファイルを生成
- 適切なエラーハンドリングとクリーンアップを実装

#### コマンドインジェクション対策
- 内部API実装を追加し、外部プロセス起動を回避可能に
- API実装では外部コマンドを使用せず、メモリ内で処理

### 2. メモリ管理の改善 (Issue #69)

#### 動的バッファ管理
- 固定サイズバッファ（4096バイト）の制限を撤廃
- ファイルサイズに基づく動的バッファ割り当て
- 必要に応じてバッファを自動的に再割り当て

#### メモリリーク対策
- すべてのエラーパスで適切にメモリを解放
- リソースの確実なクリーンアップ

### 3. 内部API実装 (Issue #40)

#### パフォーマンス向上
- `openjtalk_text_to_phonemes_api()` 関数を追加
- OpenJTalkライブラリを直接使用し、プロセス起動のオーバーヘッドを削減
- 一時ファイルI/Oを排除

#### 互換性維持
- 既存の外部バイナリ方式も維持（フォールバック用）
- API方式を優先的に使用し、失敗時にバイナリ方式にフォールバック

### 4. Windows固有の問題修正 (Issue #71)

#### UTF-8エンコーディング対応
- WindowsでUTF-8 BOMを追加して文字化けを防止
- バイナリモードでファイルを書き込み

## 実装の詳細

### ファイル変更一覧

1. **src/cpp/openjtalk_wrapper.c**
   - Windows用の安全な一時ファイル作成
   - 動的バッファ管理
   - UTF-8 BOM対応
   - 新しいAPI関数 `openjtalk_text_to_phonemes_api()`

2. **src/cpp/openjtalk_api.c**
   - 辞書パスの自動取得
   - MeCab辞書の読み込み

3. **src/cpp/openjtalk_phonemize.cpp**
   - API方式を優先的に使用するよう更新

4. **src/cpp/openjtalk_wrapper_functions.h** (新規)
   - wrapper関数の宣言を整理

5. **src/cpp/tests/test_openjtalk_security.cpp** (新規)
   - セキュリティ改善のテスト
   - 並行実行テスト
   - 大量データ処理テスト
   - 特殊文字処理テスト

6. **CMakeLists.txt**
   - openjtalk_api.c をビルド対象に追加

7. **src/cpp/tests/CMakeLists.txt**
   - セキュリティテストを追加

## テスト方法

```bash
# ビルド
mkdir build && cd build
cmake .. -DPIPER_BUILD_TESTS=ON
cmake --build .

# テスト実行
./src/cpp/tests/test_openjtalk_security
```

## 今後の推奨事項

1. **段階的移行**
   - 現在はAPI方式とバイナリ方式の両方をサポート
   - 十分なテスト後、バイナリ方式を廃止可能

2. **パフォーマンス測定**
   - API方式とバイナリ方式のベンチマーク比較
   - メモリ使用量の監視

3. **追加の改善**
   - OpenJTalkインスタンスのキャッシュ（複数回の変換で再利用）
   - マルチスレッド対応の強化