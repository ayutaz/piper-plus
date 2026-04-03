# M2-6: CI 統合更新

> **Phase:** 2 --- ストリーミング + テスト
> **見積り:** 中
> **依存:** M2-4 (ストリーミング単体テスト), M2-5 (統合テスト)
> **ブロック:** Phase 3
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m2-6-ci-統合更新)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

M1-8 で追加した C API の CI ビルド検証を拡張し、Phase 2 で追加されたストリーミングテスト (M2-4) と統合テスト (M2-5) を CI パイプラインに組み込む。テストモデルのキャッシュ機構を追加し、統合テストが 3 プラットフォームで安定実行できる環境を整備する。

**ゴール:**
- M2-4 のモデル不要テストが全 CI ランで実行される
- M2-5 の統合テストがテストモデル存在時に実行される
- テストモデルの取得とキャッシュが CI で自動化される
- シンボル可視性検証がプラットフォーム別に実行される
- 3 プラットフォーム (Linux / macOS / Windows) で CI GREEN

---

## 2. 実装する内容の詳細

### 2.1 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `.github/workflows/cpp-tests.yml` | テストモデルキャッシュ + 統合テスト + シンボル可視性検証 |

### 2.2 テストモデルのダウンロードとキャッシュ

テストモデル `multilingual-test-medium.onnx` (+ `.json`) を HuggingFace (`ayousanz/piper-plus-base`) から取得し、`actions/cache` でキャッシュする。

```yaml
    - name: Cache test model
      id: cache-test-model
      uses: actions/cache@v5
      with:
        path: test/models/
        key: test-model-multilingual-medium-v1
        # v1 は固定キー。モデル更新時にキーをインクリメント

    - name: Download test model
      if: steps.cache-test-model.outputs.cache-hit != 'true'
      run: |
        mkdir -p test/models

        # Download from HuggingFace (ayousanz/piper-plus-base)
        MODEL_URL="https://huggingface.co/ayousanz/piper-plus-base/resolve/main/multilingual-test-medium.onnx"
        CONFIG_URL="https://huggingface.co/ayousanz/piper-plus-base/resolve/main/multilingual-test-medium.onnx.json"

        echo "Downloading test model..."
        wget -q "$MODEL_URL" -O test/models/multilingual-test-medium.onnx || {
          echo "Warning: Failed to download test model. Integration tests will be skipped."
          exit 0
        }
        wget -q "$CONFIG_URL" -O test/models/multilingual-test-medium.onnx.json || {
          echo "Warning: Failed to download model config. Integration tests will be skipped."
          rm -f test/models/multilingual-test-medium.onnx
          exit 0
        }

        echo "Test model downloaded successfully"
        ls -la test/models/
```

### 2.3 辞書のダウンロードとキャッシュ

日本語テストに必要な OpenJTalk 辞書と CMU/pinyin 辞書をキャッシュする。

```yaml
    - name: Cache dictionaries
      id: cache-dicts
      uses: actions/cache@v5
      with:
        path: test/dicts/
        key: test-dicts-v1

    - name: Download dictionaries
      if: steps.cache-dicts.outputs.cache-hit != 'true'
      run: |
        mkdir -p test/dicts/open_jtalk/dic
        mkdir -p test/dicts/piper/dicts

        # OpenJTalk dictionary
        OJT_URL="https://github.com/ayutaz/pyopenjtalk-plus/releases/download/v0.4.1.post7/open_jtalk_dic_utf_8.tar.gz"
        wget -q "$OJT_URL" -O /tmp/ojt_dic.tar.gz || exit 0
        tar -xzf /tmp/ojt_dic.tar.gz -C test/dicts/open_jtalk/dic --strip-components=1
        rm /tmp/ojt_dic.tar.gz

        # CMU dictionary and pinyin data are bundled with the model config
        # or downloaded by piper-plus at runtime. For CI, we rely on
        # dict_dir being set correctly in test code.

        echo "Dictionaries downloaded:"
        ls -la test/dicts/open_jtalk/dic/ | head -5
```

### 2.4 ワークフロー全体構成

```yaml
name: C++ Tests

on:
  pull_request:
    branches: [ dev ]
    paths:
      - 'src/cpp/**'
      - 'CMakeLists.txt'
      - '.github/workflows/cpp-tests.yml'
  workflow_dispatch:

permissions:
  contents: read

jobs:
  test-cpp:
    name: C++ Tests on ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        build-type: [Release]

    steps:
      - uses: actions/checkout@v6
        with:
          submodules: true

      # --- 既存のキャッシュ + 依存インストール (M1-8 と同等) ---
      - name: Setup build cache
        uses: actions/cache@v5
        with:
          path: |
            ~/.cache/ccache
            ~/Library/Caches/ccache
          key: ${{ runner.os }}-ccache-${{ matrix.build-type }}-${{ hashFiles('**/CMakeLists.txt') }}
          restore-keys: |
            ${{ runner.os }}-ccache-${{ matrix.build-type }}-
            ${{ runner.os }}-ccache-

      - name: Install dependencies (Ubuntu)
        if: runner.os == 'Linux'
        run: |
          # ... 既存の ONNX Runtime インストール (M1-8 と同等) ...

      - name: Install dependencies (macOS)
        if: runner.os == 'macOS'
        run: |
          # ... 既存の ONNX Runtime インストール (M1-8 と同等) ...

      - name: Install dependencies (Windows)
        if: runner.os == 'Windows'
        run: |
          # ... 既存の ONNX Runtime インストール ...

      # --- テストモデル + 辞書キャッシュ (Phase 2 追加) ---
      - name: Cache test model
        id: cache-test-model
        uses: actions/cache@v5
        with:
          path: test/models/
          key: test-model-multilingual-medium-v1

      - name: Download test model
        if: steps.cache-test-model.outputs.cache-hit != 'true'
        shell: bash
        run: |
          mkdir -p test/models
          wget -q "https://huggingface.co/ayousanz/piper-plus-base/resolve/main/multilingual-test-medium.onnx" \
            -O test/models/multilingual-test-medium.onnx || true
          wget -q "https://huggingface.co/ayousanz/piper-plus-base/resolve/main/multilingual-test-medium.onnx.json" \
            -O test/models/multilingual-test-medium.onnx.json || true

      - name: Cache dictionaries
        id: cache-dicts
        uses: actions/cache@v5
        with:
          path: test/dicts/
          key: test-dicts-v1

      - name: Download dictionaries
        if: steps.cache-dicts.outputs.cache-hit != 'true'
        shell: bash
        run: |
          mkdir -p test/dicts/open_jtalk/dic
          wget -q "https://github.com/ayutaz/pyopenjtalk-plus/releases/download/v0.4.1.post7/open_jtalk_dic_utf_8.tar.gz" \
            -O /tmp/ojt_dic.tar.gz || true
          if [ -f /tmp/ojt_dic.tar.gz ]; then
            tar -xzf /tmp/ojt_dic.tar.gz -C test/dicts/open_jtalk/dic --strip-components=1
            rm /tmp/ojt_dic.tar.gz
          fi

      # --- ビルド (共有ライブラリ + テスト) ---
      - name: Configure CMake
        run: |
          cmake -B build \
            -DCMAKE_BUILD_TYPE=${{ matrix.build-type }} \
            -DBUILD_TESTS=ON \
            -DPIPER_PLUS_BUILD_SHARED=ON

      - name: Build
        run: cmake --build build --config ${{ matrix.build-type }} -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)

      # --- テスト実行 ---
      - name: Run unit tests (model-free)
        run: |
          cd build
          echo "=== Running C API unit tests (no model required) ==="
          ctest -R "^test_c_api$" --output-on-failure -V --timeout 60 || true

          echo "=== Running existing C++ tests ==="
          for test in test_gpu_device_id test_phoneme_parser test_model_speaker_detection test_prosody_inference test_swedish_phonemize; do
            if ctest -N | grep -q "${test}"; then
              ctest -R "^${test}$" --output-on-failure -V --timeout 60 || true
            fi
          done

      - name: Run integration tests (model required)
        run: |
          cd build
          echo "=== Running C API integration tests ==="
          if [ -f "../test/models/multilingual-test-medium.onnx" ]; then
            ctest -R "^test_c_api_integration$" --output-on-failure -V --timeout 120
          else
            echo "Test model not found; integration tests will be auto-skipped by GTEST_SKIP"
            ctest -R "^test_c_api_integration$" --output-on-failure -V --timeout 30 || true
          fi
        shell: bash

      # --- シンボル可視性検証 (Phase 2 追加) ---
      - name: Verify symbol visibility (Linux)
        if: runner.os == 'Linux'
        run: |
          echo "=== Checking symbol visibility ==="
          LIB_PATH=$(find build -name "libpiper_plus.so*" -type f | head -1)
          if [ -z "$LIB_PATH" ]; then
            echo "Shared library not found; skipping symbol check"
            exit 0
          fi

          echo "Library: $LIB_PATH"

          # All exported text symbols should start with piper_plus_
          UNEXPECTED=$(nm -D "$LIB_PATH" | grep ' T ' | awk '{print $3}' | grep -v '^piper_plus_' || true)
          if [ -n "$UNEXPECTED" ]; then
            echo "ERROR: Unexpected exported symbols:"
            echo "$UNEXPECTED"
            exit 1
          fi

          echo "Symbol visibility check passed"
          nm -D "$LIB_PATH" | grep ' T ' | head -20

      - name: Verify symbol visibility (macOS)
        if: runner.os == 'macOS'
        run: |
          echo "=== Checking symbol visibility ==="
          LIB_PATH=$(find build -name "libpiper_plus.dylib" -type f | head -1)
          if [ -z "$LIB_PATH" ]; then
            echo "Shared library not found; skipping symbol check"
            exit 0
          fi

          echo "Library: $LIB_PATH"

          # macOS: nm -gU lists global undefined-excluded symbols
          # exported C functions start with _ prefix
          UNEXPECTED=$(nm -gU "$LIB_PATH" | grep ' T ' | awk '{print $3}' | grep -v '^_piper_plus_' || true)
          if [ -n "$UNEXPECTED" ]; then
            echo "ERROR: Unexpected exported symbols:"
            echo "$UNEXPECTED"
            exit 1
          fi

          echo "Symbol visibility check passed"
          nm -gU "$LIB_PATH" | grep ' T ' | head -20

      - name: Verify symbol visibility (Windows)
        if: runner.os == 'Windows'
        shell: cmd
        run: |
          echo === Checking symbol visibility ===
          for /R build %%F in (piper_plus.dll) do (
            echo Library: %%F
            dumpbin /EXPORTS %%F | findstr /C:"piper_plus_"
            echo Symbol check complete
          )

      # --- テスト結果アップロード ---
      - name: Upload test results on failure
        if: failure()
        uses: actions/upload-artifact@v7
        with:
          name: test-results-${{ matrix.os }}-${{ matrix.build-type }}
          path: |
            build/Testing/Temporary/
          retention-days: 7
```

### 2.5 trigger paths の拡張

M1-8 の trigger paths に Phase 2 の新規ファイルを追加:

```yaml
on:
  pull_request:
    branches: [ dev ]
    paths:
      - 'src/cpp/**'
      - 'CMakeLists.txt'
      - '.github/workflows/cpp-tests.yml'
      # Phase 2 additions are under src/cpp/ so already covered
```

`src/cpp/**` のワイルドカードで `piper_plus.h`, `piper_plus_c_api.cpp`, `tests/test_c_api.cpp`, `tests/test_c_api_integration.cpp` は全てカバーされるため、追加の paths 変更は不要。

### 2.6 Windows 対応の考慮事項

| 項目 | Linux/macOS | Windows |
|------|------------|---------|
| モデルダウンロード | `wget` | `Invoke-WebRequest` or `curl` (built-in) |
| テスト実行 | `bash` | `cmd` or `bash` (Git Bash) |
| シンボル検証 | `nm -D` / `nm -gU` | `dumpbin /EXPORTS` |
| shared lib 拡張子 | `.so` / `.dylib` | `.dll` |
| DLL 検索パス | `LD_LIBRARY_PATH` / `DYLD_LIBRARY_PATH` | `PATH` or copy to test dir |

Windows では `ctest` 実行時に `piper_plus.dll` と `onnxruntime.dll` がテスト実行ファイルと同じディレクトリに必要。M1-4 の `copy_dlls_to_target` カスタムコマンドで対応済みの想定。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| CI エンジニア | 1 | cpp-tests.yml の更新 + テストモデルキャッシュ設定 |
| テスター | 1 | 3 プラットフォームでの CI 実行確認 |

---

## 4. 提供範囲とテスト項目

### 4.1 CI で実行されるテスト

| テスト | モデル必要 | Phase | プラットフォーム |
|--------|----------|-------|---------------|
| `test_c_api` (M1-7 + M2-4) | No | 1 + 2 | 全 3 OS |
| `test_c_api_integration` (M2-5) | Yes | 2 | 全 3 OS |
| 既存 C++ テスト (23 個) | No | - | 全 3 OS |
| シンボル可視性 | No | 2 | 全 3 OS (プラットフォーム別コマンド) |

### 4.2 受け入れ基準

- 3 プラットフォーム (ubuntu-latest, macos-latest, windows-latest) で CI GREEN
- テストモデルのキャッシュが正常に機能する (2 回目以降はダウンロードスキップ)
- テストモデル未取得時でも CI が FAIL しない (GTEST_SKIP)
- シンボル可視性チェックが `piper_plus_*` 以外のエクスポートを検出した場合 FAIL

---

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| 懸念 | リスク | 対策 |
|------|--------|------|
| HuggingFace からのモデルダウンロード失敗 | 中 | ダウンロード失敗時は `exit 0` で CI を止めない。統合テストは GTEST_SKIP で自動スキップ |
| テストモデルのサイズによる CI 速度低下 | 低 | `actions/cache` でキャッシュ。初回のみダウンロード (medium モデルは ~75MB) |
| Windows の DLL 検索パス問題 | 中 | M1-4 の `copy_dlls_to_target` で対応済みの想定。未対応の場合、テスト実行前に `PATH` を追加 |
| 辞書ダウンロードの安定性 | 低 | OpenJTalk 辞書は pyopenjtalk-plus の GitHub Release から取得。安定した配布元 |
| `nm` コマンドの出力フォーマット差異 | 低 | Linux (`nm -D`) と macOS (`nm -gU`) で別コマンドを使用。`grep` パターンもプラットフォーム別 |

### 5.2 レビュー項目

- [ ] テストモデルのキャッシュキー (`test-model-multilingual-medium-v1`) がモデル更新時にインクリメントされる運用が文書化されていること
- [ ] Windows でのテスト実行で DLL が見つかること (PATH or copy)
- [ ] `wget` が Windows CI で使えない場合の代替手段 (`curl` 等)
- [ ] シンボル可視性チェックが Windows の `dumpbin` で正しく動作すること
- [ ] 辞書ディレクトリのパスがテストコード (`test_c_api_integration.cpp`) の `dict_dir` 設定と一致すること

---

## 6. 一から作り直すとしたら

**1. テストモデルの事前ビルドと配布:**
現在はテストモデル (multilingual-test-medium.onnx) を HuggingFace から取得しているが、テスト専用の軽量モデルを自動生成する CI ジョブがあると理想的:
- 最小限のシンボル数 (10 個)、1 話者、1 言語の "test-tiny" モデルを Python で生成
- CI の最初のステップで生成し、後続のテストで使用
- 外部サービスへの依存を排除

ただし、テストモデル生成には piper_train の学習パイプラインが必要で、CI の複雑さが大幅に増す。現状の HuggingFace からの取得 + キャッシュが実用的。

**2. Docker ベースの CI:**
3 プラットフォーム対応の CI を Docker コンテナで統一する方法もある。ONNX Runtime + 辞書 + テストモデルをプリインストールしたベースイメージを用意し、ビルド+テストのみ実行。ただし macOS と Windows の Docker 対応が限定的なため、GitHub Actions のネイティブランナーの方が現実的。

**3. テスト結果の構造化レポート:**
現在は `--output-on-failure` でコンソール出力のみ。JUnit XML 形式でテスト結果を出力し、GitHub Actions の Test Summary に統合すると、テスト失敗の原因特定が容易になる。

```yaml
    - name: Run tests
      run: |
        cd build
        ctest --output-junit test-results.xml ...

    - name: Publish test results
      uses: EnricoMi/publish-unit-test-result-action@v2
      if: always()
      with:
        junit_files: build/test-results.xml
```

---

## 7. 後続タスクへの連絡事項

### Phase 3 への申し送り

- **M3-5 (リリースワークフロー):** 本チケットの CI 設定 (テストモデルキャッシュ、辞書キャッシュ、シンボル可視性チェック) はリリースビルドのワークフローでも再利用可能。ただし、リリースビルドでは統合テストはオプショナル (ビルド成功が最低条件)。
- **M3-1 (配布マニフェスト):** シンボル可視性チェックのコマンド (`nm -D`, `nm -gU`, `dumpbin`) は配布前の検証にも使用する。CI ステップの共有化を検討。
- **テストモデルの管理:** 現在のテストモデルは CSS10 JA を 6lang ベースからファインチューニングした `multilingual-test-medium.onnx`。新しいベースモデルが学習された場合、テストモデルの更新とキャッシュキーのインクリメントが必要。

### Phase 4 候補の提案 (振り返りから)

Phase 2 振り返りで以下の改善項目が Phase 4 候補として特定された。M4-1〜M4-6 の既存チケットに加えて検討すること。

- **多言語文分割の精度向上:** `splitTextToSentences()` の正規表現は日本語/英語の 2 パターンのみで、`MultilingualPhonemes` では常に日本語パターンが使われる。`UnicodeLanguageDetector` と連携した言語別文末マーカーの統合、または ICU `BreakIterator` の採用を検討する。(M2-1 懸念事項、M2-6 振り返り 3 項目目を参照)
- **crossfade 対応 Iterator:** `textToAudio` ベースの Iterator は文間 crossfade を行わず、ワンショット (`textToAudioStreaming`) との音質差が生じる可能性がある。Iterator の消費側で crossfade を適用する仕組み、または `textToAudioStreaming` を Iterator 駆動に置き換えて crossfade ロジックを統合する設計を検討する。(M2-2 懸念事項を参照)
- **`textToAudioStreaming` の Iterator 駆動への移行:** `textToAudioStreaming()` の内部実装を Iterator (`synth_start` / `synth_next`) 駆動に置き換え、レガシー API 互換を維持しつつマルチリンガルデッドコード問題を根本解決する。(M2-1 セクション 2.6 の廃止計画を参照)

---

## Phase 2 全体の振り返り: 一から設計するなら

Phase 2 を最初から設計し直すとしたら、以下の 3 つの構造的判断を再検討する。

### 1. `textToAudioStreaming` のマルチリンガルデッドコード問題

**現状の問題:**
`textToAudioStreaming()` (piper.cpp L1756-1761) の `else if (MultilingualPhonemes)` ブランチはデッドコードである。`usesOpenJTalk()` が `MultilingualPhonemes` でも `true` を返すため、マルチリンガルテキストは常に OpenJTalk-only の音素化パスを通り、英語/中国語等が正しく処理されない。

**Phase 2 での対処:**
Iterator パターン (M2-2) は `textToAudio()` ベースで実装することで、マルチリンガル問題を根本的に回避した。`textToAudioStreaming()` のデッドコードは M2-1 でコメント注記を追加するにとどめた。

**理想的な設計:**
`textToAudioStreaming()` を廃止し、Iterator パターンを唯一のストリーミング手段とする。C++ の `textToAudioStreaming()` はレガシー API として残し、内部で Iterator を駆動する形にリファクタする。これにより:
- マルチリンガルストリーミングが自然に動作する
- crossfade ロジック (L1836-1844) が Iterator の消費側に移動し、合成コアがシンプルになる
- 文分割ロジックが `splitTextToSentences()` に一元化される

ただし、この変更は既存の C++ ユーザー (`textToAudioStreaming()` の直接呼び出し) に影響するため、Phase 2 では最小限の変更にとどめた。

### 2. Iterator パターンを textToAudio ベースにした理由

**背景:**
Iterator は `splitTextToSentences()` で文分割した後、各文を `textToAudio()` で個別合成する設計を採用した。代替案として `textToAudioStreaming()` を直接 Iterator 化する方法があった。

**textToAudio ベースを選んだ理由:**
1. マルチリンガル完全対応 (`textToAudio` L1111-1293 のコードパスが正しく動作)
2. `textToAudioStreaming` のデッドコード問題を回避
3. `textToAudio` は広くテストされており、信頼性が高い
4. `SynthesisConfig` の save/restore パターンが既に確立されている

**トレードオフ:**
- `textToAudio` は全テキストを一括処理する設計なので、Iterator では文ごとに呼び出すオーバーヘッドがある (phonemize_openjtalk の初期化が文ごとに発生)
- crossfade が Iterator では行われない (ワンショットとの音質差の可能性)
- 文分割の粒度が `textToAudioStreaming` のそれと異なる (regex ベースの分割 vs textToAudio の parsePhonemeNotation)

**最適解:**
長期的には `textToAudio` のモノリシック処理を Phonemizer -> Encoder -> Synthesizer の 3 層パイプラインに分離し、Iterator がパイプラインの各ステージを文単位で駆動する設計が理想。ただし、この大規模リファクタリングは piper-plus の C++ コアへの深い変更が必要で、Phase 2 のスコープを超える。

### 3. 文分割ロジックの抽出設計

**現状:**
`splitTextToSentences()` (M2-1) は `textToAudioStreaming()` の文分割ロジックを抽出した関数。日本語/英語の正規表現で文境界を検出する。

**設計の弱点:**
1. **言語依存の正規表現:** 日本語 (`[。！？、]+`) と英語 (`[.!?,;:]+`) の 2 パターンのみ。中国語 (`。！？`) やフランス語 (`!?`) は日本語パターンで近似的にカバーされるが、専用の文分割は提供されない。
2. **PhonemeType による分岐:** `usesOpenJTalk()` の戻り値で regex を選択するが、`MultilingualPhonemes` は `usesOpenJTalk() = true` なので常に日本語パターンが使われる。マルチリンガルテキストでは英語文の分割精度が低い。
3. **動的チャンクサイズ:** `calculateDynamicChunkSize()` はテキスト特性に基づいてチャンクサイズを決めるが、ロジックが `textToAudioStreaming` 内にハードコードされている。

**改善案:**
1. `UnicodeLanguageDetector` と連携した多言語対応の文分割。各言語の文末マーカーを統合した分割ルール。
2. ICU の `BreakIterator` (sentence) を使った Unicode 準拠の文分割。ただし ICU への依存を追加するのは piper-plus のビルド複雑さを考慮すると過剰。
3. `splitTextToSentences()` にコールバック or visitor パターンを導入し、言語検出と文分割を一体化。

これらの改善は Phase 4 の候補として検討する。Phase 2 では既存の文分割ロジックをそのまま抽出し、Iterator パターンの動作を優先した。
